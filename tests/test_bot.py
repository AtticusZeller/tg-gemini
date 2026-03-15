from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Message, User

from tg_gemini.bot import (
    SessionManager,
    _is_authorized,
    _process_stream,
    _resolve_id,
    _throttle_update,
    _update_ui,
    cmd_current,
    cmd_delete,
    cmd_list,
    cmd_model,
    cmd_name,
    cmd_new,
    cmd_resume,
    cmd_start,
    cmd_status,
    handle_message,
    start_bot,
)
from tg_gemini.config import AppConfig, GeminiConfig, TelegramConfig
from tg_gemini.events import ErrorEvent, InitEvent, MessageEvent, ResultEvent, ToolUseEvent
from tg_gemini.gemini import SessionInfo

VALID_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"  # noqa: S105


def test_session_manager() -> None:
    sm = SessionManager()
    s1 = sm.get(1)
    s2 = sm.get(1)
    assert s1 is s2
    assert s1.active is True


def test_is_authorized() -> None:
    assert _is_authorized(123, []) is True
    assert _is_authorized(123, [123, 456]) is True
    assert _is_authorized(123, [456]) is False


@pytest.mark.asyncio
async def test_cmd_start() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    await cmd_start(message, sessions)
    assert sessions.get(1).active is True
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_start_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_start(message, SessionManager())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_new() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    sessions.get(1).session_id = "old"

    # Without name
    command = MagicMock()
    command.args = None
    await cmd_new(message, command, sessions)
    assert sessions.get(1).session_id is None
    assert sessions.get(1).pending_name is None

    # With name
    command.args = "New Session"
    await cmd_new(message, command, sessions)
    assert sessions.get(1).pending_name == "New Session"


@pytest.mark.asyncio
async def test_cmd_new_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_new(message, MagicMock(), SessionManager())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_list() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    agent = AsyncMock()

    # Empty
    agent.list_sessions.return_value = []
    await cmd_list(message, sessions, agent)
    assert "No sessions" in message.answer.call_args[0][0]

    # Success with custom name
    sessions.get(1).custom_names = {"id-a": "My Name"}
    agent.list_sessions.return_value = [SessionInfo(1, "Title A", "10m ago", "id-a")]
    await cmd_list(message, sessions, agent)
    assert len(sessions.get(1).last_sessions) == 1
    assert "My Name" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_list_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_list(message, SessionManager(), AsyncMock())
    message.answer.assert_not_called()


def test_resolve_id() -> None:
    sessions = [SessionInfo(1, "T", "t", "id-1")]
    assert _resolve_id("1", sessions) == "id-1"
    assert _resolve_id("2", sessions) == "2"  # Not found
    assert _resolve_id("id-2", sessions) == "id-2"
    assert _resolve_id("not-digit", sessions) == "not-digit"


@pytest.mark.asyncio
async def test_cmd_current() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))
    await cmd_current(message, sessions, config)
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_current_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_current(message, SessionManager(), MagicMock())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_name() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()

    # No session
    command = MagicMock()
    command.args = "New Name"
    await cmd_name(message, command, sessions)
    assert "No active session" in message.answer.call_args[0][0]

    # No args
    sessions.get(1).session_id = "id-1"
    command.args = None
    await cmd_name(message, command, sessions)
    assert "Usage" in message.answer.call_args[0][0]

    # Success
    command.args = "My Session"
    await cmd_name(message, command, sessions)
    assert sessions.get(1).custom_names["id-1"] == "My Session"


@pytest.mark.asyncio
async def test_cmd_name_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_name(message, MagicMock(), SessionManager())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_resume() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()

    # Latest
    command = MagicMock()
    command.args = None
    await cmd_resume(message, command, sessions)
    assert sessions.get(1).session_id == "latest"

    # By Index
    sessions.get(1).last_sessions = [SessionInfo(1, "T", "t", "id-1")]
    command.args = "1"
    await cmd_resume(message, command, sessions)
    assert sessions.get(1).session_id == "id-1"


@pytest.mark.asyncio
async def test_cmd_resume_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_resume(message, MagicMock(), SessionManager())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_delete_success() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()

    # Active session
    sessions.get(1).session_id = "id-1"
    sessions.get(1).last_sessions = [SessionInfo(1, "T", "t", "id-1")]
    sessions.get(1).custom_names = {"id-1": "Name"}
    agent = AsyncMock()
    agent.delete_session.return_value = True
    command = MagicMock()
    command.args = "1"
    await cmd_delete(message, command, sessions, agent)
    assert sessions.get(1).session_id is None
    assert "id-1" not in sessions.get(1).custom_names

    # Non-active session
    sessions.get(1).session_id = "id-active"
    sessions.get(1).last_sessions = [SessionInfo(2, "T", "t", "id-2")]
    command.args = "2"
    await cmd_delete(message, command, sessions, agent)
    assert sessions.get(1).session_id == "id-active"


@pytest.mark.asyncio
async def test_cmd_delete_fail() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()

    agent = AsyncMock()
    agent.delete_session.return_value = False

    command = MagicMock()
    command.args = "id-x"
    await cmd_delete(message, command, SessionManager(), agent)
    assert "Failed" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_delete_no_args() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    command = MagicMock()
    command.args = None
    await cmd_delete(message, command, SessionManager(), AsyncMock())
    assert "Usage" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_delete_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_delete(message, MagicMock(), SessionManager(), AsyncMock())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_model() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()

    # No args
    command = MagicMock()
    command.args = None
    await cmd_model(message, command, sessions)
    assert "Usage" in message.answer.call_args[0][0]

    # With args
    command.args = "pro"
    await cmd_model(message, command, sessions)
    assert sessions.get(1).model == "pro"
    assert "Model set to: pro" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_model_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_model(message, MagicMock(), SessionManager())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_status() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))
    await cmd_status(message, sessions, config)
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_status_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_status(message, SessionManager(), MagicMock())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_throttle_update_no_update() -> None:
    reply = AsyncMock()
    res_time, res_len = await _throttle_update(reply, "acc", [], 0.0, 0)
    assert res_time == 0.0
    assert res_len == 0
    reply.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_flow() -> None:
    user = User(id=1, is_bot=False, first_name="Test")
    chat = Chat(id=1, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.text = "hello"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    # Test pending name
    sessions.get(1).pending_name = "Assigned Name"

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield InitEvent(session_id="new_id", model="gemini-pro")
        # Not assistant
        yield MessageEvent(role="user", content="hi")
        # msg 1: trigger update
        yield MessageEvent(role="assistant", content="a" * 300, delta=True)
        # msg 2: skip update (diffs relative to msg 1)
        yield MessageEvent(role="assistant", content="b", delta=True)
        # Full content replacement (delta=False)
        yield MessageEvent(role="assistant", content="final content", delta=False)
        # Result with stats
        from tg_gemini.events import ResultEvent, StreamStats
        yield ResultEvent(
            status="success",
            stats=StreamStats(
                total_tokens=100,
                input_tokens=50,
                output_tokens=50,
                cached=0,
                input=50,
                duration_ms=1000,
                tool_calls=0,
                models={}
            )
        )

    agent.run_stream = mock_stream
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))

    # sequence: start=0, loop1=5, loop2=6, loop3=7...
    t_vals = [0.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
    t_idx = 0

    def mock_monotonic() -> float:
        nonlocal t_idx
        v = t_vals[t_idx % len(t_vals)]
        t_idx += 1
        return v

    with (
        patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()),
        patch("time.monotonic", side_effect=mock_monotonic),
    ):
        await handle_message(message, sessions, agent, config)

    assert sessions.get(1).session_id == "new_id"
    assert sessions.get(1).custom_names["new_id"] == "Assigned Name"
    assert sessions.get(1).pending_name is None
    assert reply.edit_text.call_count >= 1


@pytest.mark.asyncio
async def test_handle_message_tool_use() -> None:
    user = User(id=1, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = Chat(id=1, type="private")
    message.text = "hello"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield ToolUseEvent(tool_name="bash", tool_id="1", parameters={})
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await handle_message(message, sessions, agent, AppConfig(TelegramConfig(VALID_TOKEN)))

    assert "🔧 bash" in reply.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_message_tool_result() -> None:
    user = User(id=1, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = Chat(id=1, type="private")
    message.text = "hello"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        from tg_gemini.events import ToolResultEvent
        yield ToolUseEvent(tool_name="bash", tool_id="call_1", parameters={})
        yield ToolResultEvent(tool_id="call_1", status="success")
        yield ToolUseEvent(tool_name="python", tool_id="call_2", parameters={})
        yield ToolResultEvent(tool_id="call_2", status="error")
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await handle_message(message, sessions, agent, AppConfig(TelegramConfig(VALID_TOKEN)))

    # Final UI update should have ✅ and ❌
    final_text = reply.edit_text.call_args[0][0]
    assert "✅ bash" in final_text
    assert "❌ python" in final_text


@pytest.mark.asyncio
async def test_handle_message_no_response() -> None:
    user = User(id=1, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = Chat(id=1, type="private")
    message.text = "hello"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        if False:
            yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await handle_message(message, sessions, agent, AppConfig(TelegramConfig(VALID_TOKEN)))

    assert "No response" in reply.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_message_error() -> None:
    user = User(id=1, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = Chat(id=1, type="private")
    message.text = "hello"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield ErrorEvent(severity="error", message="failed")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await handle_message(message, sessions, agent, AppConfig(TelegramConfig(VALID_TOKEN)))

    assert "Error: failed" in reply.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_message_no_user_or_text() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    message.text = None
    await handle_message(message, SessionManager(), AsyncMock(), MagicMock())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_unauthorized() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="T")
    message.text = "h"
    config = AppConfig(TelegramConfig(VALID_TOKEN, allowed_user_ids=[999]))
    await handle_message(message, SessionManager(), AsyncMock(), config)
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_inactive() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="T")
    message.text = "h"
    sessions = SessionManager()
    sessions.get(1).active = False
    await handle_message(message, sessions, AsyncMock(), AppConfig(TelegramConfig(VALID_TOKEN)))
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_process_stream_unhandled_event() -> None:
    user = User(id=1, is_bot=False, first_name="T")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = Chat(id=1, type="private")
    message.text = "h"
    message.bot = MagicMock()
    reply = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        # Initial event
        yield InitEvent(session_id="id", model="m")
        # message role != assistant
        yield MessageEvent(role="user", content="u")
        # unknown event type (will be ignored by bot logic)
        from pydantic import BaseModel
        class UnknownEvent(BaseModel):
            type: str = "unknown"
        yield UnknownEvent()  # type: ignore
        # tool use
        yield ToolUseEvent(tool_name="t", tool_id="i", parameters={})
        # tool result with unknown tool_id (covers line 273 branch)
        from tg_gemini.events import ToolResultEvent
        yield ToolResultEvent(tool_id="unknown_id", status="success")
        # error
        yield ErrorEvent(severity="error", message="e")
        # result (fallthrough)
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await _process_stream(message, SessionManager().get(1), agent)


@pytest.mark.asyncio
async def test_process_stream_no_bot() -> None:
    message = MagicMock(spec=Message)
    message.bot = None
    res_acc, res_status = await _process_stream(message, MagicMock(), AsyncMock())
    assert res_acc == ""
    assert res_status == []


@pytest.mark.asyncio
async def test_update_ui_thinking() -> None:
    reply = MagicMock()
    reply.edit_text = AsyncMock()
    await _update_ui(reply, "", [])
    assert "Thinking..." in reply.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_update_ui_exception() -> None:
    reply = MagicMock()
    reply.edit_text = AsyncMock(side_effect=Exception("telegram error"))
    # Should not raise
    await _update_ui(reply, "text", ["status"])


@pytest.mark.asyncio
async def test_start_bot() -> None:
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))
    with patch("tg_gemini.bot.Dispatcher.start_polling", new_callable=AsyncMock) as mock_poll:
        await start_bot(config)
        mock_poll.assert_called_once()
