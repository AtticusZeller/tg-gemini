from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from tg_gemini.cli import app, main

runner = CliRunner()

VALID_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"  # noqa: S105


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "tg-gemini" in result.stdout


def test_cli_check_config_valid(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f"[telegram]\nbot_token = '{VALID_TOKEN}'\n[gemini]\nmodel = 'pro'")
    result = runner.invoke(app, ["check-config", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "Config OK" in result.stdout


def test_cli_check_config_invalid(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[gemini]\nmodel = 'pro'")
    result = runner.invoke(app, ["check-config", "--config", str(cfg_file)])
    assert result.exit_code == 1
    assert "Config error" in result.stderr


def test_cli_start_error_validation(tmp_path: Path) -> None:
    result = runner.invoke(app, ["start", "--config", str(tmp_path / "missing.toml")])
    usage_error_code = 2
    assert result.exit_code == usage_error_code


def test_cli_start_error_runtime(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f"[telegram]\nbot_token = '{VALID_TOKEN}'\n[gemini]\nmodel = 'pro'")
    with patch("tg_gemini.cli.start_bot", side_effect=RuntimeError("boom")):
        result = runner.invoke(app, ["start", "--config", str(cfg_file)])
        assert result.exit_code == 1
        assert "Error: boom" in result.stderr


def test_cli_start_success(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f"[telegram]\nbot_token = '{VALID_TOKEN}'\n[gemini]\nmodel = 'pro'")
    with patch("tg_gemini.cli.start_bot") as mock_start:
        result = runner.invoke(app, ["start", "--config", str(cfg_file)])
        assert result.exit_code == 0
        assert "Starting bot" in result.stdout
        mock_start.assert_called_once()


def test_cli_main_entry() -> None:
    with patch("tg_gemini.cli.app") as mock_app:
        main()
        mock_app.assert_called_once()
