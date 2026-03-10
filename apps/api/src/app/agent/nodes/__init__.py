import sys
from pathlib import Path

# Ensure MCP servers and shared schemas packages are importable for all node modules.
# This must run before any node imports MCP server functions.
_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)
_packages_root = str(Path(__file__).resolve().parents[6] / "packages")
if _packages_root not in sys.path:
    sys.path.insert(0, _packages_root)

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
from app.agent.nodes.preprocessing import preprocessing_node
from app.agent.nodes.profiling import profiling_node
from app.agent.nodes.recommendation import recommendation_node
from app.agent.nodes.report import report_node
from app.agent.nodes.target_id import target_id_node
from app.agent.nodes.threshold_calibration import threshold_calibration_node

__all__ = [
    "profiling_node",
    "dtype_handling_node",
    "data_understanding_node",
    "merge_planning_node",
    "opportunity_analysis_node",
    "target_id_node",
    "eda_node",
    "preprocessing_node",
    "hypothesis_node",
    "feature_eng_node",
    "feature_selection_node",
    "modeling_node",
    "threshold_calibration_node",
    "explainability_node",
    "recommendation_node",
    "report_node",
]
