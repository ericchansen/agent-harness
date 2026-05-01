"""Agent harness — the core loop that makes an LLM into an agent."""

from __future__ import annotations

import argparse
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
from agent_harness.prompt import build_system_prompt, load_skills
from agent_harness.tools import check_permission, execute_tool, load_tools


class _MockUsage:
    """Tiny usage payload so mock mode looks like the real loop."""

    prompt_tokens = 0
    completion_tokens = 0


class _MockFunction:
    """OpenAI-style function call payload."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.name = name
        self.arguments = json.dumps(arguments)


class _MockToolCall:
    """OpenAI-style tool call payload."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.id = f"mock-{name}"
        self.function = _MockFunction(name, arguments)


class _MockMessage:
    """OpenAI-style assistant message payload."""

    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[_MockToolCall] | None = None,
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


class _MockChoice:
    """OpenAI-style choice payload."""

    def __init__(self, message: _MockMessage) -> None:
        self.message = message


class _MockResponse:
    """OpenAI-style response payload."""

    def __init__(self, message: _MockMessage) -> None:
        self.choices = [_MockChoice(message)]
        self.usage = _MockUsage()


def load_config(path: str = "config.json", require_endpoint: bool = True) -> Config:
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

    if require_endpoint and not raw.get("azure_endpoint"):
        sys.exit(
            "❌ azure_endpoint is empty. Either:\n"
            "   1. Set it in config.json\n"
            "   2. Export AZURE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/\n"
            "   3. Deploy infra: az deployment sub create --location eastus2"
            " --template-file infra/main.bicep --parameters infra/main.bicepparam"
        )

    return Config(**{k: v for k, v in raw.items() if k in Config.__dataclass_fields__})


def _client_signature(config: Config) -> tuple[str, str, str]:
    """Return the config fields that require a new Azure client."""
    return (
        config.azure_endpoint,
        config.azure_deployment,
        config.azure_api_version,
    )


def _mock_response(
    messages: list[dict[str, Any]],
    tools: list[ToolSpec],
) -> _MockResponse:
    """Return a deterministic, tiny mock response for rehearsals and tests."""
    last = messages[-1]
    available = {tool.name for tool in tools}

    if last["role"] == "tool":
        content = str(last["content"]).strip() or "(no output)"
        return _MockResponse(_MockMessage(f"Mock mode result:\n{content}"))

    user_text = str(last["content"]).strip()
    lower = user_text.lower()

    if (
        any(
            phrase in lower
            for phrase in ("what files", "list files", "current directory")
        )
        and "list_files" in available
    ):
        return _MockResponse(
            _MockMessage(tool_calls=[_MockToolCall("list_files", {"path": "."})])
        )

    if "what time" in lower and "mcp__get_current_time" in available:
        return _MockResponse(
            _MockMessage(tool_calls=[_MockToolCall("mcp__get_current_time", {})])
        )

    if lower.startswith("run ") and "run_command" in available:
        command = user_text[4:].strip()
        return _MockResponse(
            _MockMessage(
                tool_calls=[_MockToolCall("run_command", {"command": command})]
            )
        )

    if lower.startswith("read ") and "read_file" in available:
        path = user_text[5:].strip()
        return _MockResponse(
            _MockMessage(tool_calls=[_MockToolCall("read_file", {"path": path})])
        )

    if lower.startswith("write ") and " to " in lower and "write_file" in available:
        payload = user_text[6:].strip()
        split_at = lower[6:].rfind(" to ")
        content = payload[:split_at].strip()
        path = payload[split_at + 4 :].strip()
        return _MockResponse(
            _MockMessage(
                tool_calls=[
                    _MockToolCall(
                        "write_file",
                        {"path": path.strip(), "content": content.strip()},
                    )
                ]
            )
        )

    if lower == "what is 2 + 2?":
        return _MockResponse(_MockMessage("4"))

    return _MockResponse(_MockMessage("Mock mode: no tool call needed."))


def run_preflight(config: Config, use_mock: bool) -> None:
    """Print a simple local setup report before a demo run."""
    tools = load_tools()
    skills = load_skills()

    print("🔎 Preflight")
    print(f"   cwd: {Path.cwd()}")
    print(f"   provider: {'mock' if use_mock else 'azure'}")
    print(f"   tools: {len(tools)} built-in")
    print(f"   skills: {len(skills)} loaded")
    print(f"   permission_mode: {config.permission_mode}")

    if use_mock:
        print("   ✅ mock mode does not require Azure connectivity")
    else:
        make_client(config)
        print(
            "   ✅ Azure client settings loaded"
            f" for {config.azure_deployment} (connectivity not verified)"
        )

    if config.mcp_server:
        with McpSession(config.mcp_server) as mcp:
            mcp_tools = mcp.list_tools()
            print(
                f"   ✅ MCP server '{config.mcp_server}' exposed {len(mcp_tools)} tools"
            )


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
    client: AzureOpenAI | None,
    config: Config,
    use_mock: bool = False,
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
            if use_mock:
                response = _mock_response(messages, tools)
            else:
                if client is None:
                    raise RuntimeError("Azure client is not initialized")
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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Minimal AI agent harness for live demos"
    )
    parser.add_argument(
        "--prompt",
        help="Run one prompt and exit instead of starting the REPL.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate demo prerequisites and print the current setup.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock responses instead of calling Azure OpenAI.",
    )
    args = parser.parse_args(argv)

    messages: list[dict[str, Any]] = []
    client: AzureOpenAI | None = None
    client_signature: tuple[str, str, str] | None = None

    config = load_config(require_endpoint=not args.mock)

    if args.preflight:
        try:
            run_preflight(config, use_mock=args.mock)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Preflight failed: {exc}")
            return 1
        return 0

    if not args.mock:
        client = make_client(config)
        client_signature = _client_signature(config)

    if args.prompt:
        try:
            agent_turn(args.prompt, messages, client, config, use_mock=args.mock)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error: {exc}")
            return 1
        return 0

    print("🤖 Agent Harness Demo")
    print(
        "   Edit config.json, tools.json, skills/"
        " in VS Code — changes apply on next prompt."
    )
    if args.mock:
        print("   Running in mock mode — deterministic responses, no Azure required.")
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

        config = load_config(require_endpoint=not args.mock)
        if not args.mock:
            new_signature = _client_signature(config)
            if client is None or new_signature != client_signature:
                client = make_client(config)
                client_signature = new_signature
        try:
            messages = agent_turn(
                user_input, messages, client, config, use_mock=args.mock
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ Error: {exc}")
        print()

    return 0
