"""Tests for cli.py: typer entry point."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from tg_gemini.cli import app


def _ki_run(coro: Any, **_: Any) -> None:
    """Mock for asyncio.run that closes any coroutine and raises KeyboardInterrupt."""
    if hasattr(coro, "close"):
        coro.close()
    raise KeyboardInterrupt


runner = CliRunner()


def test_start_missing_config(tmp_path: Path) -> None:
    """start exits with error when config file doesn't exist."""
    result = runner.invoke(app, ["--config", str(tmp_path / "nonexistent.toml")])
    assert result.exit_code != 0
    assert "not found" in result.output or "Config" in result.output


def test_start_with_valid_config(tmp_path: Path) -> None:
    """start runs engine.start() when config is valid."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[telegram]\ntoken = "123:ABC"\n\n[gemini]\n')

    with (
        patch("tg_gemini.engine.Engine"),
        patch("tg_gemini.gemini.GeminiAgent"),
        patch("tg_gemini.telegram_platform.TelegramPlatform"),
        patch("tg_gemini.session.SessionManager"),
        patch("asyncio.run", side_effect=_ki_run),
    ):
        result = runner.invoke(app, ["--config", str(config_file)])
        assert result.exit_code == 0


def test_start_keyboard_interrupt(tmp_path: Path) -> None:
    """start handles KeyboardInterrupt gracefully."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[telegram]\ntoken = "123:ABC"\n\n[gemini]\n')

    with patch("asyncio.run", side_effect=_ki_run):
        result = runner.invoke(app, ["--config", str(config_file)])
        assert result.exit_code == 0


def test_start_default_config_path_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """start without --config and no default config exits with error."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, [])
    assert result.exit_code != 0


def test_start_with_language_zh(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[telegram]\ntoken = "123:ABC"\n\n[gemini]\n\nlanguage = "zh"\n'
    )

    with patch("asyncio.run", side_effect=_ki_run):
        result = runner.invoke(app, ["--config", str(config_file)])
        assert result.exit_code == 0


def test_start_with_language_invalid(tmp_path: Path) -> None:
    """Unknown language falls back to EN."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[telegram]\ntoken = "123:ABC"\n\n[gemini]\n\nlanguage = "fr"\n'
    )

    with patch("asyncio.run", side_effect=_ki_run):
        result = runner.invoke(app, ["--config", str(config_file)])
        assert result.exit_code == 0


def test_start_short_flag_missing(tmp_path: Path) -> None:
    """Test -c short flag with nonexistent file."""
    result = runner.invoke(app, ["-c", str(tmp_path / "nonexistent.toml")])
    assert result.exit_code != 0
    assert "not found" in result.output or "Config" in result.output


def test_start_creates_data_dir(tmp_path: Path) -> None:
    """start creates data dir if it doesn't exist."""

    config_file = tmp_path / "config.toml"
    data_dir = tmp_path / "data" / "tg-gemini"
    # Root-level keys in TOML must come before any [section] header
    config_file.write_text(
        f'data_dir = "{data_dir}"\n\n[telegram]\ntoken = "123:ABC"\n\n[gemini]\n'
    )

    # Patch Engine so asyncio.run can actually run (but start() does nothing)
    with patch("tg_gemini.engine.Engine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.start = AsyncMock(return_value=None)
        mock_engine_cls.return_value = mock_engine
        result = runner.invoke(app, ["--config", str(config_file)])
        assert result.exit_code == 0
        assert data_dir.exists()
