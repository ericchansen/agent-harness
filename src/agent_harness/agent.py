"""Agent harness — the core loop that makes an LLM into an agent."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

from agent_harness.mcp_client import McpSession
from agent_harness.models import Config, ToolSpec
from agent_harness.prompt import build_system_prompt
from agent_harness.tools import check_permission, execute_tool, load_tools

# A response provider takes (messages, tools, system_prompt, config) and returns
# an OpenAI-shaped response (real Azure call or mock).
ResponseFn = Callable[[list[dict[str, Any]], list[ToolSpec], str, Config], Any]


def _execute_single_tool(
    name: str,
    args: dict[str, Any],
    tool: ToolSpec | None,
    config: Config,
    mcp: McpSession | None,
) -> str:
    """Run permission check then execute a tool, returning the result string."""
    if tool is None:
        return f"Error: unknown tool '{name}'"

    denied = check_permission(tool, config, args)
    if denied:
        print(f"  🚫 {denied}")
        return denied

    if tool.mcp_server and tool.mcp_tool_name and mcp:
        result = mcp.call_tool(tool.mcp_tool_name, args)
        preview = str(result).replace("\n", "\\n")[:150]
        print(f"  📎 [mcp] → {preview}")
    else:
        result = execute_tool(name, args)
        preview = str(result).replace("\n", "\\n")[:150]
        print(f"  📎 → {preview}")

    return result


def agent_turn(
    user_message: str,
    messages: list[dict[str, Any]],
    response_fn: ResponseFn,
    config: Config,
) -> list[dict[str, Any]]:
    """Run one full agent turn — may loop through multiple tool calls."""
    tools = load_tools()
    system_prompt = build_system_prompt()

    mcp_ctx = McpSession(config.mcp_server) if config.mcp_server else nullcontext()
    with mcp_ctx as mcp:
        if mcp is not None:
            mcp_tools = mcp.list_tools()
            tools = tools + mcp_tools
            print(f"  🔌 MCP: loaded {len(mcp_tools)} tools from {config.mcp_server}")

        if config.show_system_prompt:
            sep = "=" * 60
            print(f"\n{sep}\nSYSTEM PROMPT:\n{sep}\n{system_prompt}\n{sep}")

        messages.append({"role": "user", "content": user_message})

        for _ in range(config.max_iterations):
            response = response_fn(messages, tools, system_prompt, config)
            choice = response.choices[0]

            messages.append(choice.message.model_dump(exclude_none=True))

            if choice.message.content:
                print(f"\n{choice.message.content}")

            if not choice.message.tool_calls:
                usage = response.usage
                if usage:
                    print(
                        f"\n  ⚡ tokens: {usage.prompt_tokens} in"
                        f" / {usage.completion_tokens} out"
                    )
                return messages

            for tc in choice.message.tool_calls:
                name = tc.function.name
                args: dict[str, Any] = json.loads(tc.function.arguments)
                tool = next((t for t in tools if t.name == name), None)

                if config.show_tool_calls:
                    print(f"\n  🔧 {name}({json.dumps(args)[:120]})")

                result = _execute_single_tool(name, args, tool, config, mcp)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": str(result)}
                )

        print("  ⚠️  Max iterations reached.")

    return messages
