import streamlit as st
import uuid
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from graph import finops_agent
from tools import load_chat_history, save_chat_message, persist_decision, ask_genie

# ---------------------------------------------------------------------------
# CONFIGURATION & IDENTITY
# ---------------------------------------------------------------------------
st.set_page_config(page_title="FinOps AI Agent", layout="wide")
user_email = st.context.headers.get("X-Forwarded-Email", "user@databricks.com")

st.title("🤖 Lumina FinOps Agent")
st.caption("Powered by Databricks SDK & Genie Spaces")


# ---------------------------------------------------------------------------
# GENERIC GENIE RESPONSE RENDERER
# ---------------------------------------------------------------------------
# ask_genie() now returns a dict:
#   { "text": str, "tables": [{columns, rows, title, description, is_truncated}],
#     "suggested_questions": [str] }
#
# _infer_chart_type() picks the best Plotly chart from data shape + semantics:
#   single value          → metric card
#   1 text + 1 numeric
#     ≤ 8 categories      → donut chart      (e.g. cost by cloud provider)
#     > 8 categories      → horizontal bar
#   date col + numerics   → multi-line chart
#   1 text + 2+ numerics  → grouped bar
#   2+ numeric cols       → scatter
#   fallback              → styled dataframe
# ---------------------------------------------------------------------------

_DATE_HINTS    = {"date", "time", "month", "week", "day", "period", "year", "quarter"}
_COST_HINTS    = {"cost", "spend", "amount", "total", "price", "charge", "fee", "budget"}
_DISTRIB_HINTS = {"provider", "cloud", "vendor", "service", "region", "env",
                  "environment", "type", "category", "group", "team"}
_PALETTE       = px.colors.qualitative.Set2


def _col_is_date(col_name: str, series: pd.Series) -> bool:
    if any(h in col_name.lower() for h in _DATE_HINTS):
        return True
    try:
        pd.to_datetime(series.dropna().iloc[:3])
        return True
    except Exception:
        return False


def _col_is_cost(col_name: str) -> bool:
    return any(h in col_name.lower() for h in _COST_HINTS)


def _infer_chart_type(df: pd.DataFrame, title: str, description: str) -> str:
    num_cols  = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    text_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    hint      = (title + " " + description).lower()

    # Single scalar
    if len(df) == 1 and len(df.columns) == 1 and len(num_cols) == 1:
        return "metric"

    # Time series
    date_cols = [c for c in text_cols if _col_is_date(c, df[c])]
    if date_cols and num_cols:
        return "line"

    # 1 text + 1 numeric
    if len(text_cols) == 1 and len(num_cols) == 1:
        n_unique = df[text_cols[0]].nunique()
        if any(k in hint for k in ["distribution", "breakdown", "share", "proportion",
                                    "percentage", "by provider", "by cloud",
                                    "by service", "by region"]):
            return "donut" if n_unique <= 8 else "hbar"
        if n_unique > 8 or len(df) > 10:
            return "hbar"
        if any(h in text_cols[0].lower() for h in _DISTRIB_HINTS) or _col_is_cost(num_cols[0]):
            return "donut"
        return "donut" if n_unique <= 8 else "hbar"

    # 1 text + 2+ numerics
    if len(text_cols) == 1 and len(num_cols) >= 2:
        return "grouped_bar"

    # All numeric
    if len(text_cols) == 0 and len(num_cols) >= 2:
        return "scatter"

    return "table"


def _render_genie_table(table: dict):
    """Render one Genie query result as the most appropriate chart + data expander."""
    columns     = table.get("columns", [])
    rows        = table.get("rows", [])
    title       = table.get("title", "")
    description = table.get("description", "")

    if not columns or not rows:
        return

    df = pd.DataFrame(rows, columns=columns)
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    num_cols  = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    text_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    date_cols = [c for c in text_cols if _col_is_date(c, df[c])]

    chart_type  = _infer_chart_type(df, title, description)
    chart_title = title or (
        f"{', '.join(num_cols)} by {', '.join(text_cols)}" if text_cols else ", ".join(num_cols)
    )
    layout = dict(
        title_text=chart_title, title_x=0.0, height=400,
        margin=dict(t=50, b=20, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    chart_rendered = False

    # ── Metric card ──────────────────────────────────────────────────────
    if chart_type == "metric":
        val      = df.iloc[0, 0]
        col_name = df.columns[0]
        display  = f"${val:,.2f}" if _col_is_cost(col_name) else f"{val:,.2f}"
        st.metric(label=chart_title or col_name, value=display)
        chart_rendered = True

    # ── Donut ────────────────────────────────────────────────────────────
    elif chart_type == "donut":
        label_col = text_cols[0]
        value_col = num_cols[0]
        hover     = "$%{value:,.2f}" if _col_is_cost(value_col) else "%{value:,.2f}"
        fig = go.Figure(go.Pie(
            labels=df[label_col], values=df[value_col],
            hole=0.45, marker_colors=_PALETTE,
            textinfo="label+percent",
            hovertemplate=f"%{{label}}<br>{hover}<br>%{{percent}}<extra></extra>",
        ))
        fig.update_layout(legend_title_text=label_col, **layout)
        st.plotly_chart(fig, use_container_width=True)
        chart_rendered = True

    # ── Horizontal bar (many categories / ranked) ─────────────────────
    elif chart_type == "hbar":
        label_col = text_cols[0]
        value_col = num_cols[0]
        df_sorted = df.sort_values(value_col, ascending=True).tail(20)
        fig = px.bar(
            df_sorted, x=value_col, y=label_col, orientation="h",
            title=chart_title, color=value_col, color_continuous_scale="Blues",
            labels={value_col: f"${value_col}" if _col_is_cost(value_col) else value_col,
                    label_col: ""},
        )
        fig.update_layout(coloraxis_showscale=False, **layout)
        st.plotly_chart(fig, use_container_width=True)
        chart_rendered = True

    # ── Line chart (time series) ──────────────────────────────────────
    elif chart_type == "line":
        x_col = date_cols[0] if date_cols else text_cols[0]
        try:
            df[x_col] = pd.to_datetime(df[x_col])
            df = df.sort_values(x_col)
        except Exception:
            pass
        fig = px.line(df, x=x_col, y=num_cols, title=chart_title,
                      markers=True, color_discrete_sequence=_PALETTE)
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
        chart_rendered = True

    # ── Grouped bar (one label, multiple metrics) ─────────────────────
    elif chart_type == "grouped_bar":
        fig = px.bar(df, x=text_cols[0], y=num_cols, barmode="group",
                     title=chart_title, color_discrete_sequence=_PALETTE)
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
        chart_rendered = True

    # ── Scatter (two numeric dimensions) ─────────────────────────────
    elif chart_type == "scatter":
        fig = px.scatter(df, x=num_cols[0], y=num_cols[1],
                         color=text_cols[0] if text_cols else None,
                         title=chart_title, color_discrete_sequence=_PALETTE)
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
        chart_rendered = True

    # ── Raw data expander (always shown below chart) ──────────────────
    with st.expander("📋 View data" if chart_rendered else "📋 Data",
                     expanded=not chart_rendered):
        fmt = {c: "${:,.2f}" for c in num_cols if _col_is_cost(c)}
        st.dataframe(df.style.format(fmt) if fmt else df, use_container_width=True)
        if table.get("is_truncated"):
            st.caption("⚠️ Result set truncated — showing first rows only.")


def _render_genie_response(genie_result: dict):
    """
    Top-level renderer for a full ask_genie() response dict.
    Handles prose text, data tables/charts, and suggested follow-up questions.
    """
    # 1. Prose answer
    text = genie_result.get("text", "")
    if text:
        st.markdown(text)

    # 2. Charts / tables
    for tbl in genie_result.get("tables", []):
        _render_genie_table(tbl)

    # 3. Suggested follow-up question buttons (SDK >= 0.45)
    suggestions = genie_result.get("suggested_questions", [])
    if suggestions:
        st.markdown("**💡 You might also ask:**")
        cols = st.columns(min(len(suggestions), 3))
        for i, q in enumerate(suggestions):
            if cols[i % 3].button(q, key=f"sugg_{hash(q)}"):
                st.session_state["genie_followup"] = q
                st.rerun()


# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------
tab_governance, tab_explore = st.tabs(["📊 Anomaly Governance", "🧞 Ask Genie Anything"])

# ── TAB 1: Anomaly Governance (LangGraph agent) ───────────────────────────
with tab_governance:
    if "messages" not in st.session_state:
        st.session_state.messages = []  #clear previous chat history on page reload

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("Explain the spikes for March 2026", key="gov_input"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing and coordinating with Genie SDK..."):
                result = finops_agent.invoke({"messages": [prompt]})
                ans = result["final_report"]
                st.markdown(ans)
                save_chat_message(str(uuid.uuid4()), user_email, "assistant", ans)
                st.session_state.messages.append({"role": "assistant", "content": ans})

# ── TAB 2: Ask Genie Anything ─────────────────────────────────────────────
with tab_explore:
    st.subheader("Direct Data Conversation")
    st.write("Converse directly with the Genie Space — charts and tables rendered automatically.")

    if "genie_chat"    not in st.session_state: st.session_state.genie_chat    = []
    if "genie_tables"  not in st.session_state: st.session_state.genie_tables  = {}
    if "genie_followup" not in st.session_state: st.session_state.genie_followup = None

    # Replay previous turns (text from history + charts from stored table data)
    for idx, g in enumerate(st.session_state.genie_chat):
        with st.chat_message(g["role"]):
            st.markdown(g["content"])
            if g["role"] == "assistant" and idx in st.session_state.genie_tables:
                for tbl in st.session_state.genie_tables[idx]:
                    _render_genie_table(tbl)

    # Accept typed input or a follow-up button press
    followup  = st.session_state.pop("genie_followup", None)
    g_prompt  = followup or st.chat_input(
        "What is the distribution of costs by cloud provider?", key="genie_input"
    )

    if g_prompt:
        st.session_state.genie_chat.append({"role": "user", "content": g_prompt})
        with st.chat_message("user"):
            st.markdown(g_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Genie is thinking..."):
                genie_result = ask_genie(g_prompt)
                _render_genie_response(genie_result)

                # Persist text to chat history; store table data for chart replay
                turn_idx = len(st.session_state.genie_chat)
                st.session_state.genie_chat.append({
                    "role":    "assistant",
                    "content": genie_result.get("text", ""),
                })
                if genie_result.get("tables"):
                    st.session_state.genie_tables[turn_idx] = genie_result["tables"]

# ---------------------------------------------------------------------------
# LAKEBASE GOVERNANCE ACTION
# ---------------------------------------------------------------------------
st.divider()
with st.expander("🛠️ Persist Decision to Lakebase"):
    c1, c2 = st.columns(2)
    res_id = c1.text_input("Resource ID")
    action = c2.selectbox("Decision", ["APPROVE", "SNOOZE"])
    note   = st.text_area("Justification")
    if st.button("Commit Decision"):
        status = persist_decision(res_id, action, note, user_email)
        st.success(status)