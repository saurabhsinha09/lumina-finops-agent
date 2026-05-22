from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from tools import detect_anomaly, lookup_lakebase_memory, ask_genie, parse_date_intent
from prompts import AGENT_PERSONA


class AgentState(TypedDict):
    messages:      List[str]
    found_anomaly: bool
    resource_list: List[dict]
    target_date:   str          # FIX 1: was missing — caused KeyError in genie_investigation_node
    final_report:  str
    genie_insights: str


def analyze_billing_node(state: AgentState):
    """Node 1: Scan for spikes and capture the date period from the user's prompt."""
    prompt = state['messages'][-1]
    res    = detect_anomaly(prompt)

    # FIX 2: derive target_date from the same prompt so genie_investigation_node
    # has the period without it being hardcoded anywhere
    target_date = parse_date_intent(prompt)   # e.g. "2025-10" for "Oct 2025"

    if res.get('status') == 'spikes_found':
        return {
            "found_anomaly": True,
            "resource_list": res['data'],
            "target_date":   target_date,
            "final_report":  f"I have identified the following cost anomalies:\n{res['details']}\n\n",
        }
    return {
        "found_anomaly": False,
        "target_date":   target_date,
        "final_report":  res['details'],
    }


def genie_investigation_node(state: AgentState):
    """Node 2: Ask Genie to explain root cause for the flagged resources."""
    resources = ", ".join([r['resource_id'] for r in state['resource_list']])
    query     = (
        f"Investigate the cost spikes for {resources} during {state['target_date']}. "
        f"Identify the specific jobs or users responsible."
    )

    # FIX 3: ask_genie() returns a dict {text, tables, suggested_questions}.
    # Extract only the prose text for the governance report narrative.
    result  = ask_genie(query)
    insight = result.get("text", "") if isinstance(result, dict) else str(result)

    return {"genie_insights": f"### 💡 Genie Root Cause Analysis\n{insight}\n\n"}


def check_memory_node(state: AgentState):
    """Node 3: Correlate each spike with Lakebase governance memory."""
    memory_results = ["**Lakebase Contextualization:**"]
    for item in state['resource_list']:
        res_id = item['resource_id']
        note   = lookup_lakebase_memory(res_id)
        status = f"✅ {note}" if note else "⚠️ No active approval found."
        memory_results.append(f"- `{res_id}`: {status}")

    return {"final_report": state['final_report'] + "\n".join(memory_results)}


def responder_node(state: AgentState):
    """Node 4: Apply the AGENT_PERSONA and assemble the final report."""
    # Include Genie insights in the report if they were produced
    genie_section = state.get("genie_insights", "")
    report        = state['final_report']
    if genie_section:
        report = genie_section + report

    response = f"{AGENT_PERSONA}\n\n{report}"
    if state.get('found_anomaly'):
        response += "\n\nWould you like me to **Snooze** or **Approve** these resources?"
    return {"final_report": response}


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------
workflow = StateGraph(AgentState)
workflow.add_node("analyze_billing",   analyze_billing_node)
workflow.add_node("genie_investigation", genie_investigation_node)
workflow.add_node("check_memory",      check_memory_node)
workflow.add_node("responder",         responder_node)

workflow.set_entry_point("analyze_billing")

workflow.add_conditional_edges(
    "analyze_billing",
    lambda x: "genie_investigation" if x["found_anomaly"] else "responder",
)
workflow.add_edge("genie_investigation", "check_memory")
workflow.add_edge("check_memory",        "responder")
workflow.add_edge("responder",           END)

finops_agent = workflow.compile()