"""Tests for tg_gemini.config module."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from tg_gemini.config import (
    AppConfig,
    DisplayConfig,
    GeminiConfig,
    LogConfig,
    StreamPreviewConfig,
    TelegramConfig,
    load_config,
    resolve_config_path,
)

# ── strict validation ──────────────────────────────────────────────────────


class TestTelegramConfig:
    """Tests for TelegramConfig model."""

    def test_token_required(self) -> None:
        """Test that token is required."""
        with pytest.raises(ValidationError) as exc_info:
            TelegramConfig()  # type: ignore[call-arg]
        assert "token" in str(exc_info.value)

    def test_token_provided(self) -> None:
        """Test creation with token provided."""
        config = TelegramConfig(token="test_token_123")
        assert config.token == "test_token_123"
        assert config.allow_from == "*"  # default

    def test_allow_from_custom(self) -> None:
        """Test custom allow_from value."""
        config = TelegramConfig(token="test_token", allow_from="user1,user2")
        assert config.allow_from == "user1,user2"


class TestGeminiConfig:
    """Tests for GeminiConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = GeminiConfig()
        assert config.work_dir == "."
        assert config.model == ""
        assert config.mode == "default"
        assert config.api_key == ""
        assert config.cmd == "gemini"
        assert config.timeout_mins == 0

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = GeminiConfig(
            work_dir="/tmp/work",
            model="gemini-pro",
            mode="auto_edit",
            api_key="secret_key",
            cmd="gemini-dev",
            timeout_mins=30,
        )
        assert config.work_dir == "/tmp/work"
        assert config.model == "gemini-pro"
        assert config.mode == "auto_edit"
        assert config.api_key == "secret_key"
        assert config.cmd == "gemini-dev"
        assert config.timeout_mins == 30


class TestDisplayConfig:
    """Tests for DisplayConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = DisplayConfig()
        assert config.thinking_max_len == 300
        assert config.tool_max_len == 500

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = DisplayConfig(thinking_max_len=500, tool_max_len=1000)
        assert config.thinking_max_len == 500
        assert config.tool_max_len == 1000


class TestStreamPreviewConfig:
    """Tests for StreamPreviewConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = StreamPreviewConfig()
        assert config.enabled is True
        assert config.interval_ms == 1500
        assert config.min_delta_chars == 30
        assert config.max_chars == 2000

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = StreamPreviewConfig(
            enabled=False, interval_ms=500, min_delta_chars=10, max_chars=1000
        )
        assert config.enabled is False
        assert config.interval_ms == 500
        assert config.min_delta_chars == 10
        assert config.max_chars == 1000


class TestLogConfig:
    """Tests for LogConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = LogConfig()
        assert config.level == "INFO"

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = LogConfig(level="DEBUG")
        assert config.level == "DEBUG"


class TestAppConfig:
    """Tests for AppConfig model."""

    def test_telegram_required(self) -> None:
        """Test that telegram config is required."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig()  # type: ignore[call-arg]
        assert "telegram" in str(exc_info.value)

    def test_defaults(self) -> None:
        """Test default values for optional fields."""
        telegram = TelegramConfig(token="test_token")
        config = AppConfig(telegram=telegram)
        assert config.data_dir == "~/.tg-gemini"
        assert config.language == ""
        assert isinstance(config.gemini, GeminiConfig)
        assert isinstance(config.log, LogConfig)
        assert isinstance(config.display, DisplayConfig)
        assert isinstance(config.stream_preview, StreamPreviewConfig)

    def test_custom_values(self) -> None:
        """Test custom values."""
        telegram = TelegramConfig(token="test_token")
        gemini = GeminiConfig(model="gemini-pro")
        log = LogConfig(level="DEBUG")
        display = DisplayConfig(thinking_max_len=500)
        stream_preview = StreamPreviewConfig(enabled=False)
        config = AppConfig(
            telegram=telegram,
            gemini=gemini,
            data_dir="/custom/data",
            language="zh",
            log=log,
            display=display,
            stream_preview=stream_preview,
        )
        assert config.telegram.token == "test_token"
        assert config.gemini.model == "gemini-pro"
        assert config.data_dir == "/custom/data"
        assert config.language == "zh"
        assert config.log.level == "DEBUG"
        assert config.display.thinking_max_len == 500
        assert config.stream_preview.enabled is False


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Test loading a valid TOML config file."""
        config_file = tmp_path / "config.toml"
        config_content = """
data_dir = "~/.tg-gemini"
language = "en"

[telegram]
token = "my_bot_token"
allow_from = "user1,user2"

[gemini]
model = "gemini-pro"
mode = "auto_edit"
work_dir = "/tmp/work"
"""
        config_file.write_text(config_content)

        config = load_config(config_file)
        assert config.telegram.token == "my_bot_token"
        assert config.telegram.allow_from == "user1,user2"
        assert config.gemini.model == "gemini-pro"
        assert config.gemini.mode == "auto_edit"
        assert config.gemini.work_dir == "/tmp/work"

    def test_load_minimal_config(self, tmp_path: Path) -> None:
        """Test loading a minimal TOML config with only required fields."""
        config_file = tmp_path / "config.toml"
        config_content = """
[telegram]
token = "minimal_token"
"""
        config_file.write_text(config_content)

        config = load_config(config_file)
        assert config.telegram.token == "minimal_token"
        assert config.telegram.allow_from == "*"
        assert config.gemini.model == ""
        assert config.gemini.mode == "default"

    def test_load_invalid_config_missing_telegram(self, tmp_path: Path) -> None:
        """Test loading config without required telegram section."""
        config_file = tmp_path / "config.toml"
        config_content = """
[gemini]
model = "gemini-pro"
"""
        config_file.write_text(config_content)

        with pytest.raises(ValidationError) as exc_info:
            load_config(config_file)
        assert "telegram" in str(exc_info.value)


class TestResolveConfigPath:
    """Tests for resolve_config_path function."""

    def test_explicit_path(self) -> None:
        """Test that explicit path is returned as-is."""
        explicit = "/custom/path/config.toml"
        result = resolve_config_path(explicit)
        assert result == Path("/custom/path/config.toml")

    def test_local_config_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that local config.toml is used when it exists."""
        # Create a config.toml in tmp_path
        config_file = tmp_path / "config.toml"
        config_file.write_text("[telegram]\ntoken = 'test'\n")

        # Change to tmp_path
        monkeypatch.chdir(tmp_path)

        result = resolve_config_path(None)
        assert result == Path("config.toml")
        assert result.exists()

    def test_local_config_not_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fallback to default path when local config doesn't exist."""
        # Change to tmp_path (which has no config.toml)
        monkeypatch.chdir(tmp_path)

        result = resolve_config_path(None)
        expected = Path.home() / ".tg-gemini" / "config.toml"
        assert result == expected

    def test_none_explicit_no_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that None explicit and no local config returns default path."""
        # Change to tmp_path (which has no config.toml)
        monkeypatch.chdir(tmp_path)

        result = resolve_config_path(None)
        assert result == Path.home() / ".tg-gemini" / "config.toml"


# ── Literal / constraint validation ───────────────────────────────────────


class TestGeminiMode:
    def test_valid_modes(self) -> None:
        for mode in ("default", "auto_edit", "yolo", "plan"):
            assert GeminiConfig(mode=mode).mode == mode  # type: ignore[arg-type]

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError, match="mode"):
            GeminiConfig(mode="turbo")  # type: ignore[arg-type]


class TestLogLevel:
    def test_valid_levels(self) -> None:
        for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            assert LogConfig(level=lvl).level == lvl  # type: ignore[arg-type]

    def test_invalid_level_rejected(self) -> None:
        with pytest.raises(ValidationError, match="level"):
            LogConfig(level="VERBOSE")  # type: ignore[arg-type]


class TestAppLanguage:
    def test_valid_languages(self) -> None:
        tg = TelegramConfig(token="t")
        for lang in ("", "en", "zh"):
            assert AppConfig(telegram=tg, language=lang).language == lang  # type: ignore[arg-type]

    def test_invalid_language_rejected(self) -> None:
        with pytest.raises(ValidationError, match="language"):
            AppConfig(telegram=TelegramConfig(token="t"), language="fr")  # type: ignore[arg-type]


class TestNumericConstraints:
    def test_timeout_mins_zero_allowed(self) -> None:
        assert GeminiConfig(timeout_mins=0).timeout_mins == 0

    def test_timeout_mins_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GeminiConfig(timeout_mins=-1)

    def test_thinking_max_len_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            DisplayConfig(thinking_max_len=0)

    def test_tool_max_len_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            DisplayConfig(tool_max_len=-5)

    def test_interval_ms_zero_allowed(self) -> None:
        assert StreamPreviewConfig(interval_ms=0).interval_ms == 0

    def test_max_chars_zero_allowed(self) -> None:
        # 0 = no truncation
        assert StreamPreviewConfig(max_chars=0).max_chars == 0

    def test_max_chars_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StreamPreviewConfig(max_chars=-1)


class TestExtraFieldsForbidden:
    def test_telegram_config_rejects_extra(self) -> None:
        with pytest.raises(ValidationError):
            TelegramConfig(token="t", unknown_field="x")  # type: ignore[call-arg]

    def test_gemini_config_rejects_extra(self) -> None:
        with pytest.raises(ValidationError):
            GeminiConfig(unknown_key="x")  # type: ignore[call-arg]

    def test_app_config_rejects_extra(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(telegram=TelegramConfig(token="t"), extra_key="x")  # type: ignore[call-arg]

    def test_load_config_rejects_unknown_toml_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('[telegram]\ntoken = "t"\n\n[gemini]\nunknown_key = "x"\n')
        with pytest.raises(ValidationError):
            load_config(cfg)


class TestFrozenImmutability:
    def test_config_is_immutable(self) -> None:
        config = GeminiConfig(model="flash")
        with pytest.raises(Exception):  # noqa: B017
            config.model = "pro"  # type: ignore[misc]
