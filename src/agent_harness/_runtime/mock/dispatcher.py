"""Heuristic dispatcher that turns a user prompt into a deterministic tool call."""

from __future__ import annotations

from typing import Any

from agent_harness.models import ToolSpec

from .payloads import MockMessage, MockResponse, MockToolCall


def mock_response(
    messages: list[dict[str, Any]],
    tools: list[ToolSpec],
) -> MockResponse:
    """Return a deterministic, tiny mock response for rehearsals and tests."""
    last = messages[-1]
    available = {tool.name for tool in tools}

    if last["role"] == "tool":
        content = str(last["content"]).strip() or "(no output)"
        return MockResponse(MockMessage(f"Mock mode result:\n{content}"))

    user_text = str(last["content"]).strip()
    lower = user_text.lower()

    if (
        any(
            phrase in lower
            for phrase in ("what files", "list files", "current directory")
        )
        and "list_files" in available
    ):
        return MockResponse(
            MockMessage(tool_calls=[MockToolCall("list_files", {"path": "."})])
        )

    if "what time" in lower and "mcp__get_current_time" in available:
        return MockResponse(
            MockMessage(tool_calls=[MockToolCall("mcp__get_current_time", {})])
        )

    if lower.startswith("run ") and "run_command" in available:
        command = user_text[4:].strip()
        return MockResponse(
            MockMessage(tool_calls=[MockToolCall("run_command", {"command": command})])
        )

    if lower.startswith("read ") and "read_file" in available:
        path = user_text[5:].strip()
        return MockResponse(
            MockMessage(tool_calls=[MockToolCall("read_file", {"path": path})])
        )

    if lower.startswith("write ") and " to " in lower and "write_file" in available:
        payload = user_text[6:].strip()
        split_at = lower[6:].rfind(" to ")
        content = payload[:split_at].strip()
        path = payload[split_at + 4 :].strip()
        return MockResponse(
            MockMessage(
                tool_calls=[
                    MockToolCall(
                        "write_file",
                        {"path": path.strip(), "content": content.strip()},
                    )
                ]
            )
        )

    if lower == "what is 2 + 2?":
        return MockResponse(MockMessage("4"))

    return MockResponse(MockMessage("Mock mode: no tool call needed."))
