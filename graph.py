from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from tools import detect_anomaly, lookup_lakebase_memory
from prompts import AGENT_PERSONA

class AgentState(TypedDict):
    messages: List[str]
    found_anomaly: bool
    resource_list: List[dict]
    final_report: str

def analyze_billing_node(state: AgentState):
    """Node 1: Scan for spikes."""
    prompt = state['messages'][-1]
    res = detect_anomaly(prompt)
    
    if res.get('status') == 'spikes_found':
        return {
            "found_anomaly": True, 
            "resource_list": res['data'], 
            "final_report": f"I have identified the following cost anomalies:\n{res['details']}\n\n"
        }
    return {"found_anomaly": False, "final_report": res['details']}

def check_memory_node(state: AgentState):
    """Node 2: Correlate with Lakebase Memory."""
    memory_results = ["**Lakebase Contextualization:**"]
    for item in state['resource_list']:
        res_id = item['resource_id']
        note = lookup_lakebase_memory(res_id)
        status = f"✅ {note}" if note else "⚠️ No active approval found."
        memory_results.append(f"- `{res_id}`: {status}")
    
    return {"final_report": state['final_report'] + "\n".join(memory_results)}

def responder_node(state: AgentState):
    """Node 3: Apply the AGENT_PERSONA from prompts.py."""
    response = f"{AGENT_PERSONA}\n\n{state['final_report']}"
    if state.get('found_anomaly'):
        response += "\n\nWould you like me to **Snooze** or **Approve** these resources?"
    return {"final_report": response}

# Define Graph
workflow = StateGraph(AgentState)
workflow.add_node("analyze_billing", analyze_billing_node)
workflow.add_node("check_memory", check_memory_node)
workflow.add_node("responder", responder_node)

workflow.set_entry_point("analyze_billing")

workflow.add_conditional_edges(
    "analyze_billing",
    lambda x: "check_memory" if x["found_anomaly"] else "responder"
)

workflow.add_edge("check_memory", "responder")
workflow.add_edge("responder", END)

finops_agent = workflow.compile()
