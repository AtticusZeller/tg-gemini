"""Tests for commands.py — CommandLoader."""

from pathlib import Path

from tg_gemini.commands import CommandLoader, GeminiCommand


def _write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_loader(work_dir: Path) -> CommandLoader:
    return CommandLoader(work_dir)


# ── GeminiCommand dataclass ────────────────────────────────────────────────


def test_gemini_command_fields(tmp_path: Path) -> None:
    cmd = GeminiCommand(
        name="review",
        description="Review code",
        prompt="Review: {{args}}",
        source_path=tmp_path / "review.toml",
    )
    assert cmd.name == "review"
    assert cmd.description == "Review code"
    assert "{{args}}" in cmd.prompt


# ── CommandLoader.load ─────────────────────────────────────────────────────


def test_load_returns_zero_if_no_commands_dir(tmp_path: Path) -> None:
    loader = _make_loader(tmp_path)
    assert loader.load() == 0


def test_load_returns_zero_for_empty_commands_dir(tmp_path: Path) -> None:
    (tmp_path / ".gemini" / "commands").mkdir(parents=True)
    loader = _make_loader(tmp_path)
    assert loader.load() == 0


def test_load_parses_simple_toml(tmp_path: Path) -> None:
    _write_toml(
        tmp_path / ".gemini" / "commands" / "review.toml",
        'description = "Review code"\nprompt = "Review: {{args}}"',
    )
    loader = _make_loader(tmp_path)
    assert loader.load() == 1
    cmd = loader.get("review")
    assert cmd is not None
    assert cmd.name == "review"
    assert cmd.description == "Review code"


def test_load_replaces_colon_with_underscore(tmp_path: Path) -> None:
    """Nested toml: git/commit.toml → name='git_commit' (underscore, valid Telegram command)."""
    _write_toml(
        tmp_path / ".gemini" / "commands" / "git" / "commit.toml",
        'description = "Commit"\nprompt = "Do commit: {{args}}"',
    )
    loader = _make_loader(tmp_path)
    assert loader.load() == 1
    cmd = loader.get("git_commit")
    assert cmd is not None
    assert cmd.name == "git_commit"


def test_load_skips_toml_missing_prompt(tmp_path: Path) -> None:
    _write_toml(
        tmp_path / ".gemini" / "commands" / "bad.toml", 'description = "No prompt here"'
    )
    loader = _make_loader(tmp_path)
    assert loader.load() == 0


def test_load_multiple_commands(tmp_path: Path) -> None:
    for name in ("alpha", "beta", "gamma"):
        _write_toml(
            tmp_path / ".gemini" / "commands" / f"{name}.toml",
            f'description = "{name}"\nprompt = "Do {name}: {{{{args}}}}"',
        )
    loader = _make_loader(tmp_path)
    assert loader.load() == 3


def test_load_uses_default_description_if_missing(tmp_path: Path) -> None:
    _write_toml(
        tmp_path / ".gemini" / "commands" / "nodesc.toml", 'prompt = "Just do it"'
    )
    loader = _make_loader(tmp_path)
    loader.load()
    cmd = loader.get("nodesc")
    assert cmd is not None
    assert "nodesc" in cmd.description


# ── CommandLoader.get / list_all ──────────────────────────────────────────


def test_get_case_insensitive(tmp_path: Path) -> None:
    _write_toml(
        tmp_path / ".gemini" / "commands" / "review.toml",
        'description = "Review"\nprompt = "Review {{args}}"',
    )
    loader = _make_loader(tmp_path)
    loader.load()
    assert loader.get("REVIEW") is not None
    assert loader.get("Review") is not None


def test_get_returns_none_for_unknown(tmp_path: Path) -> None:
    loader = _make_loader(tmp_path)
    loader.load()
    assert loader.get("unknown") is None


def test_list_all_sorted(tmp_path: Path) -> None:
    for name in ("zebra", "apple", "mango"):
        _write_toml(
            tmp_path / ".gemini" / "commands" / f"{name}.toml",
            f'description = "{name}"\nprompt = "Do {name}"',
        )
    loader = _make_loader(tmp_path)
    loader.load()
    names = [c.name for c in loader.list_all()]
    assert names == sorted(names)


# ── CommandLoader.reload ──────────────────────────────────────────────────


def test_reload_clears_and_reloads(tmp_path: Path) -> None:
    _write_toml(
        tmp_path / ".gemini" / "commands" / "review.toml",
        'description = "Review"\nprompt = "Review {{args}}"',
    )
    loader = _make_loader(tmp_path)
    loader.load()
    assert loader.get("review") is not None
    # Remove the file and reload
    (tmp_path / ".gemini" / "commands" / "review.toml").unlink()
    loader.reload()
    assert loader.get("review") is None


# ── CommandLoader.expand_prompt ───────────────────────────────────────────


async def test_expand_prompt_replaces_args(tmp_path: Path) -> None:
    cmd = GeminiCommand("review", "Review", "Review: {{args}}", tmp_path / "r.toml")
    loader = _make_loader(tmp_path)
    result = await loader.expand_prompt(cmd, "my code")
    assert result == "Review: my code"


async def test_expand_prompt_appends_args_when_no_placeholder(tmp_path: Path) -> None:
    cmd = GeminiCommand("review", "Review", "Review code.", tmp_path / "r.toml")
    loader = _make_loader(tmp_path)
    result = await loader.expand_prompt(cmd, "extra args")
    assert result.endswith("extra args")
    assert "Review code." in result


async def test_expand_prompt_no_args(tmp_path: Path) -> None:
    cmd = GeminiCommand("review", "Review", "Static prompt.", tmp_path / "r.toml")
    loader = _make_loader(tmp_path)
    result = await loader.expand_prompt(cmd, "")
    assert result == "Static prompt."


async def test_expand_prompt_injects_file(tmp_path: Path) -> None:
    guide = tmp_path / "guide.md"
    guide.write_text("# Guide content")
    cmd = GeminiCommand("doc", "Doc", "Context: @{guide.md}", tmp_path / "d.toml")
    loader = CommandLoader(tmp_path)
    result = await loader.expand_prompt(cmd, "")
    assert "# Guide content" in result


async def test_expand_prompt_file_not_found(tmp_path: Path) -> None:
    cmd = GeminiCommand("doc", "Doc", "Context: @{missing.md}", tmp_path / "d.toml")
    loader = CommandLoader(tmp_path)
    result = await loader.expand_prompt(cmd, "")
    assert "[File not found:" in result


async def test_expand_prompt_shell_command(tmp_path: Path) -> None:
    cmd = GeminiCommand("sh", "Shell", "Output: !{echo hello}", tmp_path / "s.toml")
    loader = CommandLoader(tmp_path)
    result = await loader.expand_prompt(cmd, "")
    assert "hello" in result


async def test_expand_prompt_shell_command_failure(tmp_path: Path) -> None:
    cmd = GeminiCommand("sh", "Shell", "!{exit 1}", tmp_path / "s.toml")
    loader = CommandLoader(tmp_path)
    result = await loader.expand_prompt(cmd, "")
    assert "exit code: 1" in result
