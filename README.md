# 🤖 Lumina FinOps Agent
### *Bridging the Action Gap in Multi-Cloud Cost Governance*

> **Databricks — Building Intelligent Apps with Data + AI Challenge**
> Built by **Saurabh Sinha** · Licensed under MIT

---

## 📌 Table of Contents

- [Problem Statement](#-problem-statement)
- [Solution Overview](#-solution-overview)
- [Live Demo](#-live-demo)
- [Architecture](#-architecture)
- [The Four Competition Pillars](#-the-four-competition-pillars)
- [Project Structure](#-project-structure)
- [Key Features](#-key-features)
- [Data Model](#-data-model)
- [Setup & Deployment](#-setup--deployment)
- [Environment Variables](#-environment-variables)
- [How It Works](#-how-it-works)
- [Tech Stack](#-tech-stack)
- [License](#-license)

---

## 🚨 Problem Statement

Despite the availability of cloud billing dashboards, organizations suffer from two critical failures:

**1. Dashboard Fatigue**
Finance and engineering teams are drowning in cost alerts with no context — a spike on a dashboard tells you *what* happened but never *why*.

**2. The Action Gap**
Traditional FinOps tools are purely reactive. By the time a human investigates the root cause, correlates it with an ongoing project, and documents their decision, the same alert fires again next week.

Three specific pain points this project addresses:

| Pain Point | Impact |
|---|---|
| Multi-cloud billing data (AWS, GCP, Azure) is fragmented | Finance teams can't get a unified view |
| Cost spikes have no business context attached | Engineering wastes hours on already-approved spend |
| Governance decisions live in email threads or Slack | The same question is answered repeatedly |

---

## 💡 Solution Overview

**Lumina FinOps Agent** is an intelligent co-pilot built on the Databricks Data Intelligence Platform. It transforms static billing logs into a conversational agent that:

- 🔍 **Detects** cost anomalies automatically using a 7-day rolling average baseline
- 🧠 **Remembers** context — "This spike is approved for Project Phoenix" — eliminating repetitive alerts
- 💬 **Explains** root cause in plain English by correlating billing data with Genie's SQL intelligence
- ✅ **Acts** — users can Approve or Snooze alerts directly in the chat, with decisions persisted to Lakebase
- 📊 **Visualises** any Genie query result as an auto-selected chart (donut, line, bar, scatter) matching the Genie Space UI

> **Key differentiator:** Most FinOps tools stop at detection. Lumina closes the loop by persisting governance decisions back into the data platform, so the agent learns from every human choice.

---

## 🎥 Live Demo

> 📽️ **[Watch the full 5-minute demo on Loom](https://www.loom.com/share/8441d629441e4b6084c2daa7e0636c00)**

| Tab | What it does |
|---|---|
| 📊 **Anomaly Governance** | LangGraph agent scans for spikes → correlates with Lakebase memory → presents a contextualised report |
| 🧞 **Ask Genie Anything** | Direct SDK conversation with the Genie Space — any question, any chart type, rendered automatically |
| 🛠️ **Persist Decision** | Commit an APPROVE or SNOOZE decision to Lakebase with a justification note |

**Example queries to try:**
```
Anomaly Governance tab:
  "Show me cost spikes for March 2026"
  "Any anomalies in November 2025?"

Ask Genie tab:
  "What is the distribution of unblended costs by cloud provider?"
  "Show me the top 10 most expensive resources in Q1 2026"
  "How did AWS EC2 costs trend over December 2025?"
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATABRICKS APPS (Streamlit)                   │
│  ┌─────────────────────────┐  ┌──────────────────────────────┐  │
│  │   Anomaly Governance    │  │     Ask Genie Anything       │  │
│  │   (LangGraph Agent)     │  │   (Direct SDK Conversation)  │  │
│  └────────────┬────────────┘  └──────────────┬───────────────┘  │
└───────────────┼──────────────────────────────┼──────────────────┘
                │                              │
                ▼                              ▼
┌──────────────────────────┐   ┌──────────────────────────────────┐
│     LANGGRAPH AGENT      │   │         GENIE SPACE SDK          │
│                          │   │                                  │
│  analyze_billing_node    │   │  start_conversation_and_wait()   │
│         ↓                │   │  _fetch_attachment_result()      │
│  genie_investigation     │   │  → SDK-version-safe getattr()    │
│         ↓                │   │    fallbacks for all field       │
│  check_memory_node       │   │    access (≤0.44 + ≥0.45)       │
│         ↓                │   │                                  │
│  responder_node          │   │  Returns structured dict:        │
│                          │   │  {text, tables, suggestions}     │
└────────────┬─────────────┘   │  → _render_genie_response()     │
             │                 │  → auto-chart via Plotly         │
             ▼                 └──────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│                      UNITY CATALOG                               │
│  ┌──────────────────┐  ┌────────────────┐  ┌─────────────────┐ │
│  │ billing_summary  │  │ lakebase_memory│  │  chat_history   │ │
│  │ (Delta Table)    │  │ (Lakebase /    │  │  (Delta Table)  │ │
│  │                  │  │  Postgres)     │  │                 │ │
│  │ Multi-cloud      │  │ Governance     │  │ Multi-session   │ │
│  │ billing records  │  │ decisions +    │  │ conversation    │ │
│  │ AWS/GCP/Azure    │  │ expiry dates   │  │ persistence     │ │
│  └──────────────────┘  └────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏆 The Four Competition Pillars

### Pillar 1 — 💬 Natural Language Interaction (Genie)
The **Ask Genie Anything** tab connects directly to a Genie Space via the Databricks SDK (`start_conversation_and_wait`). The integration goes beyond plain text — it fetches the actual SQL result rows via `_fetch_attachment_result()` and passes them to `_render_genie_response()`, which auto-selects a Plotly chart matching the Genie Space UI. The result for "distribution of costs by cloud provider" is a live donut chart, identical to what Genie renders natively.

### Pillar 2 — 🤖 Workflow Automation (Agent Bricks / LangGraph)
The **Anomaly Governance** tab runs a four-node LangGraph agent:
1. `analyze_billing_node` — runs SQL anomaly detection with a 7-day rolling average
2. `genie_investigation_node` — asks Genie to identify the responsible jobs/users
3. `check_memory_node` — correlates each spike against active Lakebase approvals
4. `responder_node` — applies the Senior FinOps Architect persona from `prompts.py`

### Pillar 3 — 💾 State Persistence (Lakebase)
Two persistence layers work together:
- **`lakebase_memory`** — governance decisions (APPROVE/SNOOZE) with expiry dates, written via the governance action panel and read by the agent on every run
- **`chat_history`** — full conversation history per user, loaded on app start for true multi-session continuity

### Pillar 4 — 🖥️ Seamless UX (Databricks Apps)
Built with Streamlit on Databricks Apps with SSO identity injection via the `X-Forwarded-Email` header. The generic chart renderer auto-selects the best visualisation for any Genie response shape — donut for distributions, line for time series, grouped bar for comparisons — with no hardcoded query logic.

---

## 📁 Project Structure

```
lumina-finops-agent/
│
├── app.py                  # Streamlit UI — tabs, chat, generic chart renderer, action layer
├── graph.py                # LangGraph agent — 4-node agentic workflow
├── tools.py                # All SDK integrations — Genie, anomaly detection, Lakebase
├── prompts.py              # Agent persona definition
├── app.yaml                # Databricks Apps deployment config + env vars
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

### Module responsibilities

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI, `_render_genie_response()` → `_render_genie_table()` → `_infer_chart_type()` pipeline, session state + chart replay |
| `graph.py` | LangGraph `StateGraph` definition, node functions, conditional routing |
| `tools.py` | `ask_genie()` returning `{text, tables, suggested_questions}`, `detect_anomaly()`, `lookup_lakebase_memory()`, `persist_decision()`, chat history |
| `prompts.py` | `AGENT_PERSONA` — the FinOps Architect system prompt applied in `responder_node` |
| `app.yaml` | Databricks Apps command, environment variable injection, user scope authorisation |

---

## ✨ Key Features

### Generic Genie Chart Renderer
`ask_genie()` returns a structured dict `{text, tables, suggested_questions}` — never a plain string. `_render_genie_response()` in `app.py` unpacks this and passes each table to `_infer_chart_type()`, which picks the best Plotly chart purely from data shape and semantic signals in column names and query titles — no hardcoded query logic anywhere:

| Data shape | Chart rendered |
|---|---|
| 1 column, 1 row | Metric card |
| 1 text + 1 numeric, ≤8 categories | Donut chart |
| 1 text + 1 numeric, >8 categories | Horizontal bar |
| Date column + numeric(s) | Multi-line chart |
| 1 text + 2+ numerics | Grouped bar chart |
| 2+ numeric columns | Scatter plot |
| Anything else | Styled dataframe |

Every chart is followed by a collapsible **View data** expander showing the raw rows, and a truncation warning when Genie caps the result set.

### SDK Version Compatibility
The Genie integration uses `getattr()` with `try/except` guards throughout — no bare attribute access on any SDK object — handling two SDK generations transparently:

| | SDK ≤ 0.44 (Databricks App venv) | SDK ≥ 0.45 |
|---|---|---|
| Message ID | `message.id` | `message.message_id` |
| Attachment ID | `attachment.query.id` | `attachment.attachment_id` |
| Fetch method | `get_message_query_result_by_attachment()` | `get_message_attachment_query_result()` |
| Suggested questions | not available | `attachment.suggested_questions` |

### 7-Day Rolling Anomaly Detection
```sql
AVG(daily_cost) OVER (
    PARTITION BY resource_id
    ORDER BY usage_start_date
    ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
) AS avg_7d
-- Flags any day where cost > avg_7d * 1.2
```

### Governance Decision Lifecycle
```
User sees spike → Checks Lakebase memory
    ├── Memory found  → ✅ "Approved by [user] until [date]" — no action needed
    └── No memory     → ⚠️ Alert flagged as urgent business risk
                           → User commits APPROVE or SNOOZE via action panel
                               → Persisted to lakebase_memory with expiry date
                                   → Future agent runs will find the note
```

---

## 🗃️ Data Model

### `finops_gold.billing_summary` (Delta Table)
| Column | Type | Description |
|---|---|---|
| `usage_start_date` | STRING | YYYY-MM-DD format |
| `cloud_provider` | STRING | AWS / GCP / Azure |
| `resource_id` | STRING | e.g. `aws-s3-prod-001` |
| `service_name` | STRING | EC2, S3, BigQuery, etc. |
| `unblended_cost` | DOUBLE | USD cost for this line item |
| `environment` | STRING | Prod / Staging / Dev |
| `region` | STRING | us-east-1, eu-west-1, etc. |

### `finops_gold.lakebase_memory` (Lakebase / Postgres)
| Column | Type | Description |
|---|---|---|
| `event_id` | STRING | Short UUID (8 chars) |
| `resource_id` | STRING | Foreign key to billing_summary |
| `note` | STRING | `ACTION: justification text` |
| `approved_by` | STRING | User email from SSO |
| `expiry_date` | DATE | SNOOZE = +30 days, APPROVE = +365 days |

### `finops_gold.chat_history` (Delta Table)
| Column | Type | Description |
|---|---|---|
| `session_id` | STRING | UUID per browser session |
| `user_email` | STRING | From SSO header |
| `role` | STRING | user / assistant |
| `content` | STRING | Message text |
| `timestamp` | TIMESTAMP | `CURRENT_TIMESTAMP()` |

---

## 🚀 Setup & Deployment

### Prerequisites
- Databricks workspace with Unity Catalog enabled
- A Genie Space configured against the `finops_gold` schema
- A SQL Warehouse (the ID goes in `app.yaml`)
- Databricks Apps enabled in your workspace

### 1. Create the Delta tables

```sql
-- Billing summary (load from synthetic-billing.py or your real data)
CREATE TABLE IF NOT EXISTS finops.finops_gold.billing_summary (
    usage_start_date   STRING,
    cloud_provider     STRING,
    billing_account_id STRING,
    environment        STRING,
    region             STRING,
    service_name       STRING,
    usage_type         STRING,
    usage_quantity     DOUBLE,
    unblended_cost     DOUBLE,
    currency           STRING,
    resource_id        STRING,
    line_item_description STRING,
    tag_cost_center    STRING
);

-- Lakebase governance memory
CREATE TABLE IF NOT EXISTS finops.finops_gold.lakebase_memory (
    event_id    STRING,
    resource_id STRING,
    note        STRING,
    approved_by STRING,
    expiry_date DATE
);

-- Chat history
CREATE TABLE IF NOT EXISTS finops.finops_gold.chat_history (
    session_id STRING,
    user_email STRING,
    role       STRING,
    content    STRING,
    timestamp  TIMESTAMP
);
```

### 2. Generate synthetic data (optional)

```bash
python synthetic-billing.py
# Produces enterprise_billing_report_v2.csv and lakebase_memory_v2.csv
# Load into Unity Catalog via the Databricks UI or COPY INTO
```

### 3. Deploy to Databricks Apps

```bash
# From the Databricks UI:
# Apps → Create App → Upload source files → app.yaml is auto-detected

# Or via CLI:
databricks apps deploy lumina-finops-agent \
  --source-code-path ./lumina-finops-agent
```

### 4. Clear Python cache before each redeploy

Databricks Apps caches `.pyc` bytecode — always clear it before uploading updated files or the old code will continue running:

```bash
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
```

---

## ⚙️ Environment Variables

Configured in `app.yaml` — no `.env` file needed for Databricks Apps deployment.

| Variable | Description | Example |
|---|---|---|
| `DATABRICKS_WAREHOUSE_ID` | SQL Warehouse to run all queries | `bb23f7651eabe681` |
| `DATABRICKS_CATALOG` | Unity Catalog name | `finops` |
| `DATABRICKS_SCHEMA` | Schema containing all tables | `finops_gold` |
| `GENIE_SPACE_ID` | Genie Space ID for NL queries | `01f149e347...` |

Authentication is handled automatically by the Databricks Apps runtime via the `user_scopes: [all-apis, sql]` setting in `app.yaml` — no API keys or tokens needed.

---

## 🔄 How It Works

### Anomaly Governance flow (step by step)

```
User types: "Show me cost spikes for March 2026"
    │
    ▼
analyze_billing_node
    └── detect_anomaly("March 2026")
        └── SQL: 7-day rolling avg, flags cost > avg * 1.2
        └── Returns: [{resource_id, cost, avg, date}, ...]
    │
    ▼ (if spikes found)
genie_investigation_node
    └── ask_genie("Investigate spikes for aws-s3-prod-001 during 2026-03...")
        └── Genie runs SQL, returns {text, tables, suggested_questions}
        └── graph.py uses .get("text") for the prose insight
    │
    ▼
check_memory_node
    └── For each spike: lookup_lakebase_memory(resource_id)
        ├── Found  → "✅ Approved by alice@co.com until 2026-04-15: Migration work"
        └── Not found → "⚠️ No active approval found"
    │
    ▼
responder_node
    └── Applies AGENT_PERSONA, assembles final markdown report
    └── Appends: "Would you like me to Snooze or Approve these resources?"
```

### Ask Genie flow (step by step)

```
User types: "What is the distribution of costs by cloud provider?"
    │
    ▼
ask_genie(prompt)  [tools.py]
    └── w.genie.start_conversation_and_wait(space_id, content)
        └── Returns GenieMessage
    └── _resolve_message_id(message)     ← getattr fallback, SDK-version-safe
    └── For each query attachment:
        └── _resolve_attachment_id()     ← getattr fallback, SDK-version-safe
        └── _fetch_attachment_result()   ← tries new method name, falls back to old
            └── Returns StatementResponse → columns + rows
    └── Returns: {
            "text":   "AWS has the highest cost at $423,664...",
            "tables": [{"columns": ["cloud_provider","total_unblended_cost"],
                        "rows": [["AWS","423664.75"], ...]}],
            "suggested_questions": []
        }
    │
    ▼
_render_genie_response(genie_result)  [app.py]
    ├── st.markdown(text)                      ← prose answer
    ├── _render_genie_table(table)             ← for each result table
    │     └── _infer_chart_type(df, title, description)
    │           └── 1 text col + 1 numeric + "distribution" hint
    │               → DONUT CHART rendered with Plotly
    │     └── st.expander("📋 View data")      ← raw rows always accessible
    └── suggested question buttons             ← clickable follow-ups (if any)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Streamlit on Databricks Apps |
| **Agent orchestration** | LangGraph (`StateGraph`) |
| **Data platform** | Databricks Unity Catalog, Delta Lake |
| **NL data interface** | Databricks Genie Spaces (SDK) |
| **Persistence** | Lakebase (managed Postgres), Delta Tables |
| **Visualisation** | Plotly Express + Plotly Graph Objects |
| **Identity** | Databricks SSO (`X-Forwarded-Email` header) |
| **Language** | Python 3.11 |

---

## 📄 License

MIT License — Copyright (c) 2026 Saurabh Sinha. See [LICENSE](LICENSE) for full text.
