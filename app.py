import streamlit as st
import os
import uuid
from graph import finops_agent
from tools import load_chat_history, save_chat_message, persist_decision

st.set_page_config(page_title="Lumina FinOps Agent", layout="wide")

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
    genie_id = os.getenv("GENIE_SPACE_ID", "")
    st.link_button("🚀 Open Genie Deep Dive", f"https://{st.context.headers.get('Host')}/explore/genie/{genie_id}")
    if st.button("Reset Session"):
        st.session_state.messages = []
        st.rerun()

st.title("🤖 Lumina FinOps Assistant")

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
