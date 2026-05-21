import os
import uuid
import datetime
from databricks.sdk import WorkspaceClient

# Initialize Client
w = WorkspaceClient()

# --- CONSTANTS ---
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG      = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA       = os.getenv("DATABRICKS_SCHEMA", "finops_gold")
GENIE_ID     = os.getenv("GENIE_SPACE_ID")


def safe_sql(val):
    """Prevents SQL injection by escaping single quotes."""
    return str(val).replace("'", "''").strip() if val else ""


def parse_date_intent(query_text: str):
    """
    Maps natural language (e.g., 'March', 'Jan 2025') to YYYY-MM prefix.
    """
    query_lower = query_text.lower()
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    # Pick an explicit year from the query, default to 2026 for hackathon dataset
    year = "2026"
    for y in ["2024", "2025", "2026"]:
        if y in query_lower:
            year = y

    for name, num in months.items():
        if name in query_lower:
            return f"{year}-{num}"

    return datetime.datetime.now().strftime("%Y-%m")


# ---------------------------------------------------------------------------
# GENIE INTEGRATION
# ---------------------------------------------------------------------------
# The SDK's start_conversation_and_wait() returns a GenieMessage object.
# GenieMessage has NO direct .text attribute.  The response lives in:
#
#   response.attachments  →  List[GenieAttachment]
#
# Each GenieAttachment can contain:
#   • .text   → TextAttachment   (.content holds the AI-generated summary text)
#   • .query  → GenieQueryAttachment  (.description, .query SQL, .statement_id)
#
# For a factual question like "How many EC2 instances in Dec 2025?" Genie
# typically returns:
#   attachment[0].query  — the SQL it ran (+ .description as a plain-English answer)
#   attachment[1].text   — a prose summary  (.content)
#
# We collect ALL available text in priority order:
#   1. text attachments (.text.content)   — the clearest human-readable answer
#   2. query descriptions (.query.description) — Genie's plain-English answer
#   3. query SQL (.query.query)            — fallback so the user sees something
# ---------------------------------------------------------------------------

def ask_genie(prompt: str) -> str:
    """
    Sends a prompt to the configured Genie Space via the Databricks SDK
    and returns a human-readable response string.
    """
    if not GENIE_ID:
        return "⚠️ GENIE_SPACE_ID environment variable is not set."

    try:
        response = w.genie.start_conversation_and_wait(
            space_id=GENIE_ID,
            content=prompt,
        )
    except Exception as e:
        return f"⚠️ Genie SDK error: {e}"

    # --- Parse the GenieMessage attachments ---
    if not response.attachments:
        # Last resort: surface whatever content field exists on the message itself
        raw = getattr(response, "content", None)
        return raw if raw else "Genie returned no attachments for this query."

    text_parts   = []   # prose summaries — most readable
    query_parts  = []   # plain-English descriptions of the SQL result
    sql_parts    = []   # raw SQL — shown only when nothing else is available

    for attachment in response.attachments:
        # 1. Text attachment — AI-generated prose answer / summary
        if attachment.text and attachment.text.content:
            text_parts.append(attachment.text.content.strip())

        # 2. Query attachment — description + optionally the SQL itself
        if attachment.query:
            if attachment.query.description:
                query_parts.append(attachment.query.description.strip())
            if attachment.query.query:
                sql_parts.append(f"```sql\n{attachment.query.query.strip()}\n```")

    # Assemble in priority order — always prefer prose over raw SQL
    parts = text_parts or query_parts or sql_parts
    if parts:
        return "\n\n".join(parts)

    return "Genie processed the request but the response contained no readable content."


# ---------------------------------------------------------------------------
# ANOMALY DETECTION
# ---------------------------------------------------------------------------

def detect_anomaly(query_text: str):
    """SQL-based detection of cost spikes > 20% above a 7-day rolling average."""
    date_filter = parse_date_intent(query_text)

    anomaly_sql = f"""
    WITH daily_costs AS (
        SELECT resource_id, usage_start_date, SUM(unblended_cost) AS daily_cost
        FROM {CATALOG}.{SCHEMA}.billing_summary
        WHERE usage_start_date LIKE '{date_filter}%'
        GROUP BY resource_id, usage_start_date
    ),
    stats AS (
        SELECT *,
            AVG(daily_cost) OVER (
                PARTITION BY resource_id
                ORDER BY usage_start_date
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) AS avg_7d
        FROM daily_costs
    )
    SELECT resource_id, daily_cost, avg_7d, usage_start_date
    FROM stats
    WHERE daily_cost > (avg_7d * 1.2) AND avg_7d > 0
    ORDER BY (daily_cost - avg_7d) DESC
    """
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, statement=anomaly_sql
        )
        if res.result and res.result.data_array:
            spikes = [
                {"resource_id": r[0], "cost": float(r[1]), "avg": float(r[2]), "date": r[3]}
                for r in res.result.data_array
            ]
            details = "\n".join(
                f"- **{s['resource_id']}**: ${s['cost']:,.2f} on {s['date']} "
                f"(+{((s['cost'] - s['avg']) / s['avg'] * 100):.0f}% above avg)"
                for s in spikes
            )
            return {"status": "spikes_found", "data": spikes, "details": details}
    except Exception as e:
        return {"status": "error", "details": str(e), "data": []}

    return {"status": "normal", "details": f"No anomalies detected for {date_filter}.", "data": []}


# ---------------------------------------------------------------------------
# LAKEBASE MEMORY
# ---------------------------------------------------------------------------

def lookup_lakebase_memory(resource_id: str):
    """
    Returns an active governance note for the resource, or None if not found.
    IMPORTANT: callers must treat None as a miss — do NOT use truthiness alone.
    """
    mem_sql = f"""
    SELECT note, approved_by, expiry_date
    FROM {CATALOG}.{SCHEMA}.lakebase_memory
    WHERE resource_id = '{safe_sql(resource_id)}' AND expiry_date >= CURRENT_DATE()
    ORDER BY expiry_date DESC LIMIT 1
    """
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, statement=mem_sql
        )
        if res.result and res.result.data_array:
            r = res.result.data_array[0]
            return f"Approved by {r[1]} until {r[2]}: {r[0]}"
    except Exception as e:
        print(f"Lakebase memory lookup error for {resource_id}: {e}")
    return None


def persist_decision(resource_id: str, action: str, note: str, user_email: str):
    """Saves a governance decision to the lakebase_memory Delta table."""
    expiry_days = 30 if action == "SNOOZE" else 365
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.lakebase_memory
        (event_id, resource_id, note, approved_by, expiry_date)
    VALUES (
        '{str(uuid.uuid4())[:8]}',
        '{safe_sql(resource_id)}',
        '{safe_sql(action)}: {safe_sql(note)}',
        '{safe_sql(user_email)}',
        DATE_ADD(CURRENT_DATE(), {expiry_days})
    )
    """
    try:
        w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, statement=insert_sql
        )
        return f"✅ Success: `{resource_id}` {action}d in Lakebase for {expiry_days} days."
    except Exception as e:
        return f"❌ Error: {e}"


# ---------------------------------------------------------------------------
# CHAT HISTORY
# ---------------------------------------------------------------------------

def save_chat_message(session_id: str, user_email: str, role: str, content: str):
    """Persists a single chat turn to the Delta chat_history table."""
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.chat_history
    VALUES ('{safe_sql(session_id)}', '{safe_sql(user_email)}', '{safe_sql(role)}',
            '{safe_sql(content)}', CURRENT_TIMESTAMP())
    """
    try:
        w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, statement=insert_sql
        )
    except Exception as e:
        print(f"Chat history save error: {e}")


def load_chat_history(user_email: str):
    """Loads the 10 most recent messages for the user, in chronological order."""
    load_sql = f"""
    SELECT role, content FROM {CATALOG}.{SCHEMA}.chat_history
    WHERE user_email = '{safe_sql(user_email)}'
    ORDER BY timestamp DESC LIMIT 10
    """
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, statement=load_sql
        )
        if res.result and res.result.data_array:
            return [{"role": r[0], "content": r[1]} for r in res.result.data_array][::-1]
    except Exception as e:
        print(f"Chat history load error: {e}")
    return []