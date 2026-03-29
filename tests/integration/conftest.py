"""Shared fixtures for integration tests against committed (HEAD) bot.py."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram.types import Chat, User

from tg_gemini.bot import SessionManager
from tg_gemini.config import AppConfig, GeminiConfig, TelegramConfig
from tg_gemini.events import MessageEvent, ResultEvent, StreamStats, ToolResultEvent, ToolUseEvent
from tg_gemini.gemini import GeminiAgent
from tg_gemini.sessions import SessionStore


@pytest.fixture
def user_id() -> int:
    return 42


@pytest.fixture
def telegram_user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="Test", last_name="User")


@pytest.fixture
def chat() -> Chat:
    return Chat(id=1, type="private")


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        telegram=TelegramConfig(
            bot_token="123:ABC",  # noqa: S106
            allowed_user_ids=[42],
        ),
        gemini=GeminiConfig(model="flash", approval_mode="default", working_dir="."),
    )


@pytest.fixture
def mock_store() -> MagicMock:
    return MagicMock(spec=SessionStore)


@pytest.fixture
def sessions(mock_store: MagicMock) -> SessionManager:
    return SessionManager(mock_store)


@pytest.fixture
def mock_agent() -> MagicMock:
    return MagicMock(spec=GeminiAgent)


def make_message_event(content: str, *, delta: bool = False) -> MessageEvent:
    return MessageEvent(role="assistant", content=content, delta=delta)


def make_tool_use(
    tool_id: str = "c1", tool_name: str = "read_file", parameters: dict[str, Any] | None = None
) -> ToolUseEvent:
    return ToolUseEvent(
        tool_id=tool_id, tool_name=tool_name, parameters=parameters or {"file_path": "f.txt"}
    )


def make_tool_result(
    tool_id: str = "c1", status: str = "success", output: str | None = None
) -> ToolResultEvent:
    return ToolResultEvent(tool_id=tool_id, status=status, output=output)


def make_result(status: str = "success", tokens: int = 100) -> ResultEvent:
    stats = StreamStats(
        total_tokens=tokens,
        input_tokens=50,
        output_tokens=50,
        cached=0,
        _input=50,
        duration_ms=1000,
        tool_calls=0,
        models={},
    )
    return ResultEvent(status=status, stats=stats)
