from unittest.mock import MagicMock

import pytest

from tg_gemini.bot import SessionManager
from tg_gemini.config import AppConfig, GeminiConfig, TelegramConfig


@pytest.fixture
def sample_config() -> AppConfig:
    return AppConfig(
        telegram=TelegramConfig(
            bot_token="123:ABC-DEF1234ghIkl-zyx57W2v1u123ew11", allowed_user_ids=[42]
        ),
        gemini=GeminiConfig(model="flash", approval_mode="default", working_dir="."),
    )


@pytest.fixture
def mock_store() -> MagicMock:
    from tg_gemini.sessions import SessionStore

    return MagicMock(spec=SessionStore)


@pytest.fixture
def mock_sessions(mock_store: MagicMock) -> SessionManager:
    return SessionManager(mock_store)
