"""Prompt and skill loading tests."""

from __future__ import annotations

from agent_harness.prompt import build_system_prompt, load_skills


def test_load_skills_and_prompt_include_skill_contents(tmp_path, monkeypatch) -> None:
    """Skill markdown should be loaded and appended to the system prompt."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "code-review.md").write_text("Use a checklist.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    skills = load_skills()
    prompt = build_system_prompt()

    assert skills == [("code-review", "Use a checklist.")]
    assert "## Skill: code-review" in prompt
    assert "Use a checklist." in prompt
