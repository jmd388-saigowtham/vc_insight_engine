from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class MCPBridge:
    """Bridge to call MCP tool servers from within LangChain/LangGraph agents.

    Provides a unified interface for the agent to invoke MCP tools
    (e.g., sandbox code execution, data validation) via HTTP.
    """

    def __init__(self, mcp_base_url: str = "http://localhost:9100") -> None:
        self.mcp_base_url = mcp_base_url

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool by name with the given arguments."""
        logger.info("mcp_bridge.call_tool", tool=tool_name, args=arguments)
        return {
            "tool": tool_name,
            "status": "not_yet_connected",
            "message": "MCP bridge is a skeleton; connect to MCP server when available.",
        }

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        logger.info("mcp_bridge.list_tools")
        return []
