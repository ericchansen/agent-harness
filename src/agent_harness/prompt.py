"""System prompt builder — assembles identity, environment, and skills."""

from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from pathlib import Path


def load_skills(skills_dir: str = "skills") -> list[tuple[str, str]]:
    """Read all ``.md`` files from the skills directory."""
    skills_path = Path(skills_dir)
    if not skills_path.is_dir():
        return []
    return [
        (md.stem, md.read_text(encoding="utf-8"))
        for md in sorted(skills_path.glob("*.md"))
    ]


def build_system_prompt(skills_dir: str = "skills") -> str:
    """Assemble the full system prompt from identity + env + skills."""
    cwd = os.getcwd()
    skills = load_skills(skills_dir)
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    prompt = (
        "You are a helpful AI coding assistant running in a terminal.\n"
        "\n"
        "## Environment\n"
        f"- Working directory: {cwd}\n"
        f"- Platform: {platform.system()} {platform.release()}\n"
        f"- Date: {now}\n"
        "\n"
        "## Instructions\n"
        "- Be concise.\n"
        "- Use tools when you need to interact with the filesystem or run commands.\n"
        "- Tool descriptions tell you when and how to use each tool — follow them.\n"
    )

    for name, content in skills:
        prompt += f"\n## Skill: {name}\n{content}\n"

    return prompt
