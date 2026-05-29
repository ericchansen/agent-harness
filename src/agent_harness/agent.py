"""Agent harness — the core loop that makes an LLM into an agent."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

from agent_harness.mcp_client import McpSession
from agent_harness.models import Config, Skill, ToolSpec
from agent_harness.prompt import build_system_prompt, load_skills
from agent_harness.tools import check_permission, execute_tool, load_tools

from ._runtime.api import StreamResult

# A response provider takes (messages, tools, system_prompt, config) and returns
# a StreamResult — text printed live during streaming, tool calls accumulated.
ResponseFn = Callable[[list[dict[str, Any]], list[ToolSpec], str, Config], StreamResult]


def _handle_skill_tool(args: dict[str, Any], skills: list[Skill]) -> str:
    """Return a skill body by name. Mirrors Copilot CLI's `skill` tool."""
    name = args.get("name", "")
    skill = next((s for s in skills if s.name == name), None)
    if skill is None:
        available = ", ".join(s.name for s in skills) or "(none)"
        return f"Error: skill '{name}' not found. Available skills: {available}"
    return skill.body


def _execute_single_tool(
    name: str,
    args: dict[str, Any],
    tool: ToolSpec | None,
    config: Config,
    mcp: McpSession | None,
    skills: list[Skill],
) -> str:
    """Run permission check then execute a tool, returning the result string."""
    if tool is None:
        return f"Error: unknown tool '{name}'"

    denied = check_permission(tool, config, args)
    if denied:
        print(f"  🚫 {denied}")
        return denied

    if name == "skill":
        skill_name = args.get("name", "")
        result = _handle_skill_tool(args, skills)
        if any(s.name == skill_name for s in skills):
            skill = next(s for s in skills if s.name == skill_name)
            desc = f" — {skill.description}" if skill.description else ""
            print(f"  🎯 Skill activated: {skill.name}{desc}")
        else:
            print(f"  ⚠️  Skill not found: {skill_name}")
        return result

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
    skills = load_skills()
    system_prompt = build_system_prompt()

    mcp_ctx = McpSession(config.mcp_server) if config.mcp_server else nullcontext()
    with mcp_ctx as mcp:
        if mcp is not None:
            mcp_tools = mcp.list_tools()
            tools = tools + mcp_tools
            if config.show_system_prompt:
                print(
                    f"  🔌 MCP: loaded {len(mcp_tools)} tools from {config.mcp_server}"
                )

        if config.show_system_prompt:
            sep = "=" * 60
            print(f"\n{sep}\nSYSTEM PROMPT:\n{sep}\n{system_prompt}\n{sep}")

            print()
            print(f"  📋 {len(tools)} tools available:")
            for t in tools:
                prefix = "🔌" if t.mcp_server else "🔧"
                print(f"     {prefix} {t.name}: {t.description[:80]}")

            print()
            if skills:
                print(f"  📚 {len(skills)} skills advertised:")
                for skill in skills:
                    summary = skill.description or "(no description)"
                    print(f"     📖 {skill.name}: {summary[:80]}")
            else:
                print("  📚 0 skills advertised (drop a .md file in skills/)")

        messages.append({"role": "user", "content": user_message})

        for iteration in range(config.max_iterations):
            result = response_fn(messages, tools, system_prompt, config)

            messages.append(result.to_message_dict())

            if not result.tool_calls:
                if result.prompt_tokens or result.completion_tokens:
                    print(
                        f"\n  ⚡ tokens: {result.prompt_tokens} in"
                        f" / {result.completion_tokens} out"
                    )
                return messages

            for tc in result.tool_calls:
                args: dict[str, Any] = json.loads(tc.arguments)
                tool = next((t for t in tools if t.name == tc.name), None)

                if config.show_tool_calls and not result.tool_calls_printed:
                    print(f"\n  🔧 {tc.name}({json.dumps(args)[:120]})")

                tool_result = _execute_single_tool(
                    tc.name, args, tool, config, mcp, skills
                )
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": str(tool_result)}
                )

        print("  ⚠️  Max iterations reached.")

    return messages
