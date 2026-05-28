"""OpenAI-shaped response payloads for mock mode."""

from __future__ import annotations

import json
from typing import Any


class MockUsage:
    prompt_tokens = 0
    completion_tokens = 0


class MockFunction:
    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.name = name
        self.arguments = json.dumps(arguments)


class MockToolCall:
    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.id = f"mock-{name}"
        self.function = MockFunction(name, arguments)


class MockMessage:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[MockToolCall] | None = None,
    ) -> None:
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        if exclude_none:
            data = {k: v for k, v in data.items() if v is not None}
        return data


class MockChoice:
    def __init__(self, message: MockMessage) -> None:
        self.message = message


class MockResponse:
    def __init__(self, message: MockMessage) -> None:
        self.choices = [MockChoice(message)]
        self.usage = MockUsage()
