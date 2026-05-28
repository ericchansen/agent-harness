"""LLM client — Azure OpenAI via Entra ID auth."""

from __future__ import annotations

from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from openai.types.chat import ChatCompletion

from agent_harness.models import Config, ToolSpec


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


def call_model(
    client: AzureOpenAI,
    messages: list[dict[str, Any]],
    tools: list[ToolSpec],
    system_prompt: str,
    config: Config,
) -> ChatCompletion:
    """Send a chat completion request with tool definitions."""
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
    )
