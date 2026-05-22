SELECT cloud_provider, SUM(unblended_cost) as total 
            FROM finops.finops_gold.billing_summary 
            WHERE usage_start_date LIKE '2026-03%'
            GROUP BY 1;

SELECT * FROM finops.finops_gold.lakebase_memory 
WHERE resource_id = 'aws-databricks-dev-001';

WITH daily_costs AS (
        -- Step 1: Aggregate costs per resource per day first
        SELECT 
            resource_id,
            usage_start_date,
            SUM(unblended_cost) as total_daily_cost
        FROM finops.finops_gold.billing_summary
        WHERE usage_start_date LIKE '2026-03%'
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