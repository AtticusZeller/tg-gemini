import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from tg_gemini.bot import (
    SessionManager,
    UserSession,
    _build_model_keyboard,
    _build_session_keyboard,
    _build_stop_button,
    _edit_reply,
    _format_session_list,
    _format_tool_html,
    _handle_event,
    _process_stream,
    _resolve_id,
    _send_final,
    _send_new,
    _StreamState,
    _throttle_edit,
    callback_delete,
    callback_model,
    callback_noop,
    callback_resume,
    callback_stop,
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
from tg_gemini.events import (
    ErrorEvent,
    InitEvent,
    MessageEvent,
    ResultEvent,
    StreamStats,
    ToolResultEvent,
    ToolUseEvent,
)
from tg_gemini.gemini import SessionInfo

VALID_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"  # noqa: S105


@pytest.mark.asyncio
async def test_cmd_start() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    await cmd_start(message, sessions)
    message.answer.assert_called_once()
    assert sessions.get(1).active is True


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
    command = MagicMock()
    command.args = "New Session"
    await cmd_new(message, command, sessions)
    assert sessions.get(1).session_id is None
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

    agent.list_sessions.return_value = []
    await cmd_list(message, sessions, agent)
    # Empty list → plain text, not a keyboard
    message.answer.assert_called_with("No sessions found.")

    sessions.get(1).custom_names = {"id-a": "My Name"}
    agent.list_sessions.return_value = [SessionInfo(1, "Title A", "10m ago", "id-a")]
    await cmd_list(message, sessions, agent)
    assert len(sessions.get(1).last_sessions) == 1
    # With sessions → keyboard is sent
    call_args = message.answer.call_args
    assert "tap Resume or Delete" in call_args[0][0]
    assert call_args.kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_cmd_list_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_list(message, SessionManager(), AsyncMock())
    message.answer.assert_not_called()


def test_resolve_id() -> None:
    sessions = [SessionInfo(1, "T", "t", "id-1")]
    assert _resolve_id("1", sessions) == "id-1"
    assert _resolve_id("2", sessions) == "2"
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
    assert "Current Model:" in message.answer.call_args[0][0]


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

    command = MagicMock()
    command.args = "New Name"
    await cmd_name(message, command, sessions)
    assert "No active session" in message.answer.call_args[0][0]

    sessions.get(1).session_id = "id-1"
    command.args = None
    await cmd_name(message, command, sessions)
    assert "Usage" in message.answer.call_args[0][0]

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

    command = MagicMock()
    command.args = None
    await cmd_resume(message, command, sessions)
    assert sessions.get(1).session_id == "latest"

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
async def test_cmd_model_with_args() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    config = AppConfig(TelegramConfig(VALID_TOKEN))

    command = MagicMock()
    command.args = "pro"
    await cmd_model(message, command, sessions)
    assert sessions.get(1).model == "pro"
    assert "pro" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_model_no_args() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()

    command = MagicMock()
    command.args = None
    await cmd_model(message, command, sessions)
    # No args → keyboard is sent
    call_args = message.answer.call_args
    assert "Select a model" in call_args[0][0]
    assert call_args.kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_cmd_model_no_user() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    await cmd_model(message, MagicMock(), SessionManager())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_format_session_list_sorting() -> None:
    sessions = [
        SessionInfo(1, "Oldest", "1 year ago", "id-old"),
        SessionInfo(2, "Newest", "Just now", "id-new"),
        SessionInfo(3, "Medium", "2 hours ago", "id-med"),
    ]
    custom_names = {"id-med": "Named Medium"}
    result = await _format_session_list(sessions, "id-new", custom_names)

    assert "Named Medium" in result
    assert "Newest" in result
    assert "Oldest" in result
    # Active session is marked with ▶
    assert "▶" in result
    assert "id-new" in result or "Newest" in result


@pytest.mark.asyncio
async def test_format_session_list_active_unnamed() -> None:
    sessions = [SessionInfo(1, "Title", "now", "id-1")]
    result = await _format_session_list(sessions, "id-1", {})
    assert "▶" in result
    assert "Title" in result


@pytest.mark.asyncio
async def test_cmd_current_with_name() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    sessions.get(1).session_id = "id-1"
    sessions.get(1).custom_names = {"id-1": "My Session"}
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))
    await cmd_current(message, sessions, config)
    assert "Current Session:" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_process_stream_empty_text() -> None:
    message = MagicMock(spec=Message)
    message.text = ""
    message.bot = MagicMock()
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.chat = Chat(id=1, type="private")
    message.answer = AsyncMock()

    agent = AsyncMock()

    async def empty_stream(*args: Any, **kwargs: Any) -> Any:
        yield ResultEvent(status="success")

    agent.run_stream = empty_stream

    sessions = SessionManager()
    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        res_acc, res_ids = await _process_stream(
            message, sessions.get(1), agent, None, None, sessions
        )
    assert res_acc == ""
    assert res_ids == []


@pytest.mark.asyncio
async def test_process_stream_no_bot() -> None:
    message = MagicMock(spec=Message)
    message.bot = None
    message.answer = AsyncMock()
    sessions = SessionManager()
    res_acc, res_ids = await _process_stream(
        message, sessions.get(1), AsyncMock(), None, None, sessions
    )
    assert res_acc == ""
    assert res_ids == []


@pytest.mark.asyncio
async def test_cmd_status() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()
    config = AppConfig(TelegramConfig(VALID_TOKEN))
    await cmd_status(message, sessions, config)
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_success() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.text = "hello"
    message.bot = MagicMock()
    message.chat = Chat(id=1, type="private")
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    reply.answer = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield MessageEvent(role="assistant", content="hi", delta=False)
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    config = AppConfig(TelegramConfig(VALID_TOKEN))
    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await handle_message(message, sessions, agent, config)

    message.answer.assert_called()


@pytest.mark.asyncio
async def test_handle_message_unauthorized() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=2, is_bot=False, first_name="Other")
    message.text = "hello"
    config = AppConfig(TelegramConfig(VALID_TOKEN, allowed_user_ids=[1]))
    await handle_message(message, SessionManager(), AsyncMock(), config)
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_no_user_or_text() -> None:
    message = MagicMock(spec=Message)
    message.from_user = None
    message.text = "hi"
    await handle_message(message, SessionManager(), AsyncMock(), MagicMock())
    message.answer.assert_not_called()

    message.from_user = User(id=1, is_bot=False, first_name="T")
    message.text = None
    await handle_message(message, SessionManager(), AsyncMock(), MagicMock())
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_inactive() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="T")
    message.text = "hi"
    sessions = SessionManager()
    sessions.get(1).active = False
    await handle_message(message, sessions, AsyncMock(), AppConfig(TelegramConfig(VALID_TOKEN)))
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_process_stream_with_tools() -> None:
    message = MagicMock(spec=Message)
    message.bot = MagicMock()
    message.text = "use tool"
    message.chat = Chat(id=1, type="private")
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    reply = MagicMock(spec=Message)
    reply.answer = AsyncMock()
    reply.edit_text = AsyncMock()
    reply.delete = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield ToolUseEvent(tool_id="c1", tool_name="read_file", parameters={"file_path": "f"})
        yield ToolResultEvent(tool_id="c1", status="success", output="content")
        yield MessageEvent(role="assistant", content="done", delta=False)
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    sessions = SessionManager()
    session = sessions.get(1)
    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        acc, ids = await _process_stream(message, session, agent, None, None, sessions)

    assert acc == "done"
    assert "c1" in ids
    reply.delete.assert_called_once()


@pytest.mark.asyncio
async def test_process_stream_error() -> None:
    message = MagicMock(spec=Message)
    message.bot = MagicMock()
    message.text = "error"
    message.chat = Chat(id=1, type="private")
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield ErrorEvent(severity="error", message="fail")

    agent.run_stream = mock_stream
    sessions = SessionManager()

    await _process_stream(message, sessions.get(1), agent, None, None, sessions)
    reply.edit_text.assert_called_with("Error: fail", reply_markup=None)


@pytest.mark.asyncio
async def test_process_stream_no_response() -> None:
    message = MagicMock(spec=Message)
    message.bot = MagicMock()
    message.text = "nothing"
    message.chat = Chat(id=1, type="private")
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream
    sessions = SessionManager()

    await _process_stream(message, sessions.get(1), agent, None, None, sessions)
    reply.edit_text.assert_called_with("No response.", reply_markup=None)


@pytest.mark.asyncio
async def test_process_stream_with_stats() -> None:
    message = MagicMock(spec=Message)
    message.bot = MagicMock()
    message.text = "stats"
    message.chat = Chat(id=1, type="private")
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    reply.answer = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        stats = StreamStats(
            total_tokens=100,
            input_tokens=50,
            output_tokens=50,
            cached=0,
            _input=50,
            duration_ms=1000,
            tool_calls=0,
            models={},
        )
        yield MessageEvent(role="assistant", content="hi", delta=False)
        yield ResultEvent(status="success", stats=stats)

    agent.run_stream = mock_stream
    sessions = SessionManager()

    await _process_stream(message, sessions.get(1), agent, None, None, sessions)
    # Check that footer was answered
    # In _process_stream: if state.stats_footer: await reply.answer(...)
    reply.answer.assert_called()
    assert "100 tokens" in reply.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_event_init() -> None:
    session = UserSession(pending_name="My Name")
    state = _StreamState()
    reply = MagicMock(spec=Message)
    reply.chat = MagicMock()
    reply.message_id = 42
    reply.edit_text = AsyncMock()
    await _handle_event(InitEvent(session_id="s1", model="m"), session, state, reply)
    assert session.session_id == "s1"
    assert session.custom_names["s1"] == "My Name"
    assert session.pending_name is None
    # Stop button should be injected after InitEvent
    reply.edit_text.assert_called()


@pytest.mark.asyncio
async def test_handle_event_message_delta() -> None:
    state = _StreamState(accumulated="Hello ")
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    await _handle_event(
        MessageEvent(role="assistant", content="World", delta=True), UserSession(), state, reply
    )
    assert state.accumulated == "Hello World"


@pytest.mark.asyncio
async def test_handle_event_tool_result_fail() -> None:
    tool_msg = MagicMock(spec=Message)
    tool_msg.edit_text = AsyncMock()
    state = _StreamState(tool_messages={"c1": tool_msg}, tool_html={"c1": "🔧 <b>tool</b>"})
    await _handle_event(
        ToolResultEvent(tool_id="c1", status="error", error={"type": "Error", "message": "e"}),
        UserSession(),
        state,
        MagicMock(),
    )
    assert "❌" in tool_msg.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_throttle_edit() -> None:
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    # Threshold not met
    t, last_len = await _throttle_edit(reply, "short", time.monotonic(), 0)
    reply.edit_text.assert_not_called()

    # Threshold met
    long_text = "a" * 300
    t, last_len = await _throttle_edit(reply, long_text, time.monotonic() - 2, 0)
    reply.edit_text.assert_called_once()
    assert last_len == len(long_text)


@pytest.mark.asyncio
async def test_edit_reply() -> None:
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    await _edit_reply(reply, "accumulated")
    reply.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_send_final() -> None:
    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    reply.answer = AsyncMock()
    reply.bot = MagicMock()
    long_text = "a" * 5000
    await _send_final(reply, long_text)
    assert reply.edit_text.called
    assert reply.answer.called


@pytest.mark.asyncio
async def test_send_new() -> None:
    reply = MagicMock(spec=Message)
    reply.answer = AsyncMock()
    await _send_new(reply, "new msg")
    reply.answer.assert_called_once()


def test_format_tool_html() -> None:
    # Shell
    ev = ToolUseEvent(
        tool_id="c1",
        tool_name="run_shell_command",
        parameters={"command": "ls", "description": "list"},
    )
    assert "list" in _format_tool_html(ev)

    # File ops
    ev = ToolUseEvent(
        tool_id="c2",
        tool_name="replace",
        parameters={
            "file_path": "f.txt",
            "instruction": "ins",
            "old_string": "o",
            "new_string": "n",
        },
    )
    res = _format_tool_html(ev)
    assert "f.txt" in res
    assert "ins" in res
    assert "- o" in res
    assert "+ n" in res

    ev = ToolUseEvent(
        tool_id="c3", tool_name="write_file", parameters={"file_path": "f", "content": "c"}
    )
    assert "f" in _format_tool_html(ev)

    ev = ToolUseEvent(
        tool_id="c4",
        tool_name="read_file",
        parameters={"file_path": "f", "start_line": 1, "end_line": 10},
    )
    assert "L1-L10" in _format_tool_html(ev)

    # Search
    ev = ToolUseEvent(tool_id="c5", tool_name="list_directory", parameters={"dir_path": "d"})
    assert "list_directory" in _format_tool_html(ev)

    ev = ToolUseEvent(tool_id="c6", tool_name="glob", parameters={"pattern": "p"})
    assert "glob" in _format_tool_html(ev)

    ev = ToolUseEvent(tool_id="c7", tool_name="grep_search", parameters={"pattern": "p"})
    assert "grep_search" in _format_tool_html(ev)

    ev = ToolUseEvent(tool_id="c8", tool_name="google_web_search", parameters={"query": "q"})
    assert "google_web_search" in _format_tool_html(ev)

    ev = ToolUseEvent(tool_id="c9", tool_name="web_fetch", parameters={"prompt": "p"})
    assert "web_fetch" in _format_tool_html(ev)

    # Generic
    ev = ToolUseEvent(tool_id="c10", tool_name="other", parameters={"p1": "v1"})
    assert "other" in _format_tool_html(ev)
    assert "v1" in _format_tool_html(ev)

    ev = ToolUseEvent(tool_id="c11", tool_name="no_params", parameters={})
    assert "no_params" in _format_tool_html(ev)


@pytest.mark.asyncio
async def test_start_bot() -> None:
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))
    # start_bot uses asyncio.gather(polling_task, shutdown_requested.wait())
    # Pre-set the Event so .wait() returns immediately and the test doesn't hang.
    fast_event = asyncio.Event()
    fast_event.set()

    with (
        patch("tg_gemini.bot.Dispatcher.start_polling", new_callable=AsyncMock) as mock_poll,
        patch("tg_gemini.bot.Bot.set_my_commands", new_callable=AsyncMock) as mock_cmd,
        patch("tg_gemini.bot.asyncio.Event", return_value=fast_event),
    ):
        await start_bot(config)
        mock_poll.assert_called_once()
        mock_cmd.assert_called_once()


# ── Inline keyboard builder tests ────────────────────────────────────────────────


def test_build_model_keyboard() -> None:
    kb = _build_model_keyboard()
    assert kb.inline_keyboard is not None
    assert len(kb.inline_keyboard) == 1
    row = kb.inline_keyboard[0]
    assert len(row) == 4
    texts = [btn.text for btn in row]
    assert "auto" in texts
    assert "pro" in texts
    assert "flash" in texts
    assert "flash-lite" in texts
    # Verify callback data format
    for btn in row:
        assert btn.callback_data.startswith("m:")


def test_build_session_keyboard_empty() -> None:
    assert _build_session_keyboard([], None, {}) is None


def test_build_session_keyboard_with_sessions() -> None:
    sessions = [
        SessionInfo(1, "Active Session", "now", "id-active"),
        SessionInfo(2, "Other", "1h ago", "id-other"),
    ]
    kb = _build_session_keyboard(sessions, "id-active", {"id-active": "My Session"})
    assert kb is not None
    assert len(kb.inline_keyboard) == 2

    # First row: active session
    row0 = kb.inline_keyboard[0]
    assert len(row0) == 3
    assert "My Session" in row0[0].text
    assert row0[1].text == "Current"  # active session shows "Current"
    assert row0[1].callback_data == "noop:current"
    assert row0[2].callback_data == "d:id-active"

    # Second row: non-active session
    row1 = kb.inline_keyboard[1]
    assert row1[1].text == "Resume"
    assert row1[1].callback_data == "r:id-other"


def test_build_session_keyboard_truncates_long_title() -> None:
    sessions = [SessionInfo(1, "A" * 50, "now", "id-1")]
    kb = _build_session_keyboard(sessions, None, {})
    assert kb is not None
    # Title should be truncated
    assert "…" in kb.inline_keyboard[0][0].text


def test_build_stop_button() -> None:
    kb = _build_stop_button(42)
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 1
    btn = kb.inline_keyboard[0][0]
    assert "Stop" in btn.text
    assert btn.callback_data == "s:42"


# ── Callback handler tests ──────────────────────────────────────────────────────


def _make_callback_query(data: str, user_id: int = 1) -> MagicMock:
    """Create a mock CallbackQuery for testing."""
    query = MagicMock(spec=CallbackQuery)
    query.data = data
    query.from_user = User(id=user_id, is_bot=False, first_name="Test")
    msg = MagicMock(spec=Message)
    msg.edit_text = AsyncMock()
    query.message = msg
    query.answer = AsyncMock()
    return query


@pytest.mark.asyncio
async def test_callback_model() -> None:
    query = _make_callback_query("m:flash")
    sessions = SessionManager()
    await callback_model(query, sessions)
    assert sessions.get(1).model == "flash"
    query.message.edit_text.assert_called_once()
    assert "flash" in query.message.edit_text.call_args[0][0]
    query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_model_no_message() -> None:
    query = _make_callback_query("m:flash")
    query.message = None
    sessions = SessionManager()
    await callback_model(query, sessions)
    assert sessions.get(1).model is None


@pytest.mark.asyncio
async def test_callback_resume() -> None:
    query = _make_callback_query("r:session-abc-123")
    sessions = SessionManager()
    await callback_resume(query, sessions)
    assert sessions.get(1).session_id == "session-abc-123"
    query.message.edit_text.assert_called_once()
    query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_delete_success() -> None:
    query = _make_callback_query("d:id-to-delete")
    sessions = SessionManager()
    sessions.get(1).session_id = "id-to-delete"
    sessions.get(1).custom_names = {"id-to-delete": "Named"}
    agent = AsyncMock()
    agent.delete_session.return_value = True

    await callback_delete(query, sessions, agent)
    assert sessions.get(1).session_id is None
    assert "id-to-delete" not in sessions.get(1).custom_names
    agent.delete_session.assert_called_with("id-to-delete")
    query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_delete_fail() -> None:
    query = _make_callback_query("d:id-x")
    agent = AsyncMock()
    agent.delete_session.return_value = False
    sessions = SessionManager()

    await callback_delete(query, sessions, agent)
    assert "Failed" in query.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_callback_stop_with_active_stream() -> None:
    query = _make_callback_query("s:42")
    sessions = SessionManager()
    stop_evt = asyncio.Event()
    sessions.get(1).stop_event = stop_evt

    await callback_stop(query, sessions)
    assert stop_evt.is_set()
    query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_stop_no_stream() -> None:
    query = _make_callback_query("s:42")
    sessions = SessionManager()
    # stop_event is None (no active stream)
    await callback_stop(query, sessions)
    query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_stop_invalid_data() -> None:
    query = _make_callback_query("s:notanumber")
    sessions = SessionManager()
    await callback_stop(query, sessions)
    query.answer.assert_called_once_with("Already stopped.", show_alert=True)


@pytest.mark.asyncio
async def test_callback_noop() -> None:
    query = _make_callback_query("noop:info")
    await callback_noop(query)
    query.answer.assert_called_once()
