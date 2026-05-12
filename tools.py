import os
import uuid
from databricks.sdk import WorkspaceClient

# Initialize Client
w = WorkspaceClient()

# Environment Variables
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_gold")

# --- 1. PERSISTENCE LOGIC (Chat History) ---

def save_chat_message(session_id: str, user_email: str, role: str, content: str):
    """Persists chat turns to Delta for session continuity."""
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.chat_history 
    VALUES ('{safe_sql(session_id)}', '{safe_sql(user_email)}', '{safe_sql(role)}', '{safe_sql(content)}', CURRENT_TIMESTAMP())
    """
    try:
        w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=insert_sql)
    except Exception as e:
        print(f"History Save Error: {e}")

def load_chat_history(user_email: str, limit: int = 10):
    """Loads previous messages to rebuild the Agent's context."""
    load_sql = f"""
    SELECT role, content FROM {CATALOG}.{SCHEMA}.chat_history 
    WHERE user_email = '{safe_sql(user_email)}' 
    ORDER BY timestamp DESC LIMIT {limit}
    """
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=load_sql)
        if res.result and res.result.data_array:
            history = [{"role": r[0], "content": r[1]} for r in res.result.data_array]
            return history[::-1]
    except:
        pass
    return []

# --- 2. GOVERNANCE LOGIC (Lakebase Persistence) ---

def persist_decision(resource_id: str, action: str, note: str, user_email: str):
    """Saves user governance decisions back to Lakebase memory."""
    # Logic: Snooze = 30 days, Approve = 1 year
    expiry_days = 30 if action == "SNOOZE" else 365
    
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.lakebase_memory (event_id, resource_id, note, approved_by, expiry_date)
    VALUES (
        '{str(uuid.uuid4())[:8]}', 
        '{safe_sql(resource_id)}', 
        '{safe_sql(action)}: {safe_sql(note)}', 
        '{safe_sql(user_email)}', 
        DATE_ADD(CURRENT_DATE(), {expiry_days})
    )
    """
    try:
        w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=insert_sql)
        return f"Successfully persisted {action} for {resource_id}. Memory expires in {expiry_days} days."
    except Exception as e:
        return f"Error persisting decision: {str(e)}"

# --- 3. DISCOVERY LOGIC (Anomaly Detection) ---

def safe_sql(val):
    """Sanitize inputs to prevent SQL injection."""
    if val is None: return ""
    return str(val).replace("'", "''").strip()

def parse_date_intent(query_text: str):
    """Maps natural language months to the dataset date patterns."""
    query_lower = query_text.lower()
    months_map = {
        "oct": "2025-10", "nov": "2025-11", "dec": "2025-12",
        "jan": "2026-01", "feb": "2026-02", "mar": "2026-03", "apr": "2026-04"
    }
    for key, val in months_map.items():
        if key in query_lower: 
            return val
    return "2026-03" # Default fallback for the hackathon data

def detect_anomaly(query_text: str):
    """Scans for billing spikes > 20% compared to 7-day baseline."""
    date_filter = parse_date_intent(query_text)

    anomaly_sql = f"""
    WITH daily_costs AS (
        SELECT resource_id, usage_start_date, SUM(unblended_cost) as daily_cost
        FROM {CATALOG}.{SCHEMA}.billing_summary
        WHERE usage_start_date LIKE '{date_filter}%'
        GROUP BY 1, 2
    ),
    stats AS (
        SELECT *, AVG(daily_cost) OVER (PARTITION BY resource_id ORDER BY usage_start_date ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) as avg_7d
        FROM daily_costs
    )
    SELECT resource_id, daily_cost, avg_7d, usage_start_date 
    FROM stats WHERE daily_cost > (avg_7d * 1.2) AND avg_7d > 0
    ORDER BY usage_start_date DESC
    """
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=anomaly_sql)
        if res.result and res.result.data_array:
            spikes = [{"resource_id": r[0], "cost": float(r[1]), "date": r[3]} for r in res.result.data_array]
            details = "\n".join([f"- {s['resource_id']}: ${s['cost']:,.2f} on {s['date']}" for s in spikes])
            return {"status": "spikes_found", "data": spikes, "details": details}
    except Exception as e:
        return {"status": "error", "details": str(e)}
    
    return {"status": "normal", "details": f"No billing anomalies detected for {date_filter}."}

def lookup_lakebase_memory(resource_id: str):
    """Checks Lakebase for active approvals. Returns None if miss (Agent-friendly)."""
    mem_sql = f"""
    SELECT note, approved_by, expiry_date FROM {CATALOG}.{SCHEMA}.lakebase_memory 
    WHERE resource_id = '{safe_sql(resource_id)}' AND expiry_date >= CURRENT_DATE()
    ORDER BY expiry_date DESC LIMIT 1
    """
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=mem_sql)
        if res.result and res.result.data_array:
            r = res.result.data_array[0]
            return f"Approved by {r[1]} until {r[2]}: {r[0]}"
    except:
        pass
    return None


# --- 4. Genie to converse with data ---

def ask_genie(prompt: str):
    """
    Calls the Genie API to perform natural language discovery on the 
    underlying datasets. This is used for 'Root Cause' investigation.
    """
    genie_id = os.getenv("GENIE_SPACE_ID")
    try:
        # Start a conversation in the specified space
        # We use the 'execute' method to get a direct answer
        result = w.genie.ask(space_id=genie_id, prompt=prompt)
        
        # Genie returns an answer object; we extract the text response
        if result and result.answer:
            return result.answer
        return "Genie was able to process the request but didn't find a specific root cause."
    except Exception as e:
        return f"Genie Investigation Error: {str(e)}"
