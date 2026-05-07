import os
from databricks.sdk import WorkspaceClient

# Initialize the client without the warehouse_id
# It will use DATABRICKS_HOST, CLIENT_ID, and CLIENT_SECRET from the environment
w = WorkspaceClient()

# Pull variables for use in functions
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_gold")

def detect_anomaly(query_text: str):
    # Determine which month to look at based on the user prompt
    month_filter = "2026-03" if "March" in query_text else "2026-01"
    
    # SQL to find spikes > 20% vs 7-day rolling average
    anomaly_sql = f"""
    WITH stats AS (
        SELECT 
            resource_id,
            usage_start_date,
            unblended_cost as current_cost,
            AVG(unblended_cost) OVER (
                PARTITION BY resource_id 
                ORDER BY usage_start_date 
                ROWS BETWEEN 7 PRECEDING and 1 PRECEDING
            ) as avg_prior
        FROM {CATALOG}.{SCHEMA}.billing_summary
        WHERE usage_start_date LIKE '{month_filter}%'
    )
    SELECT resource_id, current_cost, avg_prior, usage_start_date
    FROM stats
    WHERE current_cost > (avg_prior * 1.2)
    ORDER BY usage_start_date DESC
    LIMIT 1
    """
    
    try:
        # Pass the warehouse_id HERE, not in the constructor
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=anomaly_sql
        )
        
        if res.result.data_array:
            row = res.result.data_array[0]
            return {
                "status": "spike_found",
                "resource_id": row[0],
                "details": f"Anomaly: {row[0]} cost ${row[1]:.2f} on {row[3]} (Avg: ${row[2]:.2f})."
            }
            
    except Exception as e:
        return {"status": "error", "details": f"Connection Error: {str(e)}"}

    # Fallback Summary Logic
    summary_sql = f"""
    SELECT cloud_provider, SUM(unblended_cost) 
    FROM {CATALOG}.{SCHEMA}.billing_summary 
    WHERE usage_start_date LIKE '{month_filter}%' 
    GROUP BY 1
    """
    try:
        sum_res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=summary_sql)
        if sum_res.result.data_array:
            breakdown = "\n".join([f"- {r[0]}: ${r[1]:,.2f}" for r in sum_res.result.data_array])
            return {"status": "normal", "details": f"Stable usage for {month_filter}:\n{breakdown}"}
    except:
        pass

    return {"status": "normal", "details": "No anomalies detected."}

def lookup_lakebase_memory(resource_id: str):
    sql = f"SELECT note, approved_by FROM {CATALOG}.{SCHEMA}.lakebase_memory WHERE resource_id = '{resource_id}' LIMIT 1"
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=sql)
        if res.result.data_array:
            return f"Approved by {res.result.data_array[0][1]}: {res.result.data_array[0][0]}"
    except:
        pass
    return None
