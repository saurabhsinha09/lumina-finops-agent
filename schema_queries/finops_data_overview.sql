SELECT
  cloud_provider AS cloud,
  service_name AS service,
  round(SUM(unblended_cost), 2) AS total_cost
FROM
  finops.finops_gold.billing_summary
GROUP BY
  cloud_provider,
  service_name
ORDER BY
  cloud_provider;

SELECT
  *
FROM
  finops.finops_gold.lakebase_memory;