import streamlit as st
import uuid
import os
from graph import finops_agent
from tools import load_chat_history, save_chat_message, persist_decision, ask_genie

import databricks.sdk
print(f"SDK VERSION: {databricks.sdk.__version__}")

# Identity & Configuration
user_email = st.context.headers.get("X-Forwarded-Email", "user@databricks.com")

st.set_page_config(page_title="FinOps AI Agent", layout="wide")

# --- UI Layout ---
st.title("🤖 Lumina FinOps Agent")
st.caption("Powered by Databricks SDK & Genie Spaces")

# Tabs for separate interaction styles
tab_governance, tab_explore = st.tabs(["📊 Anomaly Governance", "🧞 Ask Genie Anything"])

with tab_governance:
    # Historical logic for the main agent
    if "messages" not in st.session_state:
        st.session_state.messages = load_chat_history(user_email)

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("Explain the spikes for March 2026", key="gov_input"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Analyzing and coordinating with Genie SDK..."):
                result = finops_agent.invoke({"messages": [prompt]})
                ans = result["final_report"]
                st.markdown(ans)
                save_chat_message(str(uuid.uuid4()), user_email, "assistant", ans)
                st.session_state.messages.append({"role": "assistant", "content": ans})

with tab_explore:
    st.subheader("Direct Data Conversation")
    st.write("Converse directly with the Genie Space via SDK for ad-hoc summaries.")

    if "genie_chat" not in st.session_state:
        st.session_state.genie_chat = []

    for g in st.session_state.genie_chat:
        with st.chat_message(g["role"]):
            st.markdown(g["content"])

    if g_prompt := st.chat_input("How many EC2 instances spiked in Jan?", key="genie_input"):
        st.session_state.genie_chat.append({"role": "user", "content": g_prompt})
        with st.chat_message("user"): st.markdown(g_prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Genie is generating a summary..."):
                # Requirement B: Prompt sent to Genie Space via SDK
                response = ask_genie(g_prompt) 
                st.markdown(response)
                st.session_state.genie_chat.append({"role": "assistant", "content": response})

# --- Bottom Action Layer (Pillar: Lakebase) ---
st.divider()
with st.expander("🛠️ Persist Decision to Lakebase"):
    c1, c2 = st.columns(2)
    res_id = c1.text_input("Resource ID")
    action = c2.selectbox("Decision", ["APPROVE", "SNOOZE"])
    note = st.text_area("Justification")
    if st.button("Commit Decision"):
        status = persist_decision(res_id, action, note, user_email)
        st.success(status)
