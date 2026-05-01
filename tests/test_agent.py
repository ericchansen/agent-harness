"""Focused tests for the demo entry/runtime helpers."""

from __future__ import annotations

import json

from agent_harness.agent import agent_turn, load_config
from agent_harness.models import Config


def test_load_config_uses_example_and_env_override(tmp_path, monkeypatch) -> None:
    """Config falls back to config.example.json and honors env overrides."""
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "azure_endpoint": "https://from-file.example/",
                "azure_deployment": "gpt-4o",
                "azure_api_version": "2025-01-01-preview",
                "permission_mode": "workspace_write",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AZURE_ENDPOINT", "https://from-env.example/")

    config = load_config(require_endpoint=False)

    assert config.azure_endpoint == "https://from-env.example/"
    assert config.azure_deployment == "gpt-4o"


def test_agent_turn_mock_mode_roundtrips_tool_call(tmp_path, monkeypatch) -> None:
    """Mock mode should issue a tool call, execute it, and answer with the result."""
    (tmp_path / "tools.json").write_text(
        json.dumps(
            [
                {
                    "name": "list_files",
                    "description": "List files and directories at a path.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                    },
                    "permission": "read_only",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "demo.txt").write_text("hello", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = Config(
        azure_endpoint="",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="read_only",
    )

    messages = agent_turn(
        "What files are in the current directory?",
        [],
        None,
        config,
        use_mock=True,
    )

    assert any(message["role"] == "tool" for message in messages)
    assert messages[-1]["role"] == "assistant"
    assert "demo.txt" in messages[-1]["content"]
