"""Pre-demo sanity check — prints local setup without calling Azure."""

from __future__ import annotations

from pathlib import Path

from agent_harness.mcp_client import McpSession
from agent_harness.models import Config
from agent_harness.prompt import load_skills
from agent_harness.tools import load_tools

from .api import make_client


def run_preflight(config: Config, use_mock: bool) -> None:
    """Print a simple local setup report before a demo run."""
    tools = load_tools()
    skills = load_skills()

    print("🔎 Preflight")
    print(f"   cwd: {Path.cwd()}")
    print(f"   provider: {'mock' if use_mock else 'azure'}")
    print(f"   tools: {len(tools)} built-in")
    print(f"   skills: {len(skills)} loaded")
    print(f"   permission_mode: {config.permission_mode}")

    if use_mock:
        print("   ✅ mock mode does not require Azure connectivity")
    else:
        make_client(config)
        print(
            "   ✅ Azure client settings loaded"
            f" for {config.azure_deployment} (connectivity not verified)"
        )

    if config.mcp_server:
        with McpSession(config.mcp_server) as mcp:
            mcp_tools = mcp.list_tools()
            print(
                f"   ✅ MCP server '{config.mcp_server}' exposed {len(mcp_tools)} tools"
            )
