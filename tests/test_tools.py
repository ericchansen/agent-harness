"""Tool loading and permission tests."""

from __future__ import annotations

import json

from agent_harness.models import Config, ToolSpec
from agent_harness.tools import check_permission, load_tools


def test_load_tools_reads_json(tmp_path) -> None:
    """Tool specs should load directly from tools.json."""
    tools_path = tmp_path / "tools.json"
    tools_path.write_text(
        json.dumps(
            [
                {
                    "name": "read_file",
                    "description": "Read a file.",
                    "input_schema": {"type": "object", "properties": {}},
                    "permission": "read_only",
                }
            ]
        ),
        encoding="utf-8",
    )

    tools = load_tools(str(tools_path))

    assert len(tools) == 1
    assert tools[0].name == "read_file"
    assert tools[0].permission == "read_only"


def test_check_permission_blocks_outside_workspace(tmp_path, monkeypatch) -> None:
    """Non-dangerous file tools should not escape the workspace."""
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent / "outside.txt"
    tool = ToolSpec(
        name="read_file", description="Read a file.", permission="read_only"
    )
    config = Config(
        azure_endpoint="",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="read_only",
    )

    denied = check_permission(tool, config, {"path": str(outside_path)})

    assert denied is not None
    assert "outside workspace" in denied


def test_check_permission_allows_dangerous_mode_outside_workspace(
    tmp_path, monkeypatch
) -> None:
    """Dangerous mode keeps the original full-access semantics."""
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent / "outside.txt"
    tool = ToolSpec(
        name="read_file", description="Read a file.", permission="read_only"
    )
    config = Config(
        azure_endpoint="",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="dangerous",
    )

    denied = check_permission(tool, config, {"path": str(outside_path)})

    assert denied is None


def test_check_permission_still_enforces_permission_levels() -> None:
    """Workspace rules should not weaken the original permission checks."""
    tool = ToolSpec(
        name="write_file",
        description="Write a file.",
        permission="workspace_write",
    )
    config = Config(
        azure_endpoint="",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="read_only",
    )

    denied = check_permission(tool, config, {"path": "demo.txt"})

    assert denied is not None
    assert "requires 'workspace_write'" in denied
