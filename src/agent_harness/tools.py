"""Tool loading, permission checking, and built-in handlers."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_harness.models import Config, ToolSpec

PERMISSION_LEVELS: dict[str, int] = {
    "read_only": 0,
    "workspace_write": 1,
    "dangerous": 2,
}


def load_tools(path: str = "tools.json") -> list[ToolSpec]:
    """Read tool definitions from a JSON file."""
    raw: list[dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        ToolSpec(
            name=t["name"],
            description=t["description"],
            input_schema=t.get("input_schema", {}),
            permission=t.get("permission", "read_only"),
        )
        for t in raw
    ]


def check_permission(tool: ToolSpec, config: Config) -> str | None:
    """Return an error string if the tool is denied, otherwise ``None``."""
    required = PERMISSION_LEVELS.get(tool.permission, 0)
    current = PERMISSION_LEVELS.get(config.permission_mode, 1)
    if required > current:
        return (
            f"Permission denied: '{tool.name}' requires "
            f"'{tool.permission}', current mode is '{config.permission_mode}'"
        )
    return None


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Look up a built-in handler by tool name and execute it."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Error: no built-in handler for '{name}'"
    return handler(arguments)


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------


def _handle_read_file(args: dict[str, Any]) -> str:
    """Read a text file and return its contents (truncated at 10k chars)."""
    path = args.get("path", "")
    if not os.path.isfile(path):
        return f"Error: file not found: {path}"
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if len(text) > 10_000:
        return text[:10_000] + "\n...(truncated)"
    return text


def _handle_list_files(args: dict[str, Any]) -> str:
    """List directory entries, one per line."""
    path = args.get("path", ".")
    entries = sorted(os.listdir(path))
    return "\n".join(entries[:100])


def _handle_run_command(args: dict[str, Any]) -> str:
    """Run a shell command and return combined stdout + stderr."""
    cmd = args.get("command", "")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (result.stdout + result.stderr).strip()
        return out[:5_000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out (30s)"


def _handle_write_file(args: dict[str, Any]) -> str:
    """Write content to a file, creating parent directories as needed."""
    path = args.get("path", "")
    content = args.get("content", "")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "read_file": _handle_read_file,
    "list_files": _handle_list_files,
    "run_command": _handle_run_command,
    "write_file": _handle_write_file,
}
