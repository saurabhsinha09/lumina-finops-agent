import os
import uuid
from databricks.sdk import WorkspaceClient

# Initialize Client
w = WorkspaceClient()

# --- CONSTANTS ---
# Exported for app.py and graph.py
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_gold")
GENIE_ID = os.getenv("GENIE_SPACE_ID")

def safe_sql(val):
    """Prevents SQL injection by escaping single quotes."""
    return str(val).replace("'", "''").strip() if val else ""

def parse_date_intent(query_text: str):
    """
    Requirement A: Generic Date Detection.
    Maps natural language (e.g., 'March', 'Jan 2025') to YYYY-MM.
    """
    import datetime
    query_lower = query_text.lower()
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
        "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
    }
    
    # Default to current month if nothing found
    now = datetime.datetime.now()
    year = "2026" # Adjusted for Hackathon dataset context
    for y in ["2024", "2025", "2026"]:
        if y in query_lower: year = y
    
    for name, num in months.items():
        if name in query_lower:
            return f"{year}-{num}"
    
    return now.strftime("%Y-%m")

def ask_genie(prompt: str):
    """
    Requirement B: Pure SDK Interaction.
    Sends a prompt to the Genie Space and returns the text response.
    """
    try:
        # The SDK typically expects 'prompt' for execute_query 
        # or 'content' for conversation-based methods.
        # execute_query is the most direct way to get an answer.
        response = w.genie.execute_query(
            space_id=GENIE_ID,
            prompt=prompt
        )
        
        if response and response.answer:
            return response.answer
        return "Genie analyzed the data but did not provide a specific summary."

    except Exception as e:
        # If execute_query fails, we try the conversation method with the correct key
        try:
            # In some SDK versions, start_conversation_and_wait 
            # uses the message structure
            response = w.genie.start_conversation_and_wait(
                space_id=GENIE_ID,
                content=prompt  # 'content' is often used instead of 'prompt' here
            )
            return response.answer
        except Exception as nested_e:
            return f"Genie SDK Error: {str(nested_e)}"

def detect_anomaly(query_text: str):
    """SQL-based detection of cost spikes > 20%."""
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
    
    return {"status": "normal", "details": f"No anomalies detected for {date_filter}."}

def lookup_lakebase_memory(resource_id: str):
    """Retrieves existing approvals from Unity Catalog."""
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

def persist_decision(resource_id: str, action: str, note: str, user_email: str):
    """Saves a governance decision to the Lakebase Delta table."""
    expiry_days = 30 if action == "SNOOZE" else 365
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.lakebase_memory (event_id, resource_id, note, approved_by, expiry_date)
    VALUES ('{str(uuid.uuid4())[:8]}', '{safe_sql(resource_id)}', '{safe_sql(action)}: {safe_sql(note)}', 
            '{safe_sql(user_email)}', DATE_ADD(CURRENT_DATE(), {expiry_days}))
    """
    try:
        w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=insert_sql)
        return f"Success: {resource_id} {action}d in Lakebase."
    except Exception as e:
        return f"Error: {str(e)}"

def save_chat_message(session_id: str, user_email: str, role: str, content: str):
    """Persists chat history for the 'Persistence' pillar."""
    insert_sql = f"""
    INSERT INTO {CATALOG}.{SCHEMA}.chat_history VALUES 
    ('{safe_sql(session_id)}', '{safe_sql(user_email)}', '{safe_sql(role)}', '{safe_sql(content)}', CURRENT_TIMESTAMP())
    """
    try:
        w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=insert_sql)
    except:
        pass

def load_chat_history(user_email: str):
    """Loads history for the current user."""
    load_sql = f"SELECT role, content FROM {CATALOG}.{SCHEMA}.chat_history WHERE user_email = '{safe_sql(user_email)}' ORDER BY timestamp DESC LIMIT 10"
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=load_sql)
        if res.result and res.result.data_array:
            return [{"role": r[0], "content": r[1]} for r in res.result.data_array][::-1]
    except:
        pass
    return []
