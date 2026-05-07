import os
import re
from databricks.sdk import WorkspaceClient
from datetime import datetime

w = WorkspaceClient()

# Configuration from Environment Variables
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "main")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_challenge")

def parse_date_intent(query_text: str):
    """
    Maps month names to the correct year based on your dataset:
    Oct-Dec -> 2025
    Jan-Dec -> 2026
    """
    query_lower = query_text.lower()
    
    # 2025 Mapping
    if any(m in query_lower for m in ["october", "oct", "november", "nov", "december", "dec"]):
        months_25 = {"oct": "2025-10", "nov": "2025-11", "dec": "2025-12"}
        for k, v in months_25.items():
            if k in query_lower: return v
        return "2025-" # Fallback for "late 2025" queries

    # 2026 Mapping
    months_26 = {
        "january": "2026-01", "jan": "2026-01",
        "february": "2026-02", "feb": "2026-02",
        "march": "2026-03", "mar": "2026-03",
        "april": "2026-04", "apr": "2026-04"
    }
    for k, v in months_26.items():
        if k in query_lower: return v
    
    # Default to the most recent year in your data
    return "2026-"

def detect_anomaly(query_text: str):
    date_pattern = parse_date_intent(query_text)
    
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
    )
    SELECT resource_id, current_cost, avg_prior, usage_start_date
    FROM stats
    WHERE usage_start_date LIKE '{date_pattern}%'
    AND current_cost > (avg_prior * 1.2)
    ORDER BY usage_start_date DESC
    LIMIT 1
    """
    
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=anomaly_sql
        )
        
        if res.result and res.result.data_array and len(res.result.data_array) > 0:
            row = res.result.data_array[0]
            return {
                "status": "spike_found",
                "resource_id": row[0],
                "details": f"Anomaly: {row[0]} cost ${row[1]:.2f} on {row[3]}."
            }
            
    except Exception as e:
        return {"status": "error", "details": f"SQL Error: {str(e)}"}

    # Dynamic Summary Fallback
    summary_sql = f"""
    SELECT cloud_provider, SUM(unblended_cost) 
    FROM {CATALOG}.{SCHEMA}.billing_summary 
    WHERE usage_start_date LIKE '{date_pattern}%' 
    GROUP BY 1 ORDER BY 2 DESC
    """
    try:
        sum_res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=summary_sql)
        if sum_res.result and sum_res.result.data_array:
            breakdown = "\n".join([f"- {r[0]}: ${float(r[1]):,.2f}" for r in sum_res.result.data_array])
            return {"status": "normal", "details": f"Billing summary for {date_pattern}:\n{breakdown}"}
    except:
        pass

    return {"status": "normal", "details": f"No data found for the period matching '{date_pattern}'."}

def lookup_lakebase_memory(resource_id: str):
    sql = f"SELECT note, approved_by FROM {CATALOG}.{SCHEMA}.lakebase_memory WHERE resource_id = '{resource_id}' LIMIT 1"
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=sql)
        if res.result and res.result.data_array:
            return f"Approved by {res.result.data_array[0][1]}: {res.result.data_array[0][0]}"
    except:
        pass
    return None
