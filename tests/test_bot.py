from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Message, User
from pydantic import BaseModel

from tg_gemini.bot import (
    TOOL_CMD_TRUNCATE,
    TOOL_PARAM_TRUNCATE,
    SessionManager,
    UserSession,
    _edit_reply,
    _format_tool_html,
    _handle_event,
    _is_authorized,
    _process_stream,
    _resolve_id,
    _send_final,
    _send_new,
    _StreamState,
    _throttle_edit,
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


def test_session_manager() -> None:
    sm = SessionManager()
    s1 = sm.get(1)
    s2 = sm.get(1)
    assert s1 is s2
    assert s1.active is True


def test_format_tool_html_shell() -> None:
    # command in pre code block with bash language
    e = ToolUseEvent(tool_name="run_shell_command", tool_id="1", parameters={"command": "ls -la"})
    result = _format_tool_html(e)
    assert "🔧 <b>run_shell_command</b>" in result
    assert '<pre><code class="language-bash">ls -la</code></pre>' in result

    # with description as bold title
    e = ToolUseEvent(
        tool_name="run_shell_command",
        tool_id="2",
        parameters={"command": "npm install", "description": "Install deps"},
    )
    result = _format_tool_html(e)
    assert "🔧 <b>Install deps</b>" in result
    assert "npm install" in result

    # truncation
    long_cmd = "x" * (TOOL_CMD_TRUNCATE + 10)
    e = ToolUseEvent(tool_name="run_shell_command", tool_id="3", parameters={"command": long_cmd})
    assert "…" in _format_tool_html(e)

    # HTML escaping in pre block
    e = ToolUseEvent(
        tool_name="run_shell_command", tool_id="4", parameters={"command": "echo <b>hi</b>"}
    )
    assert "&lt;b&gt;" in _format_tool_html(e)


def test_format_tool_html_file_ops() -> None:
    # read_file with bold name and file path in code
    e = ToolUseEvent(tool_name="read_file", tool_id="1", parameters={"file_path": "src/main.py"})
    result = _format_tool_html(e)
    assert "🔧 <b>read_file</b>: <code>src/main.py</code>" in result

    # read_file with line range
    e = ToolUseEvent(
        tool_name="read_file",
        tool_id="2",
        parameters={"file_path": "f.py", "start_line": 10, "end_line": 20},
    )
    assert "(L10-L20)" in _format_tool_html(e)

    # read_file with start_line only
    e = ToolUseEvent(
        tool_name="read_file", tool_id="3", parameters={"file_path": "f.py", "start_line": 5}
    )
    assert "(from L5)" in _format_tool_html(e)

    # write_file with content in pre block
    e = ToolUseEvent(
        tool_name="write_file",
        tool_id="4",
        parameters={"file_path": "out.txt", "content": "first line\nsecond line"},
    )
    result = _format_tool_html(e)
    assert "<code>out.txt</code>" in result
    assert "<pre><code>" in result
    assert "first line" in result

    # write_file without content
    e = ToolUseEvent(tool_name="write_file", tool_id="5", parameters={"file_path": "out.txt"})
    result = _format_tool_html(e)
    assert "<code>out.txt</code>" in result
    assert "<pre>" not in result

    # replace with instruction and diff
    e = ToolUseEvent(
        tool_name="replace",
        tool_id="6",
        parameters={
            "file_path": "f.py",
            "instruction": "Fix the bug",
            "old_string": "old_code",
            "new_string": "new_code",
        },
    )
    result = _format_tool_html(e)
    assert "<code>f.py</code>" in result
    assert "<i>Fix the bug</i>" in result
    assert "<pre><code>" in result
    assert "- old_code" in result
    assert "+ new_code" in result

    # replace without instruction but with diff
    e = ToolUseEvent(
        tool_name="replace",
        tool_id="7",
        parameters={"file_path": "f.py", "old_string": "a", "new_string": "b"},
    )
    result = _format_tool_html(e)
    assert "- a" in result
    assert "+ b" in result

    # replace with old_string only (deletion)
    e = ToolUseEvent(
        tool_name="replace",
        tool_id="8",
        parameters={"file_path": "f.py", "old_string": "removed", "new_string": ""},
    )
    result = _format_tool_html(e)
    assert "- removed" in result
    assert "+ " not in result

    # replace with new_string only (insertion)
    e = ToolUseEvent(
        tool_name="replace",
        tool_id="9",
        parameters={"file_path": "f.py", "old_string": "", "new_string": "added"},
    )
    result = _format_tool_html(e)
    assert "+ added" in result
    assert "- " not in result

    # replace with no old/new strings
    e = ToolUseEvent(tool_name="replace", tool_id="10", parameters={"file_path": "f.py"})
    result = _format_tool_html(e)
    assert "🔧 <b>replace</b>: <code>f.py</code>" in result
    assert "<pre>" not in result


def test_format_tool_html_search() -> None:
    # list_directory with bold name
    e = ToolUseEvent(tool_name="list_directory", tool_id="1", parameters={"dir_path": "src/"})
    result = _format_tool_html(e)
    assert "<b>list_directory</b>" in result
    assert "<code>src/</code>" in result

    # glob with bold name
    e = ToolUseEvent(tool_name="glob", tool_id="2", parameters={"pattern": "**/*.py"})
    result = _format_tool_html(e)
    assert "<b>glob</b>" in result
    assert "<code>**/*.py</code>" in result

    # grep_search with pattern key
    e = ToolUseEvent(tool_name="grep_search", tool_id="3", parameters={"pattern": "TODO"})
    result = _format_tool_html(e)
    assert "<b>grep_search</b>" in result
    assert "<code>TODO</code>" in result

    # grep_search with query key (legacy)
    e = ToolUseEvent(tool_name="grep_search", tool_id="4", parameters={"query": "FIXME"})
    assert "<code>FIXME</code>" in _format_tool_html(e)

    # google_web_search with bold name
    e = ToolUseEvent(tool_name="google_web_search", tool_id="5", parameters={"query": "python"})
    result = _format_tool_html(e)
    assert "<b>google_web_search</b>" in result
    assert "python" in result

    # web_fetch with prompt key
    e = ToolUseEvent(
        tool_name="web_fetch", tool_id="6", parameters={"prompt": "https://example.com"}
    )
    result = _format_tool_html(e)
    assert "<b>web_fetch</b>" in result
    assert "https://example.com" in result

    # web_fetch with url key (legacy)
    e = ToolUseEvent(tool_name="web_fetch", tool_id="7", parameters={"url": "https://example.com"})
    assert "https://example.com" in _format_tool_html(e)


def test_format_tool_html_generic() -> None:
    # with params and bold name
    e = ToolUseEvent(tool_name="custom_tool", tool_id="1", parameters={"arg": "value"})
    result = _format_tool_html(e)
    assert "<b>custom_tool</b>" in result
    assert "value" in result

    # param truncation
    e = ToolUseEvent(
        tool_name="custom_tool", tool_id="2", parameters={"arg": "v" * (TOOL_PARAM_TRUNCATE + 10)}
    )
    assert "…" in _format_tool_html(e)

    # no params
    e = ToolUseEvent(tool_name="save_memory", tool_id="3", parameters={})
    assert _format_tool_html(e) == "🔧 save_memory"


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

    command = MagicMock()
    command.args = None
    await cmd_new(message, command, sessions)
    assert sessions.get(1).session_id is None
    assert sessions.get(1).pending_name is None

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

    agent.list_sessions.return_value = []
    await cmd_list(message, sessions, agent)
    assert "No sessions" in message.answer.call_args[0][0]

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
async def test_cmd_model() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="Test")
    message.answer = AsyncMock()
    sessions = SessionManager()

    command = MagicMock()
    command.args = None
    await cmd_model(message, command, sessions)
    assert "Usage" in message.answer.call_args[0][0]

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
async def test_throttle_edit_no_update() -> None:
    reply = AsyncMock()
    res_time, res_len = await _throttle_edit(reply, "acc", 0.0, 0)
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
    reply.answer = AsyncMock()
    reply.bot = MagicMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    sessions.get(1).pending_name = "Assigned Name"

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield InitEvent(session_id="new_id", model="gemini-pro")
        yield MessageEvent(role="user", content="hi")
        yield MessageEvent(role="assistant", content="a" * 300, delta=True)
        yield MessageEvent(role="assistant", content="b", delta=True)
        yield MessageEvent(role="assistant", content="final content", delta=False)
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
                models={},
            ),
        )

    agent.run_stream = mock_stream
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))

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
async def test_handle_message_tool_use_separate_messages() -> None:
    """Tool use events send separate HTML messages; final response sent after tools."""
    user = User(id=1, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = Chat(id=1, type="private")
    message.text = "hello"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    reply.delete = AsyncMock()

    tool_msg = MagicMock(spec=Message)
    tool_msg.edit_text = AsyncMock()

    # reply.answer returns tool_msg for tool use, then final response messages
    reply.answer = AsyncMock(return_value=tool_msg)
    reply.bot = MagicMock()
    message.answer = AsyncMock(return_value=reply)

    sessions = SessionManager()
    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield ToolUseEvent(
            tool_name="run_shell_command", tool_id="call_1", parameters={"command": "ls -la"}
        )
        yield ToolResultEvent(tool_id="call_1", status="success")
        yield MessageEvent(role="assistant", content="Done!", delta=False)
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await handle_message(message, sessions, agent, AppConfig(TelegramConfig(VALID_TOKEN)))

    # Tool use sent as HTML with pre code block
    tool_call = reply.answer.call_args_list[0]
    assert '<code class="language-bash">ls -la</code>' in tool_call.args[0]
    assert tool_call.kwargs.get("parse_mode") == "HTML"

    # Tool result edited with HTML parse_mode
    tool_msg.edit_text.assert_called_once()
    edit_call = tool_msg.edit_text.call_args
    assert "✅" in edit_call.args[0]
    assert edit_call.kwargs.get("parse_mode") == "HTML"

    # "Thinking..." reply is deleted when tools are used
    reply.delete.assert_called_once()

    # Final response sent as new message(s) via reply.answer
    assert reply.answer.call_count >= 2  # noqa: PLR2004


@pytest.mark.asyncio
async def test_handle_message_tool_result_error() -> None:
    """Tool result with error status shows ❌."""
    reply = AsyncMock()
    state = _StreamState()
    session = UserSession()

    tool_msg = MagicMock(spec=Message)
    tool_msg.edit_text = AsyncMock()
    state.tool_messages["call_1"] = tool_msg
    state.tool_html["call_1"] = "🔧 <b>bash</b>"

    await _handle_event(ToolResultEvent(tool_id="call_1", status="error"), session, state, reply)
    tool_msg.edit_text.assert_called_once_with("❌ <b>bash</b>", parse_mode="HTML")


@pytest.mark.asyncio
async def test_handle_message_tool_result_unknown_id() -> None:
    """Tool result for unknown tool_id is ignored."""
    reply = AsyncMock()
    state = _StreamState()
    session = UserSession()

    await _handle_event(
        ToolResultEvent(tool_id="unknown_id", status="success"), session, state, reply
    )
    # No crash, no side effects


@pytest.mark.asyncio
async def test_handle_message_tool_result_edit_exception() -> None:
    """Suppresses exceptions when editing tool messages."""
    reply = AsyncMock()
    state = _StreamState()
    session = UserSession()

    tool_msg = MagicMock(spec=Message)
    tool_msg.edit_text = AsyncMock(side_effect=Exception("telegram error"))
    state.tool_messages["call_1"] = tool_msg
    state.tool_html["call_1"] = "🔧 <b>bash</b>"

    # Should not raise
    await _handle_event(ToolResultEvent(tool_id="call_1", status="success"), session, state, reply)


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
async def test_handle_event_unhandled() -> None:
    """Unhandled event types are silently ignored."""
    reply = AsyncMock()
    state = _StreamState()
    session = UserSession()

    class UnknownEvent(BaseModel):
        type: str = "unknown"

    await _handle_event(UnknownEvent(), session, state, reply)  # type: ignore[arg-type]
    assert not state.aborted
    assert state.accumulated == ""


@pytest.mark.asyncio
async def test_handle_event_user_message_ignored() -> None:
    """Non-assistant messages are ignored."""
    reply = AsyncMock()
    state = _StreamState()
    session = UserSession()

    await _handle_event(MessageEvent(role="user", content="hi"), session, state, reply)
    assert state.accumulated == ""


@pytest.mark.asyncio
async def test_handle_event_result_with_stats() -> None:
    """Result event with stats stores footer in state (deferred sending)."""
    reply = AsyncMock()
    state = _StreamState()
    session = UserSession()

    await _handle_event(
        ResultEvent(
            status="success",
            stats=StreamStats(
                total_tokens=100,
                input_tokens=50,
                output_tokens=50,
                cached=0,
                input=50,
                duration_ms=2000,
                tool_calls=1,
                models={},
            ),
        ),
        session,
        state,
        reply,
    )
    assert "100 tokens" in state.stats_footer
    assert "2.0s" in state.stats_footer


@pytest.mark.asyncio
async def test_process_stream_unhandled_event() -> None:
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="T")
    message.chat = Chat(id=1, type="private")
    message.text = "h"
    message.bot = MagicMock()
    reply = AsyncMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield InitEvent(session_id="id", model="m")
        yield ErrorEvent(severity="error", message="e")
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await _process_stream(message, SessionManager().get(1), agent)


@pytest.mark.asyncio
async def test_process_stream_tools_only_no_text() -> None:
    """When there are tool messages but no accumulated text, don't show 'No response'."""
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="T")
    message.chat = Chat(id=1, type="private")
    message.text = "h"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    tool_msg = MagicMock(spec=Message)
    tool_msg.text = "🔧 bash"
    tool_msg.edit_text = AsyncMock()
    reply.answer = AsyncMock(return_value=tool_msg)
    reply.bot = MagicMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield ToolUseEvent(tool_name="bash", tool_id="c1", parameters={})
        yield ToolResultEvent(tool_id="c1", status="success")
        yield ResultEvent(status="success")

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        acc, tool_ids = await _process_stream(message, SessionManager().get(1), agent)

    assert acc == ""
    assert len(tool_ids) == 1
    # Should NOT have called edit_text with "No response"
    for call in reply.edit_text.call_args_list:
        assert "No response" not in call[0][0]


@pytest.mark.asyncio
async def test_process_stream_no_bot() -> None:
    message = MagicMock(spec=Message)
    message.bot = None
    res_acc, res_status = await _process_stream(message, MagicMock(), AsyncMock())
    assert res_acc == ""
    assert res_status == []


@pytest.mark.asyncio
async def test_edit_reply() -> None:
    reply = MagicMock()
    reply.edit_text = AsyncMock()
    await _edit_reply(reply, "hello world")
    reply.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_edit_reply_exception() -> None:
    reply = MagicMock()
    reply.edit_text = AsyncMock(side_effect=Exception("fail"))
    await _edit_reply(reply, "text")


@pytest.mark.asyncio
async def test_edit_reply_empty_chunks() -> None:
    reply = MagicMock()
    with (
        patch("tg_gemini.bot.md_to_telegram_html", return_value=""),
        patch("tg_gemini.bot.split_message_code_fence_aware", return_value=[]),
    ):
        await _edit_reply(reply, "some text")
        reply.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_send_final_single_chunk() -> None:
    reply = MagicMock()
    reply.edit_text = AsyncMock()
    reply.bot = MagicMock()
    await _send_final(reply, "hello")
    reply.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_send_final_multi_chunk() -> None:
    reply = MagicMock()
    reply.edit_text = AsyncMock()
    reply.answer = AsyncMock()
    reply.bot = MagicMock()

    with (
        patch("tg_gemini.bot.md_to_telegram_html", return_value="full html"),
        patch("tg_gemini.bot.split_message_code_fence_aware", return_value=["chunk1", "chunk2"]),
    ):
        await _send_final(reply, "text")
        reply.edit_text.assert_called_once_with("chunk1", parse_mode="HTML")
        reply.answer.assert_called_once_with("chunk2", parse_mode="HTML")


@pytest.mark.asyncio
async def test_send_final_multi_chunk_no_bot() -> None:
    """When reply.bot is None, overflow chunks are not sent."""
    reply = MagicMock()
    reply.edit_text = AsyncMock()
    reply.bot = None

    with (
        patch("tg_gemini.bot.md_to_telegram_html", return_value="full html"),
        patch("tg_gemini.bot.split_message_code_fence_aware", return_value=["chunk1", "chunk2"]),
    ):
        await _send_final(reply, "text")
        reply.edit_text.assert_called_once_with("chunk1", parse_mode="HTML")


@pytest.mark.asyncio
async def test_send_final_empty_chunks() -> None:
    reply = MagicMock()
    with (
        patch("tg_gemini.bot.md_to_telegram_html", return_value=""),
        patch("tg_gemini.bot.split_message_code_fence_aware", return_value=[]),
    ):
        await _send_final(reply, "some text")
        reply.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_send_new_single_chunk() -> None:
    reply = MagicMock()
    reply.answer = AsyncMock()
    await _send_new(reply, "hello")
    reply.answer.assert_called_once()


@pytest.mark.asyncio
async def test_send_new_multi_chunk() -> None:
    reply = MagicMock()
    reply.answer = AsyncMock()

    with (
        patch("tg_gemini.bot.md_to_telegram_html", return_value="full html"),
        patch("tg_gemini.bot.split_message_code_fence_aware", return_value=["chunk1", "chunk2"]),
    ):
        await _send_new(reply, "text")
        assert reply.answer.call_count == 2  # noqa: PLR2004
        reply.answer.assert_any_call("chunk1", parse_mode="HTML")
        reply.answer.assert_any_call("chunk2", parse_mode="HTML")


@pytest.mark.asyncio
async def test_send_new_exception_suppressed() -> None:
    reply = MagicMock()
    reply.answer = AsyncMock(side_effect=Exception("telegram error"))
    await _send_new(reply, "text")  # Should not raise


@pytest.mark.asyncio
async def test_process_stream_stats_footer_sent_last() -> None:
    """Stats footer is sent as the last message after final response."""
    message = MagicMock(spec=Message)
    message.from_user = User(id=1, is_bot=False, first_name="T")
    message.chat = Chat(id=1, type="private")
    message.text = "h"
    message.bot = MagicMock()

    reply = MagicMock(spec=Message)
    reply.edit_text = AsyncMock()
    reply.answer = AsyncMock()
    reply.bot = MagicMock()
    message.answer = AsyncMock(return_value=reply)

    agent = AsyncMock()

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        yield MessageEvent(role="assistant", content="response", delta=False)
        yield ResultEvent(
            status="success",
            stats=StreamStats(
                total_tokens=100,
                input_tokens=50,
                output_tokens=50,
                cached=0,
                input=50,
                duration_ms=2000,
                tool_calls=0,
                models={},
            ),
        )

    agent.run_stream = mock_stream

    with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
        await _process_stream(message, SessionManager().get(1), agent)

    # Stats footer sent as separate message
    stats_calls = [c for c in reply.answer.call_args_list if c.args and "tokens" in str(c.args[0])]
    assert len(stats_calls) == 1
    assert "100 tokens" in stats_calls[0].args[0]


@pytest.mark.asyncio
async def test_start_bot() -> None:
    config = AppConfig(TelegramConfig(VALID_TOKEN), GeminiConfig("auto"))
    with (
        patch("tg_gemini.bot.Dispatcher.start_polling", new_callable=AsyncMock) as mock_poll,
        patch("tg_gemini.bot.Bot.set_my_commands", new_callable=AsyncMock) as mock_cmd,
    ):
        await start_bot(config)
        mock_poll.assert_called_once()
        mock_cmd.assert_called_once()
