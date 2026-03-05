from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from app.agent.nodes.eda import eda_node
from app.agent.nodes.explainability import explainability_node
from app.agent.nodes.feature_eng import feature_eng_node
from app.agent.nodes.hypothesis import hypothesis_node
from app.agent.nodes.merge_planning import merge_planning_node
from app.agent.nodes.modeling import modeling_node
from app.agent.nodes.preprocessing import preprocessing_node
from app.agent.nodes.profiling import profiling_node
from app.agent.nodes.recommendation import recommendation_node
from app.agent.nodes.report import report_node
from app.agent.nodes.target_id import target_id_node
from app.agent.state import AgentState

logger = structlog.get_logger()


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("profiling", profiling_node)
    graph.add_node("merge_planning", merge_planning_node)
    graph.add_node("target_id", target_id_node)
    graph.add_node("eda", eda_node)
    graph.add_node("preprocessing", preprocessing_node)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_node("feature_eng", feature_eng_node)
    graph.add_node("modeling", modeling_node)
    graph.add_node("explainability", explainability_node)
    graph.add_node("recommendation", recommendation_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("profiling")
    graph.add_edge("profiling", "merge_planning")
    graph.add_edge("merge_planning", "target_id")
    graph.add_edge("target_id", "eda")
    graph.add_edge("eda", "preprocessing")
    graph.add_edge("preprocessing", "hypothesis")
    graph.add_edge("hypothesis", "feature_eng")
    graph.add_edge("feature_eng", "modeling")
    graph.add_edge("modeling", "explainability")
    graph.add_edge("explainability", "recommendation")
    graph.add_edge("recommendation", "report")
    graph.add_edge("report", END)

    return graph


compiled_graph = build_graph().compile()
