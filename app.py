import streamlit as st
import uuid
import pandas as pd
from tools import (
    detect_anomaly, 
    lookup_lakebase_memory, 
    save_chat_message, 
    load_chat_history,
    persist_decision
)

# --- 1. CONFIGURATION & IDENTITY ---
st.set_page_config(page_title="FinOps Agentic Assistant", layout="wide")

# Capture User Identity from Databricks App Headers (SSO)
user_email = st.context.headers.get("X-Forwarded-Email", "demo_user@databricks.com")

# Initialize Session State
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    # Load history from Delta Table to provide multi-session persistence
    st.session_state.messages = load_chat_history(user_email)

# --- 2. SIDEBAR / DASHBOARD ---
with st.sidebar:
    st.title("📊 Cloud Governance")
    st.info(f"Logged in as: **{user_email}**")
    st.markdown("---")
    st.markdown("""
    **App Goals:**
    - Detect Cost Spikes
    - Correlate with Lakebase
    - Persist Governance Decisions
    """)
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# --- 3. MAIN CHAT UI ---
st.title("🤖 FinOps Agentic Assistant")
st.caption("Bridging the Action Gap with intelligent billing analysis and Lakebase memory.")

# Display persistent chat history from Delta
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 4. CHAT LOGIC ---
if prompt := st.chat_input("Analyze spikes in March 2026..."):
    # Display user message and persist to Delta
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    save_chat_message(st.session_state.session_id, user_email, "user", prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing billing data and correlating with Lakebase..."):
            # Step 1: Detect Anomalies via tools.py
            result = detect_anomaly(prompt)
            
            response_text = ""
            
            if result["status"] == "spikes_found":
                response_text = result["details"] + "\n\n---\n"
                
                # Step 2: Contextualize each spike via Lakebase Memory lookup
                for spike in result["data"]:
                    memory = lookup_lakebase_memory(spike['resource_id'])
                    response_text += f"\n**Resource:** `{spike['resource_id']}`\n- **Total Cost:** ${spike['cost']:,.2f}\n- **Context:** {memory}\n"
                    
                response_text += "\nWould you like me to **Snooze** any of these alerts or **Approve** the spend?"
            
            else:
                # Fallback to general summary or normal status
                response_text = result["details"]

            st.markdown(response_text)
            
            # Step 3: PERSISTENCE: Save assistant response to Delta
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            save_chat_message(st.session_state.session_id, user_email, "assistant", response_text)

# --- 5. ACTION LAYER (Closing the Gap) ---
if len(st.session_state.messages) > 0:
    # Use an expander to allow the user to 'Take Action' on the analysis
    with st.expander("🛠️ Take Governance Action"):
        st.write("Persist a decision to Lakebase to stop repetitive alerts.")
        col1, col2 = st.columns(2)
        with col1:
            res_id = st.text_input("Resource ID", placeholder="e.g. aws-databricks-prod-001")
        with col2:
            action = st.selectbox("Action", ["APPROVED", "SNOOZE", "INVESTIGATE"])
        
        reason = st.text_area("Justification/Notes", placeholder="e.g. Planned performance testing for Project Phoenix.")
        
        if st.button("Commit to Lakebase"):
            if res_id and reason:
                msg = persist_decision(res_id, action, reason, user_email)
                st.success(msg)
                # Add the system confirmation to the chat
                st.session_state.messages.append({"role": "assistant", "content": f"**System Update:** {msg}"})
                save_chat_message(st.session_state.session_id, user_email, "assistant", msg)
            else:
                st.warning("Please provide both a Resource ID and a Reason.")
