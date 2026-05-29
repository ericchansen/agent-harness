"""LLM client — Azure OpenAI via Entra ID auth (streaming)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI, Stream
from openai.types.chat import ChatCompletionChunk

from agent_harness.models import Config, ToolSpec


@dataclass
class StreamedToolCall:
    """Accumulated tool call from streamed deltas."""

    id: str
    name: str
    arguments: str = ""


@dataclass
class StreamResult:
    """The fully-accumulated result of consuming a streaming response."""

    content: str | None = None
    tool_calls: list[StreamedToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls_printed: bool = False

    def to_message_dict(self) -> dict[str, Any]:
        """Convert to an OpenAI-shaped assistant message dict."""
        msg: dict[str, Any] = {"role": "assistant"}
        if self.content:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ]
        return msg


def make_client(config: Config) -> AzureOpenAI:
    """Build an Azure OpenAI client authenticated via Entra ID."""
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=config.azure_endpoint,
        azure_ad_token_provider=token_provider,
        api_version=config.azure_api_version,
    )


def _is_reasoning_model(deployment: str) -> bool:
    """Return True for models that produce reasoning summaries via Responses API."""
    name = deployment.lower()
    return name.startswith(("o1", "o3", "o4", "gpt-5"))


def call_model_streaming(
    client: AzureOpenAI,
    messages: list[dict[str, Any]],
    tools: list[ToolSpec],
    system_prompt: str,
    config: Config,
) -> Stream[ChatCompletionChunk]:
    """Send a streaming chat completion request with tool definitions."""
    api_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]
    api_tools: list[dict[str, Any]] | None = (
        [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]
        if tools
        else None
    )
    return client.chat.completions.create(
        model=config.azure_deployment,
        messages=api_messages,
        tools=api_tools,
        max_completion_tokens=4096,
        stream=True,
        stream_options={"include_usage": True},
    )


def _messages_to_responses_input(
    system_prompt: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert chat-completions messages to Responses API input items."""
    items: list[dict[str, Any]] = [{"role": "developer", "content": system_prompt}]
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg["tool_call_id"],
                    "output": str(msg.get("content", "")),
                }
            )
        elif role == "assistant":
            # Replay any assistant text first
            content = msg.get("content")
            if content:
                items.append({"role": "assistant", "content": content})
            # Then replay any tool calls as function_call items
            for tc in msg.get("tool_calls") or []:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    }
                )
        else:
            items.append({"role": role, "content": msg.get("content", "")})
    return items


def call_responses_streaming(
    client: AzureOpenAI,
    messages: list[dict[str, Any]],
    tools: list[ToolSpec],
    system_prompt: str,
    config: Config,
) -> Any:
    """Send a streaming Responses API request (reasoning-capable models)."""
    api_input = _messages_to_responses_input(system_prompt, messages)
    api_tools: list[dict[str, Any]] | None = (
        [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            }
            for t in tools
        ]
        if tools
        else None
    )
    return client.responses.create(
        model=config.azure_deployment,
        input=api_input,
        tools=api_tools,
        reasoning={"effort": "low", "summary": "auto"},
        stream=True,
    )


def consume_stream(
    stream: Stream[ChatCompletionChunk],
    *,
    show_tool_calls: bool = True,
) -> StreamResult:
    """Read all chunks from a streaming response, printing tokens as they arrive."""
    result = StreamResult()
    content_parts: list[str] = []
    tool_calls_by_index: dict[int, StreamedToolCall] = {}
    started_content = False
    announced_tools: set[int] = set()
    in_reasoning = False

    # ANSI codes for dimmed reasoning text
    DIM = "\033[2m"
    RESET = "\033[0m"

    for chunk in stream:
        if chunk.usage:
            result.prompt_tokens = chunk.usage.prompt_tokens
            result.completion_tokens = chunk.usage.completion_tokens

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        # o-series models stream reasoning via this attribute
        reasoning = getattr(delta, "reasoning_content", None) or getattr(
            delta, "reasoning", None
        )

        # --- streamed reasoning (dimmed) ---
        if reasoning:
            if not in_reasoning:
                sys.stdout.write(f"\n  💭 {DIM}")
                in_reasoning = True
            sys.stdout.write(reasoning)
            sys.stdout.flush()

        # --- transition from reasoning to content/tools ---
        if in_reasoning and (delta.content or delta.tool_calls):
            sys.stdout.write(RESET)
            print()
            in_reasoning = False

        # --- streamed text ---
        if delta.content:
            if not started_content:
                print("\n", end="")
                started_content = True
            sys.stdout.write(delta.content)
            sys.stdout.flush()
            content_parts.append(delta.content)

        # --- streamed tool calls (visible) ---
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_calls_by_index:
                    tool_calls_by_index[idx] = StreamedToolCall(
                        id=tc_delta.id or f"call-{idx}",
                        name=tc_delta.function.name or "",
                    )
                tc = tool_calls_by_index[idx]
                if tc_delta.function and tc_delta.function.name:
                    tc.name = tc_delta.function.name
                if tc_delta.function and tc_delta.function.arguments:
                    tc.arguments += tc_delta.function.arguments

                # Stream tool construction visibly
                if show_tool_calls:
                    if idx not in announced_tools and tc.name:
                        announced_tools.add(idx)
                        sys.stdout.write(f"\n  🔧 {tc.name}(")
                        sys.stdout.flush()
                    if tc_delta.function and tc_delta.function.arguments:
                        sys.stdout.write(tc_delta.function.arguments)
                        sys.stdout.flush()

    # Close the tool-call parentheses
    if show_tool_calls:
        for idx in sorted(announced_tools):
            sys.stdout.write(")")
        if announced_tools:
            print()

    # Close reasoning style if stream ended mid-reasoning
    if in_reasoning:
        sys.stdout.write(RESET)
        print()

    if started_content:
        print()  # newline after streamed text

    result.content = "".join(content_parts) or None
    result.tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]
    result.tool_calls_printed = show_tool_calls and bool(announced_tools)
    return result


def consume_responses_stream(
    stream: Any,
    *,
    show_tool_calls: bool = True,
) -> StreamResult:
    """Consume a streaming Responses API response.

    Streams reasoning summaries (dimmed 💭), assistant text, and tool-call
    argument deltas — all visible token-by-token.
    """
    result = StreamResult()
    content_parts: list[str] = []
    # Map output_index → accumulated tool call
    tool_calls_by_index: dict[int, StreamedToolCall] = {}
    announced_tools: set[int] = set()
    started_content = False
    in_reasoning = False

    DIM = "\033[2m"
    RESET = "\033[0m"

    for event in stream:
        et = getattr(event, "type", "")

        # --- reasoning summary ---
        if et == "response.reasoning_summary_text.delta":
            if not in_reasoning:
                sys.stdout.write(f"\n  💭 {DIM}")
                in_reasoning = True
            sys.stdout.write(event.delta)
            sys.stdout.flush()
            continue

        if et == "response.reasoning_summary_text.done":
            if in_reasoning:
                sys.stdout.write(RESET)
                print()
                in_reasoning = False
            continue

        # --- assistant text ---
        if et == "response.output_text.delta":
            if in_reasoning:
                sys.stdout.write(RESET)
                print()
                in_reasoning = False
            if not started_content:
                print()
                started_content = True
            sys.stdout.write(event.delta)
            sys.stdout.flush()
            content_parts.append(event.delta)
            continue

        # --- function/tool call announced ---
        if et == "response.output_item.added":
            item = getattr(event, "item", None)
            if item is not None and getattr(item, "type", "") == "function_call":
                if in_reasoning:
                    sys.stdout.write(RESET)
                    print()
                    in_reasoning = False
                idx = event.output_index
                tool_calls_by_index[idx] = StreamedToolCall(
                    id=item.call_id,
                    name=item.name,
                    arguments="",
                )
                if show_tool_calls and idx not in announced_tools:
                    announced_tools.add(idx)
                    sys.stdout.write(f"\n  🔧 {item.name}(")
                    sys.stdout.flush()
            continue

        # --- function call arguments streaming ---
        if et == "response.function_call_arguments.delta":
            idx = event.output_index
            if idx in tool_calls_by_index:
                tool_calls_by_index[idx].arguments += event.delta
                if show_tool_calls:
                    sys.stdout.write(event.delta)
                    sys.stdout.flush()
            continue

        # --- usage on completion ---
        if et == "response.completed":
            response_obj = getattr(event, "response", None)
            usage = getattr(response_obj, "usage", None) if response_obj else None
            if usage:
                result.prompt_tokens = getattr(usage, "input_tokens", 0)
                result.completion_tokens = getattr(usage, "output_tokens", 0)
            continue

    # Close any open visuals
    if show_tool_calls:
        for _idx in sorted(announced_tools):
            sys.stdout.write(")")
        if announced_tools:
            print()

    if in_reasoning:
        sys.stdout.write(RESET)
        print()

    if started_content:
        print()

    result.content = "".join(content_parts) or None
    result.tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]
    result.tool_calls_printed = show_tool_calls and bool(announced_tools)
    return result
