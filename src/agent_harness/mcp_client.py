"""MCP client — persistent session for tool discovery and execution."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_harness.models import ToolSpec


class McpSession:
    """Manages a persistent MCP server connection for one agent turn.

    Usage::

        with McpSession("mcp_server") as mcp:
            tools = mcp.list_tools()
            result = mcp.call_tool("get_current_time", {})
    """

    def __init__(self, server_module: str) -> None:
        self._server_module = server_module
        self._session: ClientSession | None = None
        self._cleanup: Any = None

    def __enter__(self) -> McpSession:
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._connect())
        return self

    def __exit__(self, *_: Any) -> None:
        if self._cleanup is not None:
            try:
                self._loop.run_until_complete(self._cleanup())
            except Exception:  # noqa: BLE001
                pass
        self._loop.close()

    async def _connect(self) -> None:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", self._server_module]
        )
        ctx = stdio_client(params)
        transport = await ctx.__aenter__()
        read, write = transport
        session_ctx = ClientSession(read, write)
        self._session = await session_ctx.__aenter__()
        await self._session.initialize()

        async def cleanup() -> None:
            await session_ctx.__aexit__(None, None, None)
            await ctx.__aexit__(None, None, None)

        self._cleanup = cleanup

    def list_tools(self) -> list[ToolSpec]:
        """Discover tools from the MCP server."""
        assert self._session is not None
        result = self._loop.run_until_complete(self._session.list_tools())
        tools: list[ToolSpec] = []
        for t in result.tools:
            schema: dict[str, Any] = (
                t.inputSchema  # type: ignore[assignment]
                if hasattr(t, "inputSchema")
                else {"type": "object", "properties": {}}
            )
            tools.append(
                ToolSpec(
                    name=f"mcp__{t.name}",
                    description=t.description or t.name,
                    input_schema=schema,
                    permission="read_only",
                    mcp_server=self._server_module,
                    mcp_tool_name=t.name,
                )
            )
        return tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the connected MCP server."""
        assert self._session is not None
        result = self._loop.run_until_complete(
            self._session.call_tool(tool_name, arguments)
        )
        return "\n".join(
            block.text for block in result.content if hasattr(block, "text")
        )
