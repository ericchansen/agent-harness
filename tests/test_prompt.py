"""Prompt and skill loading tests."""

from __future__ import annotations

from agent_harness.prompt import build_system_prompt, load_skills


def test_load_skills_parses_frontmatter(tmp_path, monkeypatch) -> None:
    """Skill markdown with frontmatter should populate description."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "code-review.md").write_text(
        "---\n" "description: Structured review\n" "---\n" "Use a checklist.",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    skills = load_skills()
    assert len(skills) == 1
    skill = skills[0]
    assert skill.name == "code-review"
    assert skill.description == "Structured review"
    assert skill.body.strip() == "Use a checklist."


def test_load_skills_without_frontmatter(tmp_path, monkeypatch) -> None:
    """Skills without frontmatter still load (no description)."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "plain.md").write_text("Use a checklist.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    skills = load_skills()
    assert len(skills) == 1
    assert skills[0].description == ""
    assert skills[0].body == "Use a checklist."


def test_build_system_prompt_advertises_name_and_description_only(
    tmp_path, monkeypatch
) -> None:
    """The prompt should advertise only name + description, never the body."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "code-review.md").write_text(
        "---\ndescription: Reviews code thoroughly\n---\nFULL BODY GOES HERE.",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    prompt = build_system_prompt()

    assert "<available_skills>" in prompt
    assert "<name>code-review</name>" in prompt
    assert "<description>Reviews code thoroughly</description>" in prompt
    assert "<skills_instructions>" in prompt
    # Critical: body must NOT be in the prompt — it loads via the skill tool
    assert "FULL BODY GOES HERE." not in prompt
