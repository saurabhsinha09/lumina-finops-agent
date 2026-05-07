import os
from databricks.sdk import WorkspaceClient
import uuid

# Initialize the Databricks Workspace Client
w = WorkspaceClient()

# Configuration from Environment Variables
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_gold")

# --- 1. PERSISTENCE LOGIC (Chat History) ---

def save_chat_message(session_id: str, user_email: str, role: str, content: str):
    """
    Persists a single chat turn into the Delta history table.
    Ensures the agent 'remembers' the conversation context across refreshes.
    """
    # Escaping single quotes to prevent SQL syntax errors in content
    clean_content = content.replace("'", "''")
    
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.chat_history 
    (session_id, user_email, role, content, timestamp)
    VALUES ('{session_id}', '{user_email}', '{role}', '{clean_content}', CURRENT_TIMESTAMP())
    """
    try:
        w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=insert_sql)
    except Exception as e:
        print(f"Error saving chat history: {e}")

def load_chat_history(user_email: str, limit: int = 15):
    """
    Retrieves previous messages for a specific user to rebuild session state.
    """
    load_sql = f"""
    SELECT role, content FROM {CATALOG}.{SCHEMA}.chat_history 
    WHERE user_email = '{user_email}' 
    ORDER BY timestamp DESC LIMIT {limit}
    """
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=load_sql)
        if res.result and res.result.data_array:
            # We fetch DESC to get the latest, but we return in chronological order for the UI
            history = [{"role": r[0], "content": r[1]} for r in res.result.data_array]
            return history[::-1] 
    except Exception as e:
        print(f"Error loading chat history: {e}")
    return []

# --- 2. GOVERNANCE LOGIC (Lakebase Persistence) ---

def persist_decision(resource_id: str, action_str: str, note: str, user_email: str):
    """
    Writes to your schema: event_id, resource_id, note, approved_by, expiry_date
    """
    # Generate a unique event ID
    event_id = str(uuid.uuid4())[:8]
    
    # Let's assume 'Snooze' sets an expiry 30 days out
    # 'Approve' could set an expiry 10 years out (effectively permanent)
    days_to_add = 30 if action_str == "SNOOZE" else 3650
    
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.lakebase_memory 
    (event_id, resource_id, note, approved_by, expiry_date)
    VALUES (
        '{event_id}', 
        '{resource_id}', 
        '{action_str}: {note}', 
        '{user_email}', 
        DATE_ADD(CURRENT_DATE(), {days_to_add})
    )
    """
    try:
        w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=insert_sql)
        return f"Decision persisted under Event ID {event_id}. Expiry set for {days_to_add} days."
    except Exception as e:
        return f"Error: {str(e)}"

# --- 3. DISCOVERY LOGIC (Anomaly Detection) ---

def parse_date_intent(query_text: str):
    """Maps natural language months to the dataset date patterns."""
    query_lower = query_text.lower()
    months_map = {
        "oct": "2025-10", "nov": "2025-11", "dec": "2025-12",
        "jan": "2026-01", "feb": "2026-02", "mar": "2026-03", "apr": "2026-04"
    }
    for key, val in months_map.items():
        if key in query_lower: return val
    return "2026-" # Default fallback

def detect_anomaly(query_text: str):
    """Aggregated anomaly detection with 7-day baseline."""
    date_pattern = parse_date_intent(query_text)
    
    anomaly_sql = f"""
    WITH daily_costs AS (
        SELECT resource_id, usage_start_date, SUM(unblended_cost) as total_daily_cost
        FROM {CATALOG}.{SCHEMA}.billing_summary
        WHERE usage_start_date LIKE '{date_pattern}%'
        GROUP BY 1, 2
    ),
    stats AS (
        SELECT resource_id, usage_start_date, total_daily_cost as current_cost,
        AVG(total_daily_cost) OVER (PARTITION BY resource_id ORDER BY usage_start_date ROWS BETWEEN 7 PRECEDING and 1 PRECEDING) as avg_prior
        FROM daily_costs
    )
    SELECT resource_id, current_cost, avg_prior, usage_start_date
    FROM stats
    WHERE current_cost > (avg_prior * 1.2) AND avg_prior > 0
    ORDER BY usage_start_date DESC
    """
    
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=anomaly_sql)
        if res.result and res.result.data_array and len(res.result.data_array) > 0:
            found_spikes = []
            descriptions = []
            for row in res.result.data_array:
                found_spikes.append({"resource_id": row[0], "cost": float(row[1]), "avg": float(row[2]), "date": row[3]})
                descriptions.append(f"- {row[0]}: ${float(row[1]):,.2f} on {row[3]}")
            
            return {
                "status": "spikes_found",
                "data": found_spikes,
                "details": "Detected spikes:\\n" + "\\n".join(descriptions[:5])
            }
    except Exception as e:
        return {"status": "error", "details": str(e)}

    return {"status": "normal", "details": f"No anomalies found for {date_pattern}."}

def lookup_lakebase_memory(resource_id: str):
    """
    Check if a resource has an active (non-expired) note.
    """
    memory_sql = f"""
    SELECT note, approved_by, expiry_date 
    FROM {CATALOG}.{SCHEMA}.lakebase_memory 
    WHERE resource_id = '{resource_id}' 
    AND expiry_date >= CURRENT_DATE()
    ORDER BY expiry_date DESC LIMIT 1
    """
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=memory_sql)
        if res.result and res.result.data_array:
            r = res.result.data_array[0]
            return f"Approved by {r[1]} until {r[2]}: {r[0]}"
    except:
        pass
    return "No active approval or snooze found."
