from pathlib import Path

import pytest

from tg_gemini.config import load_config


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.toml")


def test_load_config_invalid_telegram(tmp_path: Path) -> None:
    cfg_file = tmp_path / "invalid.toml"
    cfg_file.write_text("[gemini]\nmodel = 'auto'")
    with pytest.raises(ValueError, match="'telegram.bot_token' is required"):
        load_config(cfg_file)


def test_load_config_invalid_approval_mode(tmp_path: Path) -> None:
    cfg_file = tmp_path / "invalid.toml"
    cfg_file.write_text("[telegram]\nbot_token = 'token'\n[gemini]\napproval_mode = 'invalid'")
    with pytest.raises(ValueError, match="must be one of"):
        load_config(cfg_file)


def test_load_config_invalid_model(tmp_path: Path) -> None:
    cfg_file = tmp_path / "invalid.toml"
    cfg_file.write_text("[telegram]\nbot_token = 'token'\n[gemini]\nmodel = 'invalid-model'")
    with pytest.raises(ValueError, match="must be one of"):
        load_config(cfg_file)


def test_load_config_valid(tmp_path: Path) -> None:
    cfg_file = tmp_path / "valid.toml"
    token = "123:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"  # noqa: S105
    cfg_file.write_text(
        f"[telegram]\nbot_token = '{token}'\nallowed_user_ids = [123]\n[gemini]\nmodel = 'pro'\napproval_mode = 'yolo'\nworking_dir = '.'"
    )
    cfg = load_config(cfg_file)
    assert cfg.telegram.bot_token == token
    assert cfg.telegram.allowed_user_ids == [123]
    assert cfg.gemini.model == "pro"
    assert cfg.gemini.approval_mode == "yolo"
    assert cfg.gemini.working_dir == "."
