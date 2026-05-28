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


# ---------------------------------------------------------------------------
# Sensitive-file protection
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = Config(
    azure_endpoint="",
    azure_deployment="gpt-4o",
    azure_api_version="2025-01-01-preview",
    permission_mode="workspace_write",
)


def test_read_config_json_is_allowed(tmp_path, monkeypatch) -> None:
    """config.json no longer contains secrets — reading is safe."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="read_file", description="Read a file.", permission="read_only"
    )

    denied = check_permission(tool, _DEFAULT_CONFIG, {"path": "config.json"})

    assert denied is None


def test_read_env_is_denied(tmp_path, monkeypatch) -> None:
    """read_file must not expose .env to the LLM."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="read_file", description="Read a file.", permission="read_only"
    )

    denied = check_permission(tool, _DEFAULT_CONFIG, {"path": ".env"})

    assert denied is not None
    assert "sensitive file" in denied


def test_write_config_json_is_denied(tmp_path, monkeypatch) -> None:
    """write_file must not tamper with config.json."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="write_file", description="Write a file.", permission="workspace_write"
    )

    denied = check_permission(tool, _DEFAULT_CONFIG, {"path": "config.json"})

    assert denied is not None
    assert "sensitive file" in denied


def test_write_tools_json_is_denied(tmp_path, monkeypatch) -> None:
    """write_file must not let the agent modify its own tool definitions."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="write_file", description="Write a file.", permission="workspace_write"
    )

    denied = check_permission(tool, _DEFAULT_CONFIG, {"path": "tools.json"})

    assert denied is not None
    assert "sensitive file" in denied


def test_write_skills_dir_is_denied(tmp_path, monkeypatch) -> None:
    """write_file must not let the agent inject into system-prompt skills."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="write_file", description="Write a file.", permission="workspace_write"
    )

    denied = check_permission(tool, _DEFAULT_CONFIG, {"path": "skills/evil.md"})

    assert denied is not None
    assert "protected directory" in denied


def test_sensitive_check_applies_in_dangerous_mode(tmp_path, monkeypatch) -> None:
    """Sensitive-file protection is enforced even in dangerous mode."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="read_file", description="Read a file.", permission="read_only"
    )
    config = Config(
        azure_endpoint="",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="dangerous",
    )

    denied = check_permission(tool, config, {"path": ".env"})

    assert denied is not None
    assert "sensitive file" in denied


def test_normal_file_read_still_allowed(tmp_path, monkeypatch) -> None:
    """Regular workspace files must remain accessible."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="read_file", description="Read a file.", permission="read_only"
    )

    denied = check_permission(tool, _DEFAULT_CONFIG, {"path": "readme.md"})

    assert denied is None


def test_normal_file_write_still_allowed(tmp_path, monkeypatch) -> None:
    """Regular workspace files must remain writable."""
    monkeypatch.chdir(tmp_path)
    tool = ToolSpec(
        name="write_file", description="Write a file.", permission="workspace_write"
    )

    denied = check_permission(tool, _DEFAULT_CONFIG, {"path": "output.txt"})

    assert denied is None
