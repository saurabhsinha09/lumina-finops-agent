CREATE TABLE IF NOT EXISTS finops.finops_gold.billing_summary
AS SELECT * FROM read_files('/Volumes/finops/finops_gold/landing_zone/enterprise_billing_report_v2.csv');

-- Add a comment for Genie to understand the table
COMMENT ON TABLE finops.finops_gold.billing_summary IS 'Contains multi-cloud billing data with resource IDs and unblended costs.';

CREATE TABLE IF NOT EXISTS finops.finops_gold.lakebase_memory
AS SELECT * FROM read_files('/Volumes/finops/finops_gold/landing_zone/lakebase_memory_v2.csv');

COMMENT ON TABLE finops.finops_gold.lakebase_memory IS 'Persistent memory storing approved cost anomalies and architectural notes.';

CREATE TABLE IF NOT EXISTS finops.finops_gold.chat_history (
    session_id STRING,
    user_email STRING,
    role STRING, -- 'user' or 'assistant'
    content STRING,
    timestamp TIMESTAMP
);