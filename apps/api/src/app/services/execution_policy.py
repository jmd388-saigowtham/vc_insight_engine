"""Central execution policy service for the platform-wide control flow.

Every agent node delegates to this service for the canonical execution
pattern: tool discovery → code reuse → code generation → approval →
execution → provenance tracking.

Safe auto-execute (no approval needed):
  - Reading files, profiling, schema inference, read-only descriptive stats,
    reading session memory.

Approval REQUIRED:
  - Any data mutation, dtype changes, merges, target derivation, preprocessing,
    feature engineering, hypothesis execution, model training, threshold
    locking, any file-writing code, any sandboxed execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from app.agent.state import AgentState

logger = structlog.get_logger()

# Actions that can auto-execute without user approval
# Uses (server, tool) tuples matching node_helpers._READ_ONLY_TOOLS
SAFE_ACTIONS: frozenset[tuple[str, str]] = frozenset({
    ("data_ingest", "profile"),
    ("data_ingest", "sample"),
    ("data_ingest", "row_count"),
    ("data_ingest", "list_sheets"),
    ("session_doc", "read"),
    ("session_doc", "get_section"),
    ("eda_plots", "distribution_plot"),
    ("eda_plots", "correlation_matrix"),
    ("eda_plots", "scatter_plot"),
    ("eda_plots", "box_plot"),
    ("eda_plots", "target_analysis"),
    ("hypothesis", "generate_hypotheses"),
    ("hypothesis", "run_test"),
    ("hypothesis", "summarize_results"),
    ("modeling_explain", "shap_analysis"),
    ("modeling_explain", "feature_importance"),
    ("modeling_explain", "predict"),
    ("modeling_explain", "detect_leakage"),
    ("modeling_explain", "calibration_analysis"),
    ("modeling_explain", "learning_curve_analysis"),
    ("modeling_explain", "generate_model_card"),
    ("dtype_manager", "suggest_types"),
    ("dtype_manager", "validate_types"),
    ("code_registry", "retrieve"),
    ("code_registry", "get_latest"),
    ("merge_planner", "detect_keys"),
})


@dataclass
class ExecutionResult:
    """Result of executing an action through the policy."""
    success: bool
    action_taken: str  # "tool_auto", "tool_proposed", "code_reuse", "code_generated"
    result: Any = None
    proposal_needed: bool = False
    proposal_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    trace_events: list[dict[str, Any]] = field(default_factory=list)


class ExecutionPolicyService:
    """Shared service implementing the platform-wide execution policy.

    Every node calls this service instead of implementing the policy inline.
    This prevents duplicated policy logic across nodes.

    Currently available for any agent node that wants centralized policy
    enforcement (tool discovery → code reuse → approval → provenance).
    Most nodes use inline approval_helpers; this service provides a
    higher-level alternative for nodes that prefer it.
    """

    def __init__(self):
        self._bridge = None

    def _get_bridge(self):
        if self._bridge is None:
            from app.agent.tools.mcp_bridge import MCPBridge
            self._bridge = MCPBridge()
        return self._bridge

    async def discover_tool(
        self, intent: str, server_hint: str | None = None
    ) -> dict[str, Any] | None:
        """Discover an MCP tool that matches the given intent.

        Returns tool info dict if found, None otherwise.
        """
        bridge = self._get_bridge()
        tools = await bridge.list_tools()

        if server_hint:
            matching = [
                t for t in tools
                if t["server"] == server_hint and intent in t["tool"]
            ]
            if matching:
                return matching[0]

        matching = [t for t in tools if intent in t["tool"]]
        if matching:
            return matching[0]

        return None

    async def search_reusable_code(
        self,
        session_id: str,
        intent: str,
    ) -> dict[str, Any] | None:
        """Search the code registry for reusable code matching the intent."""
        try:
            bridge = self._get_bridge()
            result = await bridge.call_tool(
                "code_registry", "retrieve", {"session_id": session_id, "step": intent}
            )
            if result and hasattr(result, "code") and result.code:
                return {
                    "code": result.code,
                    "step": intent,
                    "source": "code_registry",
                }
        except Exception as e:
            logger.debug("Code registry search failed", error=str(e))

        return None

    def is_safe_action(self, server: str, tool: str) -> bool:
        """Check if a tool action is safe to auto-execute."""
        return (server, tool) in SAFE_ACTIONS

    async def execute_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute an MCP tool directly."""
        bridge = self._get_bridge()
        return await bridge.call_tool(server_name, tool_name, arguments)

    async def execute_and_record(
        self,
        state: AgentState,
        step: str,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        description: str = "",
    ) -> ExecutionResult:
        """Execute a tool with policy enforcement and provenance recording.

        If the tool is safe (read-only), executes directly.
        If the tool requires approval, returns proposal data.
        Records provenance for all executions.
        """
        session_id = str(state.get("session_id", ""))
        trace_events: list[dict[str, Any]] = []

        trace_events.append({
            "event_type": "TOOL_DISCOVERY",
            "step": step,
            "payload": {
                "intent": description or f"{server}.{tool}",
                "tool_found": f"{server}.{tool}",
            },
        })

        if self.is_safe_action(server, tool):
            # Auto-execute
            try:
                result = await self.execute_tool(server, tool, arguments)
                # Record provenance
                await self.record_provenance(
                    session_id,
                    step,
                    code=f"# Auto-executed: {server}.{tool}\n# {description}",
                )
                # Update session memory
                await self.update_session_memory(
                    session_id,
                    step.replace("_", " ").title(),
                    f"Executed {server}.{tool}: {description}",
                )
                return ExecutionResult(
                    success=True,
                    action_taken="tool_auto",
                    result=result,
                    trace_events=trace_events,
                )
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    action_taken="tool_auto",
                    error=str(e),
                    trace_events=trace_events,
                )
        else:
            # Needs approval
            return ExecutionResult(
                success=True,
                action_taken="tool_proposed",
                proposal_needed=True,
                proposal_data={
                    "tool_server": server,
                    "tool_name": tool,
                    "arguments": arguments,
                    "description": description,
                },
                trace_events=trace_events,
            )

    async def execute_with_policy(
        self,
        state: AgentState,
        step: str,
        intent: str,
        *,
        mcp_tool_hint: str | None = None,
        code_generator: Any = None,
    ) -> ExecutionResult:
        """Execute an action following the platform-wide execution policy.

        1. Discover MCP tool for intent
        2. If tool found and action is read-only → auto-execute
        3. If tool found and action is mutating → propose tool call for approval
        4. If no tool → search code_registry for reusable code
        5. If reusable code found → propose reuse with explanation
        6. If nothing reusable → signal that code generation is needed

        Args:
            state: Current agent state.
            step: Pipeline step name.
            intent: What the action is trying to accomplish.
            mcp_tool_hint: Optional server name hint for tool discovery.
            code_generator: Optional callable for generating code.

        Returns:
            ExecutionResult with action taken and any proposal data.
        """
        session_id = str(state.get("session_id", ""))
        trace_events: list[dict[str, Any]] = []

        # 1. Discover MCP tool
        tool_info = await self.discover_tool(intent, mcp_tool_hint)

        if tool_info:
            trace_events.append({
                "event_type": "TOOL_DISCOVERY",
                "step": step,
                "payload": {
                    "intent": intent,
                    "tool_found": f"{tool_info['server']}.{tool_info['tool']}",
                },
            })

            # 2. Safe auto-execute
            if self.is_safe_action(tool_info["server"], tool_info["tool"]):
                return ExecutionResult(
                    success=True,
                    action_taken="tool_auto",
                    trace_events=trace_events,
                )

            # 3. Mutating action — needs approval
            return ExecutionResult(
                success=True,
                action_taken="tool_proposed",
                proposal_needed=True,
                proposal_data={
                    "tool_server": tool_info["server"],
                    "tool_name": tool_info["tool"],
                    "intent": intent,
                },
                trace_events=trace_events,
            )

        trace_events.append({
            "event_type": "TOOL_DISCOVERY",
            "step": step,
            "payload": {
                "intent": intent,
                "tool_found": None,
                "message": "No MCP tool found, searching code registry",
            },
        })

        # 4. Search code registry
        reusable = await self.search_reusable_code(session_id, intent)
        if reusable:
            trace_events.append({
                "event_type": "CODE_REUSE",
                "step": step,
                "payload": {
                    "source": "code_registry",
                    "intent": intent,
                },
            })
            return ExecutionResult(
                success=True,
                action_taken="code_reuse",
                result=reusable,
                proposal_needed=True,
                proposal_data={
                    "code": reusable["code"],
                    "source": "code_registry",
                    "intent": intent,
                },
                trace_events=trace_events,
            )

        # 5. Need code generation
        return ExecutionResult(
            success=True,
            action_taken="code_generation_needed",
            proposal_needed=True,
            proposal_data={"intent": intent},
            trace_events=trace_events,
        )

    async def record_provenance(
        self,
        session_id: str,
        step: str,
        code: str,
        proposal_id: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        artifacts: list[str] | None = None,
    ) -> None:
        """Record code execution provenance in the code registry and session doc."""
        try:
            bridge = self._get_bridge()
            await bridge.call_tool(
                "code_registry",
                "store",
                {
                    "session_id": session_id,
                    "step": step,
                    "code": code,
                    "metadata": {
                        "proposal_id": proposal_id,
                        "stdout": stdout,
                        "stderr": stderr,
                        "artifacts": artifacts or [],
                    },
                },
            )
        except Exception as e:
            logger.warning("Failed to record provenance", error=str(e))

    async def update_session_memory(
        self,
        session_id: str,
        section: str,
        content: str,
    ) -> None:
        """Update a section in the session markdown memory."""
        try:
            bridge = self._get_bridge()
            await bridge.call_tool(
                "session_doc",
                "upsert",
                {"session_id": session_id, "section": section, "content": content},
            )
        except Exception as e:
            logger.warning("Failed to update session memory", error=str(e))

    async def read_session_memory(self, session_id: str) -> str:
        """Read the full session markdown memory."""
        try:
            bridge = self._get_bridge()
            result = await bridge.call_tool(
                "session_doc", "read", {"session_id": session_id}
            )
            if result and hasattr(result, "document"):
                return result.document
        except Exception as e:
            logger.debug("Failed to read session memory", error=str(e))
        return ""
