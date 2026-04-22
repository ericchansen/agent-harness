"""Data models used across the agent harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Config:
    """Runtime configuration — loaded from ``config.json`` each turn."""

    azure_endpoint: str
    azure_deployment: str
    azure_api_version: str
    permission_mode: str
    max_iterations: int = 10
    show_system_prompt: bool = False
    show_tool_calls: bool = True
    mcp_server: str | None = None


@dataclass
class ToolSpec:
    """One tool visible to the model — loaded from ``tools.json`` or MCP."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    permission: str = "read_only"
    # Set for tools discovered via MCP
    mcp_server: str | None = None
    mcp_tool_name: str | None = None
