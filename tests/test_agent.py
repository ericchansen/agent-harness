"""Focused tests for the demo entry/runtime helpers."""

from __future__ import annotations

import json
import socket

import agent_harness._runtime.preflight as preflight_module
from agent_harness._runtime.api import StreamedToolCall, StreamResult
from agent_harness._runtime.cli import _format_runtime_error
from agent_harness._runtime.config import load_config
from agent_harness._runtime.mock import mock_response
from agent_harness._runtime.preflight import run_preflight
from agent_harness.agent import agent_turn
from agent_harness.models import Config


def _mock_provider():
    """Adapt the bare mock_response to the agent's ResponseFn signature."""

    def provider(messages, tools, system_prompt, config):  # noqa: ARG001
        mock = mock_response(messages, tools)
        msg = mock.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    StreamedToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )
        return StreamResult(content=msg.content, tool_calls=tool_calls)

    return provider


def test_load_config_uses_example_and_env_override(tmp_path, monkeypatch) -> None:
    """Config falls back to config.example.json; endpoint comes from env."""
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
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
        _mock_provider(),
        config,
    )

    assert any(message["role"] == "tool" for message in messages)
    assert messages[-1]["role"] == "assistant"
    assert "demo.txt" in messages[-1]["content"]


def test_agent_turn_mock_mode_write_handles_mixed_case_to(
    tmp_path, monkeypatch
) -> None:
    """Mock mode should parse write prompts case-insensitively."""
    (tmp_path / "tools.json").write_text(
        json.dumps(
            [
                {
                    "name": "write_file",
                    "description": "Write a file.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                    "permission": "workspace_write",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = Config(
        azure_endpoint="",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="workspace_write",
    )

    messages = agent_turn(
        "Write hello TO test.txt",
        [],
        _mock_provider(),
        config,
    )

    assert any(message["role"] == "tool" for message in messages)
    assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "hello"


def test_run_preflight_says_connectivity_not_verified(
    tmp_path, monkeypatch, capsys
) -> None:
    """Azure preflight wording should not overclaim live validation."""
    (tmp_path / "tools.json").write_text("[]", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(preflight_module, "make_client", lambda config: object())

    config = Config(
        azure_endpoint="https://example.test/",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="workspace_write",
    )

    run_preflight(config, use_mock=False)

    out = capsys.readouterr().out
    assert "connectivity not verified" in out


def test_format_runtime_error_reports_unresolvable_endpoint() -> None:
    """Endpoint DNS failures should produce actionable endpoint guidance."""
    config = Config(
        azure_endpoint="https://agent-harness-dev.cognitiveservices.azure.com/",
        azure_deployment="gpt-4o",
        azure_api_version="2025-01-01-preview",
        permission_mode="workspace_write",
    )
    err = RuntimeError("Connection error.")
    err.__cause__ = socket.gaierror(11001, "getaddrinfo failed")

    message = _format_runtime_error(err, config)

    assert "could not resolve the Azure endpoint host" in message
    assert "agent-harness-dev.cognitiveservices.azure.com" in message
    assert "nslookup" in message
