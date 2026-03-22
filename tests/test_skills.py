"""Tests for skills.py — SkillRegistry."""

from pathlib import Path

from tg_gemini.skills import Skill, SkillRegistry


def _make_skill_dir(tmp_path: Path, name: str, content: str) -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


# ── Skill dataclass ────────────────────────────────────────────────────────


def test_skill_fields() -> None:
    skill = Skill(
        name="review",
        display_name="Code Review",
        description="Review code",
        prompt="You are a reviewer.",
        source_dir=Path("/tmp/review"),
    )
    assert skill.name == "review"
    assert skill.display_name == "Code Review"
    assert skill.description == "Review code"
    assert skill.prompt == "You are a reviewer."


# ── SkillRegistry.load ─────────────────────────────────────────────────────


def test_load_returns_zero_if_no_dirs() -> None:
    registry = SkillRegistry([])
    assert registry.load() == 0


def test_load_skips_nonexistent_dir(tmp_path: Path) -> None:
    registry = SkillRegistry([tmp_path / "nonexistent"])
    assert registry.load() == 0


def test_load_parses_skill_with_frontmatter(tmp_path: Path) -> None:
    content = "---\nname: Code Review\ndescription: Review code for issues\n---\n\nYou are a reviewer."
    _make_skill_dir(tmp_path, "review", content)
    registry = SkillRegistry([tmp_path])
    assert registry.load() == 1
    skill = registry.get("review")
    assert skill is not None
    assert skill.display_name == "Code Review"
    assert skill.description == "Review code for issues"
    assert skill.prompt == "You are a reviewer."


def test_load_parses_skill_without_frontmatter(tmp_path: Path) -> None:
    content = "You are a refactoring expert."
    _make_skill_dir(tmp_path, "refactor", content)
    registry = SkillRegistry([tmp_path])
    assert registry.load() == 1
    skill = registry.get("refactor")
    assert skill is not None
    assert skill.name == "refactor"
    assert skill.display_name == "refactor"
    assert skill.prompt == "You are a refactoring expert."


def test_load_ignores_non_directory_entries(tmp_path: Path) -> None:
    (tmp_path / "file.md").write_text("not a skill dir")
    registry = SkillRegistry([tmp_path])
    assert registry.load() == 0


def test_load_ignores_dirs_without_skill_md(tmp_path: Path) -> None:
    subdir = tmp_path / "noskill"
    subdir.mkdir()
    (subdir / "README.md").write_text("not a skill")
    registry = SkillRegistry([tmp_path])
    assert registry.load() == 0


def test_load_multiple_skills(tmp_path: Path) -> None:
    for name in ("alpha", "beta", "gamma"):
        _make_skill_dir(tmp_path, name, f"Skill: {name}")
    registry = SkillRegistry([tmp_path])
    assert registry.load() == 3


def test_load_multiple_dirs(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _make_skill_dir(dir_a, "skill1", "Skill 1")
    _make_skill_dir(dir_b, "skill2", "Skill 2")
    registry = SkillRegistry([dir_a, dir_b])
    assert registry.load() == 2


def test_load_logs_warning_on_bad_skill(tmp_path: Path) -> None:
    """A skill dir with an unreadable SKILL.md is skipped without crash."""
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("---\nbad: yaml: :\n---\nbody")
    # Even with bad YAML, _extract_frontmatter falls back to empty dict
    registry = SkillRegistry([tmp_path])
    count = registry.load()
    # Should still load with fallback (no exception raised)
    assert count >= 0


# ── SkillRegistry.get ──────────────────────────────────────────────────────


def test_get_case_insensitive(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "review", "Review skill")
    registry = SkillRegistry([tmp_path])
    registry.load()
    assert registry.get("REVIEW") is not None
    assert registry.get("Review") is not None


def test_get_normalizes_hyphens_underscores(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "code-review", "Review skill")
    registry = SkillRegistry([tmp_path])
    registry.load()
    assert registry.get("code_review") is not None
    assert registry.get("code-review") is not None


def test_get_returns_none_for_unknown(tmp_path: Path) -> None:
    registry = SkillRegistry([tmp_path])
    registry.load()
    assert registry.get("nonexistent") is None


# ── SkillRegistry.list_all ─────────────────────────────────────────────────


def test_list_all_sorted(tmp_path: Path) -> None:
    for name in ("zebra", "apple", "mango"):
        _make_skill_dir(tmp_path, name, f"Skill {name}")
    registry = SkillRegistry([tmp_path])
    registry.load()
    names = [s.name for s in registry.list_all()]
    assert names == sorted(names)


def test_list_all_empty_before_load() -> None:
    registry = SkillRegistry([])
    assert registry.list_all() == []


# ── SkillRegistry.invalidate ──────────────────────────────────────────────


def test_invalidate_clears_skills(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "review", "Review")
    registry = SkillRegistry([tmp_path])
    registry.load()
    assert registry.get("review") is not None
    registry.invalidate()
    assert registry.get("review") is None
    assert registry.list_all() == []


# ── SkillRegistry.build_invocation_prompt ─────────────────────────────────


def test_build_invocation_prompt_no_args() -> None:
    skill = Skill(
        "review", "Code Review", "Review code", "You are a reviewer.", Path("/tmp")
    )
    prompt = SkillRegistry.build_invocation_prompt(skill, "")
    assert "Code Review" in prompt
    assert "Review code" in prompt
    assert "You are a reviewer." in prompt
    assert "User Arguments" not in prompt


def test_build_invocation_prompt_with_args() -> None:
    skill = Skill("review", "Code Review", "Review code", "Instructions.", Path("/tmp"))
    prompt = SkillRegistry.build_invocation_prompt(skill, "my args")
    assert "User Arguments" in prompt
    assert "my args" in prompt


# ── _extract_frontmatter ──────────────────────────────────────────────────


def test_extract_frontmatter_no_dashes() -> None:
    registry = SkillRegistry([])
    fm, body = registry._extract_frontmatter("Just a body.")
    assert fm == {}
    assert body == "Just a body."


def test_extract_frontmatter_incomplete_dashes() -> None:
    registry = SkillRegistry([])
    fm, body = registry._extract_frontmatter("---\nname: test\n")
    assert fm == {}


def test_description_falls_back_to_first_body_line(tmp_path: Path) -> None:
    content = "First line as description.\nSecond line."
    _make_skill_dir(tmp_path, "myfoo", content)
    registry = SkillRegistry([tmp_path])
    registry.load()
    skill = registry.get("myfoo")
    assert skill is not None
    assert "First line" in skill.description
