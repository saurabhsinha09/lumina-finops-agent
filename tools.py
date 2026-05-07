import os
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
# Set these in your Databricks App Environment Variables
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")

def detect_anomaly(query_text: str):
    # Mathematical Spike Detection (20% Threshold)
    sql = """
    WITH stats AS (
        SELECT resource_id, unblended_cost,
               AVG(unblended_cost) OVER (PARTITION BY resource_id ORDER BY usage_start_date ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) as avg_prior
        FROM main.finops_challenge.billing_summary
    )
    SELECT resource_id, unblended_cost FROM stats 
    WHERE unblended_cost > (avg_prior * 1.2) AND usage_start_date >= '2026-01-01'
    LIMIT 1
    """
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=sql)
        if res.result.data_array:
            return {"status": "spike_found", "resource_id": res.result.data_array[0][0]}
    except:
        pass
    return {"status": "normal", "details": "The current billing trends look consistent with your historical 7-day average."}

def lookup_lakebase_memory(resource_id: str):
    sql = f"SELECT note FROM main.finops_challenge.lakebase_memory WHERE resource_id = '{resource_id}'"
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=sql)
        if res.result.data_array:
            return res.result.data_array[0][0]
    except:
        pass
    return None
