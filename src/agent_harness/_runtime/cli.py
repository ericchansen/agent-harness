"""CLI entry point — argparse, REPL, response-provider selection."""

from __future__ import annotations

import argparse
from typing import Any
from urllib.parse import urlparse

from openai import AzureOpenAI

from agent_harness.agent import ResponseFn, agent_turn
from agent_harness.models import Config

from .api import call_model, make_client
from .config import client_signature, load_config
from .mock import mock_response
from .preflight import run_preflight


def _azure_provider(client: AzureOpenAI) -> ResponseFn:
    """Bind an Azure client into a ResponseFn."""

    def provider(
        messages: list[dict[str, Any]],
        tools: Any,
        system_prompt: str,
        config: Config,
    ) -> Any:
        return call_model(client, messages, tools, system_prompt, config)

    return provider


def _mock_provider() -> ResponseFn:
    """Return a ResponseFn that ignores Azure and dispatches deterministically."""

    def provider(
        messages: list[dict[str, Any]],
        tools: Any,
        system_prompt: str,  # noqa: ARG001
        config: Config,  # noqa: ARG001
    ) -> Any:
        return mock_response(messages, tools)

    return provider


def _format_runtime_error(exc: Exception, config: Config) -> str:
    """Return a concise, actionable CLI error message."""
    endpoint = config.azure_endpoint.rstrip("/")
    host = urlparse(endpoint).hostname or endpoint

    current: BaseException | None = exc
    messages: list[str] = []
    while current is not None:
        msg = str(current).strip()
        if msg:
            messages.append(msg.lower())
        current = current.__cause__

    if any(
        token in message
        for message in messages
        for token in ("getaddrinfo failed", "non-existent domain", "name or service")
    ):
        return (
            "Connection error: could not resolve the Azure endpoint host "
            f"'{host}'.\n"
            "Check AZURE_ENDPOINT in your .env file (or shell), and verify with:\n"
            f"  nslookup {host}"
        )

    return str(exc)


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
    config = load_config(require_endpoint=not args.mock)

    if args.preflight:
        try:
            run_preflight(config, use_mock=args.mock)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Preflight failed: {exc}")
            return 1
        return 0

    client: AzureOpenAI | None = None
    signature: tuple[str, str, str] | None = None
    if args.mock:
        response_fn: ResponseFn = _mock_provider()
    else:
        client = make_client(config)
        signature = client_signature(config)
        response_fn = _azure_provider(client)

    if args.prompt:
        try:
            agent_turn(args.prompt, messages, response_fn, config)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error: {_format_runtime_error(exc, config)}")
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
            new_signature = client_signature(config)
            if client is None or new_signature != signature:
                client = make_client(config)
                signature = new_signature
                response_fn = _azure_provider(client)
        try:
            messages = agent_turn(user_input, messages, response_fn, config)
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ Error: {_format_runtime_error(exc, config)}")
        print()

    return 0
