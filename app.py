import streamlit as st
import os
import uuid
from graph import finops_agent
from tools import load_chat_history, save_chat_message, persist_decision

st.set_page_config(page_title="Lumina FinOps Agent", layout="wide")

# CONFIGURATION & IDENTITY ---
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID")
workspace_url = os.getenv("WORKSPACE_URL")
org_id = os.getenv("ORG_ID")

# Identity & Session
user_email = st.context.headers.get("X-Forwarded-Email", "developer@company.com")
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = load_chat_history(user_email)

# Sidebar with Genie Link (Pillar: Genie)
with st.sidebar:
    st.title("🛡️ Governance Center")
    st.info(f"User: {user_email}")
    full_genie_url = f"{workspace_url}/genie/rooms/{GENIE_SPACE_ID}?o={org_id}"
    st.link_button("🚀 Open Genie Deep Dive", full_genie_url)
    st.divider()
    if st.button("Reset Session"):
        st.session_state.messages = []
        st.rerun()

st.title("🤖 Lumina FinOps Assistant")
st.caption("AI-Powered Cloud Cost Governance & Anomaly Detection")

# Display Chat History
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Chat Input (Pillar: Agent Bricks)
if prompt := st.chat_input("Analyze spikes in March..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    save_chat_message(st.session_state.session_id, user_email, "user", prompt)

    with st.chat_message("assistant"):
        # Invoke the LangGraph Agentic Loop
        with st.spinner("Agent Bricks working..."):
            result = finops_agent.invoke({"messages": [prompt]})
            ans = result["final_report"]
            st.markdown(ans)
            
            st.session_state.messages.append({"role": "assistant", "content": ans})
            save_chat_message(st.session_state.session_id, user_email, "assistant", ans)

# Action Layer (Pillar: Lakebase Persistence)
with st.expander("🛠️ Take Action"):
    c1, c2 = st.columns(2)
    rid = c1.text_input("Resource ID")
    act = c2.selectbox("Action", ["SNOOZE", "APPROVE"])
    note = st.text_area("Justification")
    if st.button("Persist to Lakebase"):
        res = persist_decision(rid, act, note, user_email)
        st.success(res)
