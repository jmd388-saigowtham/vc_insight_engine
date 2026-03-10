"""LangGraph state machine — hub-and-spoke architecture.

The orchestrator node is the central hub that decides which execution
node to run next. All execution nodes return to the orchestrator.
Special actions "wait" and "end" route to END.
"""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from app.agent.nodes.data_understanding import data_understanding_node
from app.agent.nodes.dtype_handling import dtype_handling_node
from app.agent.nodes.eda import eda_node
from app.agent.nodes.explainability import explainability_node
from app.agent.nodes.feature_eng import feature_eng_node
from app.agent.nodes.feature_selection import feature_selection_node
from app.agent.nodes.hypothesis import hypothesis_node
from app.agent.nodes.merge_planning import merge_planning_node
from app.agent.nodes.modeling import modeling_node
from app.agent.nodes.opportunity_analysis import opportunity_analysis_node
from app.agent.nodes.orchestrator import orchestrator_node
from app.agent.nodes.preprocessing import preprocessing_node
from app.agent.nodes.profiling import profiling_node
from app.agent.nodes.recommendation import recommendation_node
from app.agent.nodes.report import report_node
from app.agent.nodes.target_id import target_id_node
from app.agent.nodes.threshold_calibration import threshold_calibration_node
from app.agent.state import AgentState

logger = structlog.get_logger()

# All execution nodes that the orchestrator can dispatch to
EXECUTION_NODES = {
    "profiling": profiling_node,
    "dtype_handling": dtype_handling_node,
    "data_understanding": data_understanding_node,
    "merge_planning": merge_planning_node,
    "opportunity_analysis": opportunity_analysis_node,
    "target_id": target_id_node,
    "feature_selection": feature_selection_node,
    "eda": eda_node,
    "preprocessing": preprocessing_node,
    "hypothesis": hypothesis_node,
    "feature_eng": feature_eng_node,
    "modeling": modeling_node,
    "threshold_calibration": threshold_calibration_node,
    "explainability": explainability_node,
    "recommendation": recommendation_node,
    "report": report_node,
}


def route_next_action(state: AgentState) -> str:
    """Read state['next_action'] and return the target node name.

    Used as the conditional edge function from the orchestrator.
    """
    action = state.get("next_action", "end")

    if action in ("wait", "end"):
        return "end"

    if action in EXECUTION_NODES:
        return action

    logger.warning("route_next_action: unknown action, ending", action=action)
    return "end"


def route_from_execution(state: AgentState) -> str:
    """Route from an execution node back to orchestrator or END.

    When a node sets next_action to 'wait' (pending proposal/approval)
    or 'end', route directly to END without going through the orchestrator
    again. Otherwise, route back to orchestrator for the next decision.
    """
    action = state.get("next_action", "")
    if action in ("wait", "end"):
        return "end"
    return "orchestrator"


def build_graph() -> StateGraph:
    """Build the hub-and-spoke graph with orchestrator as the central hub."""
    graph = StateGraph(AgentState)

    # Add the orchestrator hub
    graph.add_node("orchestrator", orchestrator_node)

    # Add all execution nodes
    for name, fn in EXECUTION_NODES.items():
        graph.add_node(name, fn)

    # Entry point is always the orchestrator
    graph.set_entry_point("orchestrator")

    # Conditional edges from orchestrator to execution nodes (or END)
    route_map = {name: name for name in EXECUTION_NODES}
    route_map["end"] = END
    graph.add_conditional_edges("orchestrator", route_next_action, route_map)

    # Execution nodes route back to orchestrator OR to END (for wait/end)
    exec_route_map = {"orchestrator": "orchestrator", "end": END}
    for name in EXECUTION_NODES:
        graph.add_conditional_edges(name, route_from_execution, exec_route_map)

    return graph


compiled_graph = build_graph().compile()
