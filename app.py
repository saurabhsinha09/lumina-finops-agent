import streamlit as st
import pandas as pd
import plotly.express as px
from graph import finops_agent

st.set_page_config(page_title="Agentic FinOps Assistant", layout="wide")

# Custom CSS for the reasoning trace look
st.markdown("""
    <style>
    .reasoning-trace {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 10px;
        border-left: 5px solid #ff4b4b;
    }
    </style>
""", unsafe_allow_html=True)

st.title("💰 Agentic FinOps Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Chat Logic
if prompt := st.chat_input("Ex: Analyze the spike on Jan 15th"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # This is where the Reasoning Trace is rendered
        with st.status("🔍 Agent Reasoning Trace", expanded=True) as status:
            st.write("Step 1: Querying Unity Catalog for 7-day rolling averages...")
            # Trigger LangGraph
            result = finops_agent.invoke({"messages": [prompt]})
            
            # Dynamically update the status based on graph path
            if result.get("found_anomaly"):
                st.write(f"✅ Anomaly Detected: {result['resource_id']}")
                st.write("Step 2: Searching Lakebase Memory for existing approvals...")
            else:
                st.write("✅ No anomalies found in billing data.")
            
            status.update(label="Analysis Complete!", state="complete", expanded=False)

        # Final Agent Response
        st.markdown(result['final_output'])

        # Contextual Visualization
        if result.get("found_anomaly"):
            st.info(f"**Action Recommended:** Investigate {result['resource_id']}")
