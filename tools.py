import os
import uuid
import datetime
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG      = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA       = os.getenv("DATABRICKS_SCHEMA", "finops_gold")
GENIE_ID     = os.getenv("GENIE_SPACE_ID")


def safe_sql(val):
    return str(val).replace("'", "''").strip() if val else ""


def parse_date_intent(query_text: str):
    query_lower = query_text.lower()
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
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

def _resolve_message_id(message):
    # NEVER use direct attribute access — different SDK versions have different fields.
    # SDK <= 0.44: only .id exists, .message_id does not exist at all
    # SDK >= 0.45: .message_id added, .id kept as legacy alias
    try:
        val = getattr(message, "message_id", None)
        if val:
            return val
    except Exception:
        pass
    try:
        val = getattr(message, "id", None)
        if val:
            return val
    except Exception:
        pass
    return None


def _resolve_attachment_id(attachment):
    # SDK <= 0.44: GenieAttachment has no .attachment_id; id lives on .query.id
    # SDK >= 0.45: .attachment_id added directly to GenieAttachment
    try:
        val = getattr(attachment, "attachment_id", None)
        if val:
            return val
    except Exception:
        pass
    try:
        q = getattr(attachment, "query", None)
        if q:
            val = getattr(q, "id", None)
            if val:
                return val
    except Exception:
        pass
    return None


def _fetch_attachment_result(space_id, conversation_id, message_id, attachment_id):
    # SDK >= 0.45: get_message_attachment_query_result
    # SDK <= 0.44: get_message_query_result_by_attachment
    try:
        if hasattr(w.genie, "get_message_attachment_query_result"):
            return w.genie.get_message_attachment_query_result(
                space_id=space_id,
                conversation_id=conversation_id,
                message_id=message_id,
                attachment_id=attachment_id,
            )
        if hasattr(w.genie, "get_message_query_result_by_attachment"):
            return w.genie.get_message_query_result_by_attachment(
                space_id=space_id,
                conversation_id=conversation_id,
                message_id=message_id,
                attachment_id=attachment_id,
            )
    except Exception as e:
        print(f"Attachment result fetch error: {e}")
    return None


def _extract_rows(stmt_resp):
    if not stmt_resp:
        return None
    try:
        columns = []
        if stmt_resp.manifest and stmt_resp.manifest.schema and stmt_resp.manifest.schema.columns:
            columns = [col.name for col in stmt_resp.manifest.schema.columns]
        rows = []
        if stmt_resp.result and stmt_resp.result.data_array:
            rows = stmt_resp.result.data_array
        return {"columns": columns, "rows": rows} if (columns and rows) else None
    except Exception:
        return None


def ask_genie(prompt: str) -> dict:
    empty = {"text": "", "tables": [], "suggested_questions": []}

    if not GENIE_ID:
        return {**empty, "text": "⚠️ GENIE_SPACE_ID is not configured."}

    try:
        message = w.genie.start_conversation_and_wait(
            space_id=GENIE_ID,
            content=prompt,
        )
    except Exception as e:
        return {**empty, "text": f"⚠️ Genie SDK error: {e}"}

    space_id        = getattr(message, "space_id", None)
    conversation_id = getattr(message, "conversation_id", None)
    message_id      = _resolve_message_id(message)

    text_parts  = []
    desc_parts  = []
    tables      = []
    suggestions = []

    for attachment in (getattr(message, "attachments", None) or []):

        # Prose text
        text_att = getattr(attachment, "text", None)
        if text_att:
            content = getattr(text_att, "content", None)
            if content:
                text_parts.append(content.strip())

        # Query attachment
        q = getattr(attachment, "query", None)
        if q:
            desc = getattr(q, "description", None)
            if desc:
                desc_parts.append(desc.strip())

            attachment_id = _resolve_attachment_id(attachment)

            if attachment_id and space_id and conversation_id and message_id:
                result_resp = _fetch_attachment_result(
                    space_id, conversation_id, message_id, attachment_id
                )
                if result_resp:
                    row_data = _extract_rows(getattr(result_resp, "statement_response", None))
                    if row_data:
                        meta = getattr(q, "query_result_metadata", None)
                        is_truncated = getattr(meta, "is_truncated", False) or False
                        tables.append({
                            "columns":      row_data["columns"],
                            "rows":         row_data["rows"],
                            "title":        getattr(q, "title", "") or "",
                            "description":  getattr(q, "description", "") or "",
                            "is_truncated": is_truncated,
                        })

        # Suggested questions (SDK >= 0.45 only — safe to skip if absent)
        sq = getattr(attachment, "suggested_questions", None)
        if sq:
            qs = getattr(sq, "questions", None)
            if qs:
                suggestions.extend(qs)

    # Fallback: message.query_result.statement_id (available in all SDK versions)
    if not tables:
        qr = getattr(message, "query_result", None)
        stmt_id = getattr(qr, "statement_id", None) if qr else None
        if stmt_id:
            try:
                stmt = w.statement_execution.get_statement(statement_id=stmt_id)
                row_data = _extract_rows(stmt)
                if row_data:
                    tables.append({
                        "columns":      row_data["columns"],
                        "rows":         row_data["rows"],
                        "title":        "",
                        "description":  "",
                        "is_truncated": getattr(qr, "is_truncated", False) or False,
                    })
            except Exception as e:
                print(f"Top-level query_result fallback error: {e}")

    answer_text = "\n\n".join(text_parts) if text_parts else "\n\n".join(desc_parts)
    if not answer_text:
        answer_text = "Genie processed the request but returned no readable text."

    return {"text": answer_text, "tables": tables, "suggested_questions": suggestions}


# ---------------------------------------------------------------------------
# ANOMALY DETECTION
# ---------------------------------------------------------------------------

def detect_anomaly(query_text: str):
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
    expiry_days = 30 if action == "SNOOZE" else 365
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.lakebase_memory
        (event_id, resource_id, note, approved_by, expiry_date)
    VALUES (
        '{str(uuid.uuid4())[:8]}', '{safe_sql(resource_id)}',
        '{safe_sql(action)}: {safe_sql(note)}', '{safe_sql(user_email)}',
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