"""Configuration loading and validation for tg-gemini."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

__all__ = [
    "AppConfig",
    "DisplayConfig",
    "GeminiConfig",
    "LogConfig",
    "StreamPreviewConfig",
    "TelegramConfig",
    "load_config",
    "resolve_config_path",
]


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""

    token: str
    allow_from: str = "*"


class GeminiConfig(BaseModel):
    """Gemini CLI configuration."""

    work_dir: str = "."
    model: str = ""
    mode: str = "default"  # default | auto_edit | yolo | plan
    api_key: str = ""
    cmd: str = "gemini"
    timeout_mins: int = 0


class DisplayConfig(BaseModel):
    """Display/formatting configuration."""

    thinking_max_len: int = 300
    tool_max_len: int = 500


class StreamPreviewConfig(BaseModel):
    """Stream preview update configuration."""

    enabled: bool = True
    interval_ms: int = 1500
    min_delta_chars: int = 30
    max_chars: int = 2000


class LogConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"


class AppConfig(BaseModel):
    """Root application configuration."""

    telegram: TelegramConfig
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    data_dir: str = "~/.tg-gemini"
    language: str = ""  # "" = auto-detect, "en", "zh"
    log: LogConfig = Field(default_factory=LogConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    stream_preview: StreamPreviewConfig = Field(default_factory=StreamPreviewConfig)


def load_config(path: Path) -> AppConfig:
    """Load configuration from a TOML file.

    Args:
        path: Path to the TOML configuration file.

    Returns:
        Parsed and validated AppConfig instance.
    """
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return AppConfig(**raw)


def resolve_config_path(explicit: str | None) -> Path:
    """Resolve the configuration file path.

    Checks in order:
    1. Explicit path if provided
    2. Local config.toml in current directory
    3. Default path at ~/.tg-gemini/config.toml

    Args:
        explicit: Optional explicit path provided by user.

    Returns:
        Resolved Path to the configuration file.
    """
    if explicit:
        return Path(explicit)
    local = Path("config.toml")
    if local.exists():
        return local
    return Path.home() / ".tg-gemini" / "config.toml"
