from typing import TypedDict, Annotated, List
import operator
from langgraph.graph import StateGraph, END
from tools import detect_anomaly, lookup_lakebase_memory

class AgentState(TypedDict):
    messages: Annotated[List[str], operator.add]
    found_anomaly: bool
    resource_id: str
    final_output: str

def analyze_billing_node(state: AgentState):
    user_input = state['messages'][-1]
    res = detect_anomaly(user_input)
    if res['status'] == 'spike_found':
        return {"found_anomaly": True, "resource_id": res['resource_id']}
    return {"found_anomaly": False, "final_output": res['details']}

def check_memory_node(state: AgentState):
    note = lookup_lakebase_memory(state['resource_id'])
    if note:
        output = f"I found a spike for **{state['resource_id']}**, but Lakebase memory confirms: *'{note}'*. No action required."
    else:
        output = f"🚨 **ALARM**: Unexplained spike for **{state['resource_id']}**. No approval found in Lakebase memory."
    return {"final_output": output}

def route_logic(state: AgentState):
    return "check_memory" if state.get("found_anomaly") else END

workflow = StateGraph(AgentState)
workflow.add_node("analyze_billing", analyze_billing_node)
workflow.add_node("check_memory", check_memory_node)

workflow.set_entry_point("analyze_billing")
workflow.add_conditional_edges("analyze_billing", route_logic, {"check_memory": "check_memory", END: END})
workflow.add_edge("check_memory", END)

finops_agent = workflow.compile()
