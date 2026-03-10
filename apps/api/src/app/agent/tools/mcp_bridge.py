"""Bridge to call MCP tool servers as direct Python imports.

MCP servers in this project are plain Python modules with functions
(not HTTP/stdio servers). This bridge dispatches tool calls to the
appropriate server function by name.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Ensure MCP servers and shared schemas are importable
_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)
_packages_root = str(Path(__file__).resolve().parents[6] / "packages")
if _packages_root not in sys.path:
    sys.path.insert(0, _packages_root)

# ---------------------------------------------------------------------------
# Lazy imports — avoids circular / heavy import at module load time
# ---------------------------------------------------------------------------


def _get_data_ingest():
    from data_ingest.server import list_sheets, profile, row_count, sample

    return {
        "profile": profile,
        "sample": sample,
        "row_count": row_count,
        "list_sheets": list_sheets,
    }


def _get_merge_planner():
    from merge_planner.server import detect_keys, execute_merge, generate_merge_code

    return {
        "detect_keys": detect_keys,
        "generate_merge_code": generate_merge_code,
        "execute_merge": execute_merge,
    }


def _get_preprocessing():
    from preprocessing.server import (
        create_interaction_features,
        create_pipeline,
        create_polynomial_features,
        encode_categorical,
        handle_missing,
        scale_numeric,
    )

    return {
        "handle_missing": handle_missing,
        "encode_categorical": encode_categorical,
        "scale_numeric": scale_numeric,
        "create_pipeline": create_pipeline,
        "create_polynomial_features": create_polynomial_features,
        "create_interaction_features": create_interaction_features,
    }


def _get_sandbox_executor():
    from sandbox_executor.server import run, validate_code

    return {"run": run, "validate_code": validate_code}


def _get_eda_plots():
    from eda_plots.server import (
        box_plot,
        correlation_matrix,
        distribution_plot,
        scatter_plot,
        target_analysis,
    )

    return {
        "distribution_plot": distribution_plot,
        "correlation_matrix": correlation_matrix,
        "scatter_plot": scatter_plot,
        "box_plot": box_plot,
        "target_analysis": target_analysis,
    }


def _get_hypothesis():
    from hypothesis.server import generate_hypotheses, run_test, summarize_results

    return {
        "generate_hypotheses": generate_hypotheses,
        "run_test": run_test,
        "summarize_results": summarize_results,
    }


def _get_modeling_explain():
    from modeling_explain.server import (
        calibration_analysis,
        detect_leakage,
        feature_importance,
        generate_model_card,
        learning_curve_analysis,
        predict,
        shap_analysis,
        train,
    )

    return {
        "train": train,
        "shap_analysis": shap_analysis,
        "predict": predict,
        "feature_importance": feature_importance,
        "detect_leakage": detect_leakage,
        "calibration_analysis": calibration_analysis,
        "learning_curve_analysis": learning_curve_analysis,
        "generate_model_card": generate_model_card,
    }


def _get_session_doc():
    from session_doc.server import (
        get_section,
        initialize,
        read,
        upsert,
        upsert_structured,
    )

    return {
        "read": read,
        "upsert": upsert,
        "upsert_structured": upsert_structured,
        "get_section": get_section,
        "initialize": initialize,
    }


def _get_dtype_manager():
    from dtype_manager.server import cast_column, suggest_types, validate_types

    return {
        "cast_column": cast_column,
        "validate_types": validate_types,
        "suggest_types": suggest_types,
    }


def _get_code_registry():
    from code_registry.server import (
        get_history,
        get_latest,
        get_provenance_chain,
        retrieve,
        search_by_intent,
        store,
        update_status,
    )

    return {
        "store": store,
        "retrieve": retrieve,
        "get_latest": get_latest,
        "get_history": get_history,
        "search_by_intent": search_by_intent,
        "get_provenance_chain": get_provenance_chain,
        "update_status": update_status,
    }


# Map of server_name -> lazy loader function
_SERVER_LOADERS: dict[str, Any] = {
    "data_ingest": _get_data_ingest,
    "merge_planner": _get_merge_planner,
    "preprocessing": _get_preprocessing,
    "sandbox_executor": _get_sandbox_executor,
    "eda_plots": _get_eda_plots,
    "hypothesis": _get_hypothesis,
    "modeling_explain": _get_modeling_explain,
    "session_doc": _get_session_doc,
    "dtype_manager": _get_dtype_manager,
    "code_registry": _get_code_registry,
}

# Cache resolved server tool dicts
_SERVER_CACHE: dict[str, dict[str, Any]] = {}


def _resolve_server(server_name: str) -> dict[str, Any]:
    if server_name not in _SERVER_CACHE:
        loader = _SERVER_LOADERS.get(server_name)
        if loader is None:
            raise ValueError(f"Unknown MCP server: {server_name}")
        _SERVER_CACHE[server_name] = loader()
    return _SERVER_CACHE[server_name]


class MCPBridge:
    """Bridge to call MCP tool servers from within LangChain/LangGraph agents.

    Provides a unified interface for the agent to invoke MCP tools
    by dispatching to the appropriate Python module function.
    """

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call an MCP tool by server and function name.

        Args:
            server_name: The MCP server module (e.g. "data_ingest").
            tool_name: The function name within the server (e.g. "profile").
            arguments: Keyword arguments passed to the function.

        Returns:
            The Pydantic model (or other return value) from the tool function.
        """
        logger.info(
            "mcp_bridge.call_tool",
            server=server_name,
            tool=tool_name,
            args=arguments,
        )
        tools = _resolve_server(server_name)
        fn = tools.get(tool_name)
        if fn is None:
            raise ValueError(
                f"Tool '{tool_name}' not found in server '{server_name}'. "
                f"Available: {list(tools.keys())}"
            )
        return fn(**arguments)

    async def list_tools(self) -> list[dict[str, str]]:
        """List all available tools across all servers."""
        result: list[dict[str, str]] = []
        for server_name, loader in _SERVER_LOADERS.items():
            try:
                tools = _resolve_server(server_name)
                for tool_name in tools:
                    result.append({"server": server_name, "tool": tool_name})
            except Exception as exc:
                logger.warning(
                    "mcp_bridge.list_tools: failed to load server",
                    server=server_name,
                    error=str(exc),
                )
        return result
