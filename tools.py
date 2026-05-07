import os
import re
from databricks.sdk import WorkspaceClient

# Initialize the Databricks Workspace Client
# It automatically uses the App's Service Principal credentials from the environment
w = WorkspaceClient()

# Load Configuration from Environment Variables set in the Databricks App UI
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_gold")

def parse_date_intent(query_text: str):
    """
    Maps natural language months to the correct year based on the dataset:
    - Oct to Dec -> 2025
    - Jan to Apr -> 2026
    """
    query_lower = query_text.lower()
    
    # 2025 Mapping (Dataset Start)
    months_25 = {
        "october": "2025-10", "oct": "2025-10",
        "november": "2025-11", "nov": "2025-11",
        "december": "2025-12", "dec": "2025-12"
    }
    for name, pattern in months_25.items():
        if name in query_lower:
            return pattern

    # 2026 Mapping
    months_26 = {
        "january": "2026-01", "jan": "2026-01",
        "february": "2026-02", "feb": "2026-02",
        "march": "2026-03", "mar": "2026-03",
        "april": "2026-04", "apr": "2026-04"
    }
    for name, pattern in months_26.items():
        if name in query_lower:
            return pattern
    
    # Default fallback: Search all of 2026
    return "2026-"

def detect_anomaly(query_text: str):
    """
    1. Identifies the date range from user query.
    2. Runs a Window Function to find spikes > 20% vs 7-day average.
    3. If no spike, returns a high-level cost summary.
    """
    date_pattern = parse_date_intent(query_text)
    
    # SQL to find spikes using a 7-day rolling average baseline
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
        WHERE usage_start_date LIKE '{date_pattern}%'
    )
    SELECT resource_id, current_cost, avg_prior, usage_start_date
    FROM stats
    WHERE current_cost > (avg_prior * 1.2)
    ORDER BY usage_start_date DESC
    LIMIT 1
    """
    
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=anomaly_sql
        )
        
        # Safety Check: Ensure result exists and has rows
        if res.result and res.result.data_array and len(res.result.data_array) > 0:
            row = res.result.data_array[0]
            # Convert values to float for safe formatting
            curr_val = float(row[1])
            avg_val = float(row[2])
            return {
                "status": "spike_found",
                "resource_id": row[0],
                "details": f"Anomaly Detected: {row[0]} cost was ${curr_val:,.2f} on {row[3]} (Baseline: ${avg_val:,.2f})."
            }
            
    except Exception as e:
        return {"status": "error", "details": f"SQL Error: {str(e)}"}

    # FALLBACK: If no spikes, provide a summary of the requested period
    summary_sql = f"""
    SELECT cloud_provider, SUM(unblended_cost) as total_cost
    FROM {CATALOG}.{SCHEMA}.billing_summary
    WHERE usage_start_date LIKE '{date_pattern}%'
    GROUP BY 1
    ORDER BY 2 DESC
    """
    
    try:
        sum_res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=summary_sql
        )
        
        if sum_res.result and sum_res.result.data_array:
            # Format results into a readable list
            lines = [f"- {r[0]}: ${float(r[1]):,.2f}" for r in sum_res.result.data_array]
            breakdown = "\n".join(lines)
            return {
                "status": "normal",
                "details": f"No significant spikes found. Cost breakdown for {date_pattern}:\n\n{breakdown}"
            }
    except Exception as e:
        return {"status": "error", "details": f"Summary Error: {str(e)}"}

    return {"status": "normal", "details": f"No billing data found for the period '{date_pattern}'."}

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
        
        if res.result and res.result.data_array and len(res.result.data_array) > 0:
            note = res.result.data_array[0][0]
            approver = res.result.data_array[0][1]
            return f"Context found in Lakebase: Approved by {approver} - '{note}'"
            
    except Exception as e:
        print(f"Memory lookup error: {e}")
        
    return "No prior approval notes found in Lakebase memory for this resource."
