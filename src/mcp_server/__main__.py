"""Minimal MCP server — exposes tools over stdio using the MCP protocol.

Run standalone:  python mcp_server.py
The agent starts this as a subprocess and discovers its tools automatically.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-tools")


@mcp.tool()
def get_current_time() -> str:
    """Return the current date and time. Use when the user asks what time it is."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@mcp.tool()
def word_count(text: str) -> str:
    """Count words, lines, and characters in the given text."""
    lines = text.strip().splitlines()
    words = text.split()
    return f"{len(words)} words, {len(lines)} lines, {len(text)} characters"


def main() -> None:
    """Entry point for ``python -m mcp_server``."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
