import pytest

from tg_gemini.config import AppConfig, GeminiConfig, TelegramConfig


@pytest.fixture
def sample_config() -> AppConfig:
    return AppConfig(
        telegram=TelegramConfig(
            bot_token="123:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",  # noqa: S106
            allowed_user_ids=[42],
        ),
        gemini=GeminiConfig(model="flash", approval_mode="default", working_dir="."),
    )
