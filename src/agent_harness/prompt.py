"""System prompt builder — assembles identity, environment, and skills."""

from __future__ import annotations

import os
import platform
import re
from datetime import datetime, timezone
from html import escape as _xml_escape
from pathlib import Path

from agent_harness.models import Skill


def _parse_skill_file(name: str, raw: str) -> Skill:
    """Parse a .md file with optional YAML-like frontmatter into a Skill.

    Frontmatter format::

        ---
        description: short summary shown to the model in <available_skills>
        ---
        ## Skill body in markdown...
    """
    description = ""
    body = raw

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if fm_match:
        block = fm_match.group(1)
        body = raw[fm_match.end() :]
        for line in block.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            if key.strip().lower() == "description":
                description = value.strip()

    return Skill(name=name, description=description, body=body)


def load_skills(skills_dir: str = "skills") -> list[Skill]:
    """Read all ``.md`` files from the skills directory."""
    skills_path = Path(skills_dir)
    if not skills_path.is_dir():
        return []
    return [
        _parse_skill_file(md.stem, md.read_text(encoding="utf-8"))
        for md in sorted(skills_path.glob("*.md"))
    ]


def _skills_block(skills: list[Skill]) -> str:
    """Render the <skills_instructions> + <available_skills> XML block.

    Mirrors the Copilot CLI pattern: only name + description go into the
    prompt; the body loads only when the model invokes the ``skill`` tool.
    """
    if not skills:
        return ""

    out = [
        "",
        "<skills_instructions>",
        "When the user's request matches a skill in <available_skills>, you",
        "MUST invoke the `skill` tool with that skill's name BEFORE doing any",
        "other work. The tool returns the skill's full instructions; follow",
        "them exactly. Never mention or 'use' a skill without first calling",
        "the `skill` tool to load it.",
        "</skills_instructions>",
        "",
        "<available_skills>",
    ]
    for skill in skills:
        name = _xml_escape(skill.name)
        desc = _xml_escape(skill.description or "(no description)")
        out.append("  <skill>")
        out.append(f"    <name>{name}</name>")
        out.append(f"    <description>{desc}</description>")
        out.append("  </skill>")
    out.append("</available_skills>")
    return "\n".join(out) + "\n"


def build_system_prompt(skills_dir: str = "skills") -> str:
    """Assemble the full system prompt from identity + env + advertised skills."""
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
        "- Use tools when you need to interact with the filesystem or run"
        " commands.\n"
        "- Tool descriptions tell you when and how to use each tool — follow"
        " them.\n"
    )

    prompt += _skills_block(skills)
    return prompt
