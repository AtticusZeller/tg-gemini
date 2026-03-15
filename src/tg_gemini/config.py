import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Model Aliases and Actual Names
# Reference: gemini-cli model selection
MODEL_ALIASES = {
    "auto": "gemini-2.5-pro / gemini-3.1-pro-preview",
    "pro": "gemini-2.5-pro / gemini-3.1-pro-preview",
    "flash": "gemini-2.5-flash",
    "flash-lite": "gemini-2.5-flash-lite",
}

SUPPORTED_MODELS = frozenset(
    {
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        *MODEL_ALIASES.keys(),
    }
)

VALID_APPROVAL_MODES = frozenset({"default", "auto_edit", "yolo"})

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "tg-gemini" / "config.toml"


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    allowed_user_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class GeminiConfig:
    model: str = "auto"
    approval_mode: str = "default"
    working_dir: str = "."


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    gemini: GeminiConfig = field(default_factory=GeminiConfig)


def _validate_config(data: dict[str, Any]) -> None:
    telegram = data.get("telegram")
    if not isinstance(telegram, dict) or "bot_token" not in telegram:
        msg = "Config error: 'telegram.bot_token' is required"
        raise ValueError(msg)

    gemini = data.get("gemini", {})
    approval_mode = gemini.get("approval_mode", "default")
    if approval_mode not in VALID_APPROVAL_MODES:
        msg = f"Config error: 'gemini.approval_mode' must be one of {sorted(VALID_APPROVAL_MODES)}, got '{approval_mode}'"
        raise ValueError(msg)

    model = gemini.get("model", "auto")
    if model not in SUPPORTED_MODELS:
        msg = (
            f"Config error: 'gemini.model' must be one of {sorted(SUPPORTED_MODELS)}, got '{model}'"
        )
        raise ValueError(msg)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    _validate_config(data)

    telegram_data = data["telegram"]
    telegram = TelegramConfig(
        bot_token=telegram_data["bot_token"],
        allowed_user_ids=telegram_data.get("allowed_user_ids", []),
    )

    gemini_data = data.get("gemini", {})
    gemini = GeminiConfig(
        model=gemini_data.get("model", "auto"),
        approval_mode=gemini_data.get("approval_mode", "default"),
        working_dir=gemini_data.get("working_dir", "."),
    )

    return AppConfig(telegram=telegram, gemini=gemini)
