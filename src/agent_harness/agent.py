"""Agent harness — the core loop that makes an LLM into an agent."""

from __future__ import annotations

import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from openai import AzureOpenAI

from agent_harness.api import call_model, make_client
from agent_harness.mcp_client import McpSession
from agent_harness.models import Config, ToolSpec
from agent_harness.prompt import build_system_prompt
from agent_harness.tools import check_permission, execute_tool, load_tools


def load_config(path: str = "config.json") -> Config:
    """Load config from JSON file, with env var overrides.

    Falls back to ``config.example.json`` if ``config.json`` doesn't exist.
    ``AZURE_ENDPOINT`` env var overrides the file value.
    """
    config_path = Path(path)
    if not config_path.exists():
        fallback = Path("config.example.json")
        if fallback.exists():
            config_path = fallback
        else:
            sys.exit(
                "❌ No config.json found. Copy config.example.json to config.json"
                " and set your azure_endpoint."
            )

    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))

    # Env var overrides
    if endpoint := os.environ.get("AZURE_ENDPOINT"):
        raw["azure_endpoint"] = endpoint
    if deployment := os.environ.get("AZURE_DEPLOYMENT"):
        raw["azure_deployment"] = deployment

    if not raw.get("azure_endpoint"):
        sys.exit(
            "❌ azure_endpoint is empty. Either:\n"
            "   1. Set it in config.json\n"
            "   2. Export AZURE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/\n"
            "   3. Deploy infra: az deployment sub create --location eastus2"
            " --template-file infra/main.bicep --parameters infra/main.bicepparam"
        )

    return Config(**{k: v for k, v in raw.items() if k in Config.__dataclass_fields__})


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

    denied = check_permission(tool, config)
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
    client: AzureOpenAI,
    config: Config,
) -> list[dict[str, Any]]:
    """Run one full agent turn — may loop through multiple tool calls."""
    tools = load_tools()
    system_prompt = build_system_prompt()

    # Open a persistent MCP session for this turn (or a no-op context)
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
            response = call_model(client, messages, tools, system_prompt, config)
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


def main() -> None:
    """Interactive REPL entry point."""
    messages: list[dict[str, Any]] = []
    config = load_config()
    client = make_client(config)

    print("🤖 Agent Harness Demo")
    print(
        "   Edit config.json, tools.json, skills/"
        " in VS Code — changes apply on next prompt."
    )
    print("   Type 'quit' to exit, 'reset' to clear conversation.\n")

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "reset":
            messages.clear()
            print("  🧹 Conversation cleared.\n")
            continue

        config = load_config()  # reload each turn for live editing
        try:
            messages = agent_turn(user_input, messages, client, config)
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ Error: {exc}")
        print()
