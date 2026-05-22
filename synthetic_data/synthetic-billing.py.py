import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 1. Setup Parameters
start_date = datetime(2025, 10, 1)
num_days = 215 
clouds = ['AWS', 'GCP', 'Azure']
environments = ['Prod', 'Staging', 'Dev', 'Shared-Services']
regions = ['us-east-1', 'eu-west-1', 'ap-south-1']

service_details = {
    'AWS': {
        'EC2': ['RunInstances', 'EBS:VolumeUsage', 'DataTransfer-Out'],
        'S3': ['StandardStorage', 'Select-Storage', 'DataTransfer-Out'],
        'RDS': ['db.m5.large', 'StorageUsage'],
        'Lambda': ['Lambda-GB-Second', 'Requests'],
        'Databricks': ['Premium-Worker-DBU', 'Serverless-SQL-DBU']
    },
    'GCP': {
        'Compute Engine': ['N1-Standard-8', 'PersistentDisk'],
        'BigQuery': ['Analysis', 'ActiveStorage'],
        'Cloud Storage': ['MultiRegional', 'Class-A-Operations'],
        'PubSub': ['MessageDelivery']
    },
    'Azure': {
        'Virtual Machines': ['D2s_v3', 'Managed_Disks'],
        'SQL Database': ['vCore-Hours', 'Data-Storage'],
        'Blob Storage': ['Hot-LRS-Storage'],
        'Sentinel': ['Data-Ingestion']
    }
}

billing_data = []
memory_records = []

# 2. Generation Loop
for i in range(num_days):
    current_date = start_date + timedelta(days=i)
    date_str = current_date.strftime("%Y-%m-%d")
    
    for cloud in clouds:
        for env in environments:
            for region in regions:
                for service, usage_types in service_details[cloud].items():
                    for usage_type in usage_types:
                        base_rate = 45.0 if env == 'Prod' else 15.0
                        usage_quantity = np.random.uniform(10, 100)
                        unblended_cost = usage_quantity * (base_rate / 100)
                        
                        resource_id = f"{cloud.lower()}-{service.lower()}-{env.lower()}-001"
                        spike = 0
                        
                        # --- ANOMALY & MEMORY LOGIC ---
                        
                        # A. AWS S3 Spike (Approved)
                        if service == 'S3' and env == 'Prod' and "2025-11-10" <= date_str <= "2025-11-17":
                            spike = np.random.uniform(400, 700)
                            if i == 40: 
                                memory_records.append({
                                    "event_id": "MEM-001", "resource_id": resource_id,
                                    "note": "Tata Elxsi Phase 1 Data Migration - Approved by Archi Board.",
                                    "approved_by": "Senior CSA", "expiry_date": "2025-12-01"
                                })

                        # B. Azure Sentinel Spike (Unapproved / Logging Error)
                        if service == 'Sentinel' and env == 'Dev' and date_str == "2026-01-15":
                            spike = 1100.0 

                        # C. GCP Compute Maintenance (Approved)
                        if service == 'Compute Engine' and env == 'Staging' and date_str == "2026-03-20":
                            spike = 350.0
                            if i == 170:
                                memory_records.append({
                                    "event_id": "MEM-002", "resource_id": resource_id,
                                    "note": "Quarterly Load Testing for modern data platform.",
                                    "approved_by": "Platform Ops", "expiry_date": "2026-03-30"
                                })

                        # NEW D. AWS Databricks Serverless Spike (Approved)
                        if service == 'Databricks' and usage_type == 'Serverless-SQL-DBU' and env == 'Prod' and "2025-12-20" <= date_str <= "2025-12-27":
                            spike = np.random.uniform(300, 500)
                            if i == 80:
                                memory_records.append({
                                    "event_id": "MEM-003", "resource_id": resource_id,
                                    "note": "Year-end financial reporting batch processing.",
                                    "approved_by": "Finance Controller", "expiry_date": "2026-01-05"
                                })
                        
                        # NEW E. Azure SQL DB Scaling (Approved)
                        if cloud == 'Azure' and service == 'SQL Database' and env == 'Prod' and "2026-02-05" <= date_str <= "2026-02-10":
                            spike = np.random.uniform(200, 400)
                            if i == 127:
                                memory_records.append({
                                    "event_id": "MEM-004", "resource_id": resource_id,
                                    "note": "Scaling up for Customer Portal promo campaign.",
                                    "approved_by": "Product Owner", "expiry_date": "2026-02-15"
                                })

                        billing_data.append({
                            "usage_start_date": date_str,
                            "cloud_provider": cloud,
                            "billing_account_id": f"ACT-{np.random.randint(1000,9999)}",
                            "environment": env,
                            "region": region,
                            "service_name": service,
                            "usage_type": usage_type,
                            "usage_quantity": round(usage_quantity, 4),
                            "unblended_cost": round(unblended_cost + spike, 2),
                            "currency": "USD",
                            "resource_id": resource_id,
                            "line_item_description": f"Charge for {service} {usage_type} in {region}",
                            "tag_cost_center": "FIN-OPS" if env == 'Prod' else "ENG-RD"
                        })

# 3. Finalization
df_billing = pd.DataFrame(billing_data)
df_memory = pd.DataFrame(memory_records).drop_duplicates()

# 4. Save to CSV
df_billing.to_csv("enterprise_billing_report_v2.csv", index=False)
df_memory.to_csv("lakebase_memory_v2.csv", index=False)

print(f"Generated {len(df_billing)} billing records.")
print(f"Generated {len(df_memory)} memory records.")
print("\nMemory Records Detail:")
print(df_memory[['event_id', 'resource_id', 'note', 'approved_by']])