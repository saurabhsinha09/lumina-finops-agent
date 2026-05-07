import os
import pandas as pd
from databricks.sdk import WorkspaceClient

# Initialize the Databricks Workspace Client
# Explicitly pull the credentials provided by the App environment
w = WorkspaceClient(
    host=os.getenv("DATABRICKS_HOST"),
    client_id=os.getenv("DATABRICKS_CLIENT_ID"),
    client_secret=os.getenv("DATABRICKS_CLIENT_SECRET"),
    warehouse_id=os.getenv("DATABRICKS_WAREHOUSE_ID")
)

# Load Environment Variables set in the Databricks App UI
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_gold")

def detect_anomaly(query_text: str):
    """
    1. Runs a Window Function to find spikes > 20% vs 7-day average.
    2. If no spike is found, returns a high-level cost summary for the month.
    """
    
    # --- STEP 1: MATHEMATICAL SPIKE DETECTION ---
    anomaly_sql = f"""
    WITH stats AS (
        SELECT 
            resource_id,
            usage_start_date,
            unblended_cost as current_cost,
            AVG(unblended_cost) OVER (
                PARTITION BY resource_id 
                ORDER BY usage_start_date 
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) as avg_prior
        FROM {CATALOG}.{SCHEMA}.billing_summary
    )
    SELECT resource_id, current_cost, avg_prior, usage_start_date
    FROM stats
    WHERE current_cost > (avg_prior * 1.2) -- 20% Threshold
    AND usage_start_date >= '2025-10-01'
    ORDER BY usage_start_date DESC
    LIMIT 1
    """
    
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=anomaly_sql
        )
        
        if res.result.data_array:
            row = res.result.data_array[0]
            return {
                "status": "spike_found",
                "resource_id": row[0],
                "details": f"Anomaly Detected: {row[0]} cost was ${row[1]:.2f} on {row[3]}, which is significantly higher than the 7-day average of ${row[2]:.2f}."
            }
            
    except Exception as e:
        return {"status": "error", "details": f"SQL Error: {str(e)}"}

    # --- STEP 2: SUMMARY FALLBACK (If no spike found) ---
    # We extract the month if mentioned, otherwise default to latest data
    month_filter = "2026-03" if "March" in query_text else "2026-01"
    
    summary_sql = f"""
    SELECT cloud_provider, SUM(unblended_cost) as total_cost
    FROM {CATALOG}.{SCHEMA}.billing_summary
    WHERE usage_start_date LIKE '{month_filter}%'
    GROUP BY 1
    ORDER BY 2 DESC
    """
    
    try:
        summary_res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=summary_sql
        )
        
        if summary_res.result.data_array:
            lines = [f"- {r[0]}: ${r[1]:,.2f}" for r in summary_res.result.data_array]
            breakdown = "\n".join(lines)
            return {
                "status": "normal",
                "details": f"No significant spikes found for this period. Here is the cost breakdown for {month_filter}:\n\n{breakdown}"
            }
    except:
        pass

    return {"status": "normal", "details": "Billing is stable and no anomalies were detected."}

def lookup_lakebase_memory(resource_id: str):
    """
    Queries the Lakebase Memory table for approval notes tied to a specific resource.
    """
    memory_sql = f"""
    SELECT note, approved_by 
    FROM {CATALOG}.{SCHEMA}.lakebase_memory 
    WHERE resource_id = '{resource_id}'
    LIMIT 1
    """
    
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=memory_sql
        )
        
        if res.result.data_array:
            note = res.result.data_array[0][0]
            approver = res.result.data_array[0][1]
            return f"Approved by {approver}: {note}"
            
    except Exception as e:
        print(f"Memory lookup error: {e}")
        
    return None
