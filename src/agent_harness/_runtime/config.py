"""Config loading and Azure client cache key."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

from agent_harness.models import Config


def load_config(path: str = "config.json", require_endpoint: bool = True) -> Config:
    """Load config from JSON file + env vars.

    Non-sensitive settings (deployment, permission mode, etc.) come from
    ``config.json``.  Secrets (``azure_endpoint``) come exclusively from
    environment variables — either exported in the shell or placed in a
    ``.env`` file (loaded automatically via python-dotenv).
    """
    load_dotenv(find_dotenv(usecwd=True), override=False)

    config_path = Path(path)
    if not config_path.exists():
        fallback = Path("config.example.json")
        if fallback.exists():
            config_path = fallback
        else:
            sys.exit(
                "❌ No config.json found. Copy config.example.json to config.json."
            )

    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))

    # Secrets come exclusively from env vars (shell or .env file).
    if endpoint := os.environ.get("AZURE_ENDPOINT"):
        raw["azure_endpoint"] = endpoint
    if deployment := os.environ.get("AZURE_DEPLOYMENT"):
        raw["azure_deployment"] = deployment

    raw.setdefault("azure_endpoint", "")

    if require_endpoint and not raw.get("azure_endpoint"):
        sys.exit(
            "❌ azure_endpoint is not set. Either:\n"
            "   1. Create a .env file with AZURE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/\n"
            "   2. Export AZURE_ENDPOINT in your shell\n"
            "   3. Deploy infra: az deployment sub create --location eastus2"
            " --template-file infra/main.bicep --parameters infra/main.bicepparam"
        )

    return Config(**{k: v for k, v in raw.items() if k in Config.__dataclass_fields__})


def client_signature(config: Config) -> tuple[str, str, str]:
    """Return the config fields that require a new Azure client."""
    return (
        config.azure_endpoint,
        config.azure_deployment,
        config.azure_api_version,
    )
