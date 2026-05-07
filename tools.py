import os
from databricks.sdk import WorkspaceClient

# Initialize the Databricks Workspace Client
w = WorkspaceClient()

# Configuration from Environment Variables
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("DATABRICKS_CATALOG", "finops")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "finops_gold")

def parse_date_intent(query_text: str):
    """Maps natural language months to the correct year."""
    query_lower = query_text.lower()
    
    # 2025 Mapping
    months_25 = {
        "october": "2025-10", "oct": "2025-10",
        "november": "2025-11", "nov": "2025-11",
        "december": "2025-12", "dec": "2025-12"
    }
    for name, pattern in months_25.items():
        if name in query_lower: return pattern

    # 2026 Mapping
    months_26 = {
        "january": "2026-01", "jan": "2026-01",
        "february": "2026-02", "feb": "2026-02",
        "march": "2026-03", "mar": "2026-03",
        "april": "2026-04", "apr": "2026-04"
    }
    for name, pattern in months_26.items():
        if name in query_lower: return pattern
    
    return "2026-"

def detect_anomaly(query_text: str):
    """Detects cost spikes and returns a consistent 'details' key to avoid KeyErrors."""
    date_pattern = parse_date_intent(query_text)
    
    anomaly_sql = f"""
    WITH daily_costs AS (
        -- Step 1: Aggregate costs per resource per day first
        SELECT 
            resource_id,
            usage_start_date,
            SUM(unblended_cost) as total_daily_cost
        FROM {CATALOG}.{SCHEMA}.billing_summary
        WHERE usage_start_date LIKE '{date_pattern}%'
        GROUP BY 1, 2
    ),
    stats AS (
        -- Step 2: Calculate 7-day rolling average on aggregated data
        SELECT 
            resource_id,
            usage_start_date,
            total_daily_cost as current_cost,
            AVG(total_daily_cost) OVER (
                PARTITION BY resource_id 
                ORDER BY usage_start_date 
                ROWS BETWEEN 7 PRECEDING and 1 PRECEDING
            ) as avg_prior
        FROM daily_costs
    )
    SELECT resource_id, current_cost, avg_prior, usage_start_date
    FROM stats
    WHERE current_cost > (avg_prior * 1.2)
    AND avg_prior > 0 -- Avoid division by zero/initial noise
    ORDER BY usage_start_date DESC
    """
    
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID, 
            statement=anomaly_sql
        )
        
        if res.result and res.result.data_array and len(res.result.data_array) > 0:
            found_spikes = []
            spike_descriptions = []
            
            for row in res.result.data_array:
                # Create structured data
                spike_info = {
                    "resource_id": row[0],
                    "cost": float(row[1]),
                    "avg": float(row[2]),
                    "date": row[3]
                }
                found_spikes.append(spike_info)
                # Create a string description for the 'details' key
                spike_descriptions.append(f"- {row[0]} cost ${float(row[1]):,.2f} on {row[3]}")

            return {
                "status": "spikes_found",
                "data": found_spikes,
                "details": "The following anomalies were detected:\n" + "\n".join(spike_descriptions[:5])
            }
            
    except Exception as e:
        return {"status": "error", "details": f"SQL Error: {str(e)}"}

    # Fallback Summary
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
            return {
                "status": "normal", 
                "details": f"No spikes found. Summary for {date_pattern}:\n{breakdown}"
            }
    except:
        pass

    return {"status": "normal", "details": f"No data found for {date_pattern}."}

def lookup_lakebase_memory(resource_id: str):
    """Searches Lakebase Memory for approval justifications."""
    memory_sql = f"""
    SELECT note, approved_by FROM {CATALOG}.{SCHEMA}.lakebase_memory 
    WHERE resource_id = '{resource_id}' LIMIT 1
    """
    try:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=memory_sql)
        if res.result and res.result.data_array and len(res.result.data_array) > 0:
            return f"Context found: Approved by {res.result.data_array[0][1]} - '{res.result.data_array[0][0]}'"
    except:
        pass
        
    return "No prior approval notes found in Lakebase memory for this resource."
