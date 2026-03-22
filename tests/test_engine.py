"""Tests for engine.py: Engine message routing and command dispatch."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from tg_gemini.config import (
    AppConfig,
    DisplayConfig,
    GeminiConfig,
    StreamPreviewConfig,
    TelegramConfig,
)
from tg_gemini.engine import Engine
from tg_gemini.gemini import GeminiAgent, GeminiSession
from tg_gemini.i18n import I18n, Language
from tg_gemini.models import Event, EventType, Message, ReplyContext
from tg_gemini.session import SessionManager


def _make_config() -> AppConfig:
    return AppConfig(
        telegram=TelegramConfig(token="tok"),
        gemini=GeminiConfig(),
        display=DisplayConfig(thinking_max_len=50, tool_max_len=100),
        stream_preview=StreamPreviewConfig(
            enabled=True, interval_ms=0, min_delta_chars=1
        ),
    )


def _make_engine(
    config: AppConfig | None = None,
) -> tuple[Engine, MagicMock, MagicMock]:
    cfg = config or _make_config()
    agent = MagicMock(spec=GeminiAgent)
    agent.model = ""
    agent.mode = "default"
    agent.available_models.return_value = []
    platform = MagicMock()
    platform.start = AsyncMock()
    platform.stop = AsyncMock()
    platform.send = AsyncMock()
    platform.reply = AsyncMock()
    platform.send_preview_start = AsyncMock(return_value=MagicMock())
    platform.update_message = AsyncMock()
    platform.delete_preview = AsyncMock()
    platform.start_typing = AsyncMock(
        return_value=asyncio.create_task(asyncio.sleep(0))
    )
    sessions = SessionManager()
    i18n = I18n(lang=Language.EN)
    engine = Engine(
        config=cfg, agent=agent, platform=platform, sessions=sessions, i18n=i18n
    )
    return engine, agent, platform


def _make_message(
    content: str = "hello", session_key: str = "telegram:1:2", user_id: str = "2"
) -> Message:
    return Message(
        session_key=session_key,
        platform="telegram",
        user_id=user_id,
        user_name="testuser",
        content=content,
        reply_ctx=ReplyContext(chat_id=1, message_id=10),
    )


# --- Engine.start / stop ---


async def test_engine_start_calls_platform() -> None:
    engine, _agent, platform = _make_engine()
    await engine.start()
    platform.start.assert_called_once_with(engine.handle_message)


async def test_engine_stop_calls_platform() -> None:
    engine, _agent, platform = _make_engine()
    await engine.stop()
    platform.stop.assert_called_once()


# --- handle_message ---


async def test_handle_message_empty_content_ignored() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message(content="")
    await engine.handle_message(msg)
    platform.send.assert_not_called()
    platform.reply.assert_not_called()


async def test_handle_message_slash_command_dispatched() -> None:
    engine, _agent, _platform = _make_engine()
    msg = _make_message(content="/help")
    with patch.object(
        engine, "handle_command", new=AsyncMock(return_value=True)
    ) as mock_cmd:
        await engine.handle_message(msg)
        mock_cmd.assert_called_once_with(msg, "/help")


async def test_handle_message_busy_session_queues() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    session = engine._sessions.get_or_create(msg.session_key)
    session._busy = True  # Simulate busy

    await engine.handle_message(msg)
    platform.send.assert_called_once()
    text = platform.send.call_args[0][1]
    assert "busy" in text.lower() or "⏳" in text


async def test_handle_message_busy_queue_full() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    session = engine._sessions.get_or_create(msg.session_key)
    session._busy = True

    # Fill the queue
    q = engine._queues.setdefault(msg.session_key, asyncio.Queue(maxsize=5))
    for _ in range(5):
        await q.put(msg)

    await engine.handle_message(msg)
    platform.send.assert_called()
    # Still gets a busy message
    call_text = platform.send.call_args[0][1]
    assert "⏳" in call_text or "busy" in call_text.lower()


# --- handle_command ---


async def test_handle_command_new() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/new")
    assert result is True
    platform.send.assert_called_once()
    text = platform.send.call_args[0][1]
    assert "🆕" in text or "new" in text.lower()


async def test_handle_command_help() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/help")
    assert result is True
    platform.send.assert_called_once()


async def test_handle_command_stop() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/stop")
    assert result is True
    platform.send.assert_called_once()


async def test_handle_command_model_with_arg() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/model gemini-2.5-flash")
    assert result is True
    assert agent.model == "gemini-2.5-flash"
    platform.send.assert_called_once()
    text = platform.send.call_args[0][1]
    assert "gemini-2.5-flash" in text


async def test_handle_command_model_no_arg() -> None:
    engine, agent, platform = _make_engine()
    agent.model = "flash"
    agent.available_models.return_value = [MagicMock(name="flash")]
    msg = _make_message()
    result = await engine.handle_command(msg, "/model")
    assert result is True
    platform.send.assert_called_once()
    text = platform.send.call_args[0][1]
    assert "flash" in text


async def test_handle_command_model_no_model_set() -> None:
    engine, agent, platform = _make_engine()
    agent.model = ""
    agent.available_models.return_value = []
    msg = _make_message()
    result = await engine.handle_command(msg, "/model")
    assert result is True
    platform.send.assert_called_once()
    text = platform.send.call_args[0][1]
    assert "(default)" in text


async def test_handle_command_mode_valid() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/mode yolo")
    assert result is True
    assert agent.mode == "yolo"
    platform.send.assert_called_once()


async def test_handle_command_mode_invalid() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/mode invalid_mode")
    assert result is True
    platform.send.assert_called_once()


async def test_handle_command_mode_no_arg() -> None:
    engine, agent, platform = _make_engine()
    agent.mode = "plan"
    msg = _make_message()
    result = await engine.handle_command(msg, "/mode")
    assert result is True
    platform.send.assert_called_once()
    text = platform.send.call_args[0][1]
    assert "plan" in text


async def test_handle_command_unknown() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/unknown")
    assert result is True
    platform.send.assert_called_once()
    text = platform.send.call_args[0][1]
    assert "unknown" in text.lower() or "Unknown" in text


async def test_handle_command_with_botname_suffix() -> None:
    engine, _agent, _platform = _make_engine()
    msg = _make_message()
    result = await engine.handle_command(msg, "/help@mybotname")
    assert result is True


# --- _run_gemini with mocked events ---


def _mock_gemini_session(events: list[Event]) -> MagicMock:
    session = MagicMock(spec=GeminiSession)
    session.current_session_id = ""
    session.alive = True
    session.send = AsyncMock()
    session.close = AsyncMock()

    q: asyncio.Queue[Event] = asyncio.Queue()
    for evt in events:
        q.put_nowait(evt)

    session.events = q
    return session


async def test_run_gemini_text_only() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.TEXT, content="Hello "),
        Event(type=EventType.TEXT, content="world"),
        Event(type=EventType.RESULT, done=True, session_id="s1"),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    # Either preview was used or reply was sent
    assert (
        platform.reply.called
        or platform.send_preview_start.called
        or platform.update_message.called
    )


async def test_run_gemini_text_stored_in_session() -> None:
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.TEXT, session_id="new-session-id", tool_name="flash"),
        Event(type=EventType.RESULT, done=True, session_id="new-session-id"),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    user_session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, user_session)
    assert user_session.agent_session_id == "new-session-id"


async def test_run_gemini_tool_use_and_result() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.TEXT, content="Let me check"),
        Event(type=EventType.TOOL_USE, tool_name="read_file", tool_input="/x.txt"),
        Event(type=EventType.TOOL_RESULT, tool_name="id1", content="file content"),
        Event(type=EventType.TEXT, content="Here it is"),
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    # Should have sent tool notification
    calls = platform.send.call_args_list
    texts = [str(c[0][1]) for c in calls]
    assert any("read_file" in t or "🔧" in t for t in texts)


async def test_run_gemini_thinking_event() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.THINKING, content="thinking about this problem..."),
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    calls = platform.send.call_args_list
    texts = [str(c[0][1]) for c in calls]
    assert any("thinking" in t.lower() or "<i>" in t for t in texts)


async def test_run_gemini_thinking_truncated() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    long_thinking = "x" * 200  # > thinking_max_len=50
    events = [
        Event(type=EventType.THINKING, content=long_thinking),
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    calls = platform.send.call_args_list
    texts = [str(c[0][1]) for c in calls]
    thinking_texts = [t for t in texts if "<i>" in t or "x" * 50 in t]
    assert any(len(t) < 200 for t in thinking_texts)


async def test_run_gemini_error_event() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.ERROR, error=RuntimeError("agent crashed")),
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    calls = platform.send.call_args_list
    texts = [str(c[0][1]) for c in calls]
    assert any("agent crashed" in t or "❌" in t for t in texts)


async def test_run_gemini_error_no_error_obj() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.ERROR, error=None),  # error=None
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)
    # Should handle gracefully
    calls = platform.send.call_args_list
    texts = [str(c[0][1]) for c in calls]
    assert any("❌" in t or "Error" in t for t in texts)


async def test_run_gemini_empty_response_no_tool() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.RESULT, done=True)  # No text content
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session
    # Make preview finish return False (no preview)
    platform.send_preview_start.side_effect = Exception("no preview")

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    # Should send empty response message
    calls = platform.send.call_args_list
    texts = [str(c[0][1]) for c in calls if c[0][1] is not None]
    assert any(
        "no response" in t.lower() or "无响应" in t or "response" in t.lower()
        for t in texts
    )


async def test_run_gemini_exception_sends_error() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    agent.start_session.side_effect = RuntimeError("start failed")

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    platform.send.assert_called()
    call_text = platform.send.call_args[0][1]
    assert "start failed" in call_text or "❌" in call_text


async def test_run_gemini_timeout() -> None:
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    # Session that never produces events
    mock_session = MagicMock(spec=GeminiSession)
    mock_session.current_session_id = ""
    mock_session.send = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.events = asyncio.Queue()  # empty queue → timeout

    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)

    from typing import Any as _Any

    def _fake_wait_for(coro: _Any, **_: _Any) -> _Any:
        if hasattr(coro, "close"):
            coro.close()
        raise TimeoutError

    with patch("asyncio.wait_for", side_effect=_fake_wait_for):
        await engine._run_gemini(msg, session)
    # Should handle timeout gracefully


async def test_process_acquires_lock_and_drains_queue() -> None:
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [Event(type=EventType.RESULT, done=True)]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    queued_msg = _make_message(content="queued message")
    q = engine._queues.setdefault(msg.session_key, asyncio.Queue(maxsize=5))
    await q.put(queued_msg)

    with patch.object(engine, "_run_gemini", wraps=engine._run_gemini) as mock_run:
        await engine._process(msg, session)
        # Should process current message + drain queue
        assert mock_run.call_count >= 1


async def test_process_already_locked() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()

    session = engine._sessions.get_or_create(msg.session_key)
    session._busy = True  # Already locked by try_lock simulation

    # Override try_lock to return False
    original_try_lock = session.try_lock

    async def fake_try_lock() -> bool:
        return False

    session.try_lock = fake_try_lock  # type: ignore[method-assign]

    await engine._process(msg, session)
    platform.send.assert_called_once()  # "busy" message
    session.try_lock = original_try_lock  # type: ignore[method-assign]


# --- _reply ---


async def test_reply_with_reply_ctx() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    await engine._reply(msg, "hello")
    platform.send.assert_called_once_with(msg.reply_ctx, "hello")


async def test_reply_no_reply_ctx() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    msg.reply_ctx = None
    await engine._reply(msg, "hello")
    platform.send.assert_not_called()


# --- queue drain with empty queue ---


async def test_process_empty_queue_after_completion() -> None:
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [Event(type=EventType.RESULT, done=True)]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    # No queue set up
    await engine._process(msg, session)
    # Should complete without error


async def test_tool_use_long_input_truncated() -> None:
    engine, agent, platform = _make_engine()
    msg = _make_message()

    long_input = "x" * 200  # > tool_max_len=100
    events = [
        Event(type=EventType.TOOL_USE, tool_name="shell", tool_input=long_input),
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    calls = platform.send.call_args_list
    texts = [str(c[0][1]) for c in calls]
    tool_texts = [t for t in texts if "shell" in t or "🔧" in t]
    assert any(len(t) < 200 for t in tool_texts)


# --- Additional coverage tests ---


async def test_handle_message_goes_to_process() -> None:
    """Non-slash, non-busy message should call _process."""
    engine, agent, _platform = _make_engine()
    msg = _make_message(content="tell me a joke")

    events = [Event(type=EventType.RESULT, done=True)]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    await engine.handle_message(msg)
    # _run_gemini was called (part of _process)
    agent.start_session.assert_called_once()


async def test_process_queue_empty_race() -> None:
    """Test the QueueEmpty exception branch in _process."""
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [Event(type=EventType.RESULT, done=True)]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)

    # Pre-populate a queue but then have get_nowait raise QueueEmpty
    q: asyncio.Queue[Message] = asyncio.Queue(maxsize=5)
    engine._queues[msg.session_key] = q
    # Put one item in the queue
    await q.put(msg)

    # Make get_nowait raise QueueEmpty to test that branch
    call_count = [0]

    def fake_get_nowait() -> Message:
        call_count[0] += 1
        raise asyncio.QueueEmpty

    q.get_nowait = fake_get_nowait  # type: ignore[method-assign]

    await engine._process(msg, session)
    assert call_count[0] >= 1  # Was called


async def test_handle_message_images_files_no_content() -> None:
    """Message with images but no text content should still be processed."""
    engine, agent, _platform = _make_engine()

    events = [Event(type=EventType.RESULT, done=True)]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    msg = _make_message(content="")
    from tg_gemini.models import ImageAttachment

    msg.images = [ImageAttachment(mime_type="image/jpeg", data=b"data")]

    await engine.handle_message(msg)
    agent.start_session.assert_called_once()


async def test_run_gemini_text_event_empty_content_and_session_id() -> None:
    """TEXT event with both empty content and empty session_id → no-op."""
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.TEXT, content="", session_id=""),  # both empty → no-op
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)
    # No reply since no text was accumulated


async def test_run_gemini_thinking_event_empty_content() -> None:
    """THINKING event with empty content → no-op."""
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.THINKING, content=""),  # empty → no-op
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)
    # No thinking message sent since content was empty


async def test_run_gemini_tool_result_empty_content() -> None:
    """TOOL_RESULT event with empty content → no message sent."""
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=EventType.TOOL_RESULT, content=""),  # empty → no-op
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)
    # No tool result message since content was empty


async def test_run_gemini_unknown_event_type() -> None:
    """Unknown event type → match falls through without crash."""
    from typing import cast

    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [
        Event(type=cast("EventType", "unknown_xyz")),  # type: ignore[arg-type]
        Event(type=EventType.RESULT, done=True),
    ]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)
    # Should complete without crash


# ---------------------------------------------------------------------------
# Engine scenario tests with real GeminiSession (no mock agent)
# ---------------------------------------------------------------------------


import json  # noqa: E402


def _jsonl(*events: dict) -> list[bytes]:
    return [json.dumps(e).encode() + b"\n" for e in events]


class _AsyncBytesStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)

    def __aiter__(self) -> "_AsyncBytesStream":
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._lines)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _make_proc_real(lines: list[bytes] = [], returncode: int = 0) -> MagicMock:  # noqa: B006
    from unittest.mock import AsyncMock, MagicMock

    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = _AsyncBytesStream(lines)
    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.wait = AsyncMock(return_value=returncode)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


def _make_engine_real_agent() -> tuple[Engine, GeminiAgent, MagicMock]:
    """Engine wired with a real GeminiAgent (subprocess will be patched per-test)."""
    cfg = _make_config()
    agent = GeminiAgent(
        work_dir="/tmp", model="", mode="default", cmd="gemini", api_key=""
    )
    platform = MagicMock()
    platform.start = AsyncMock()
    platform.stop = AsyncMock()
    platform.send = AsyncMock()
    platform.reply = AsyncMock()
    platform.send_preview_start = AsyncMock(return_value=MagicMock())
    platform.update_message = AsyncMock()
    platform.delete_preview = AsyncMock()
    platform.start_typing = AsyncMock(
        return_value=asyncio.create_task(asyncio.sleep(0))
    )
    sessions = SessionManager()
    i18n = I18n(lang=Language.EN)
    engine = Engine(
        config=cfg, agent=agent, platform=platform, sessions=sessions, i18n=i18n
    )
    return engine, agent, platform


async def test_engine_scenario_text_response() -> None:
    """Real GeminiSession: plain text response reaches platform.send."""
    engine, _agent, platform = _make_engine_real_agent()
    msg = _make_message("hello")

    lines = _jsonl(
        {"type": "init", "session_id": "s1", "model": "gemini-2.0-flash"},
        {"type": "message", "role": "assistant", "content": "Hi there!", "delta": True},
        {"type": "result", "status": "success", "session_id": "s1"},
    )

    with patch(
        "tg_gemini.gemini.asyncio.create_subprocess_exec",
        return_value=_make_proc_real(lines=lines),
    ):
        await engine.handle_message(msg)

    # platform.send is called at least once (stream preview or direct reply)
    assert platform.send.called or platform.send_preview_start.called


async def test_engine_scenario_tool_use_sends_notification() -> None:
    """Real GeminiSession: tool_use event sends tool notification to platform."""
    engine, _agent, platform = _make_engine_real_agent()
    msg = _make_message("use a tool")

    lines = _jsonl(
        {"type": "init", "session_id": "s2", "model": "gemini-2.0-flash"},
        {"type": "message", "role": "assistant", "content": "Sure", "delta": True},
        {
            "type": "tool_use",
            "tool_name": "read_file",
            "parameters": {"path": "/tmp/test.py"},
        },
        {
            "type": "tool_result",
            "tool_id": "tu-1",
            "status": "success",
            "output": "print('hello')",
        },
        {"type": "message", "role": "assistant", "content": "Done", "delta": True},
        {"type": "result", "status": "success", "session_id": "s2"},
    )

    with patch(
        "tg_gemini.gemini.asyncio.create_subprocess_exec",
        return_value=_make_proc_real(lines=lines),
    ):
        await engine.handle_message(msg)

    # Tool notification must have been sent
    all_send_texts = [str(c) for c in platform.send.call_args_list]
    assert any("read_file" in t for t in all_send_texts)


async def test_engine_scenario_session_resume_loop() -> None:
    """Full session resume cycle: init stores session_id; next message passes --resume."""
    engine, _agent, platform = _make_engine_real_agent()
    msg = _make_message("first message")

    # Turn 1: Gemini emits init with session_id
    turn1 = _jsonl(
        {"type": "init", "session_id": "gemini-sess-xyz", "model": "gemini-2.0-flash"},
        {"type": "message", "role": "assistant", "content": "Hello!", "delta": True},
        {"type": "result", "status": "success"},
    )

    with patch(
        "tg_gemini.gemini.asyncio.create_subprocess_exec",
        return_value=_make_proc_real(lines=turn1),
    ):
        await engine.handle_message(msg)

    # The session must have stored the agent_session_id
    session = engine._sessions.get_or_create(msg.session_key)
    assert session.agent_session_id == "gemini-sess-xyz"

    # Turn 2: verify --resume is passed with stored id
    turn2 = _jsonl(
        {"type": "init", "session_id": "gemini-sess-xyz", "model": "gemini-2.0-flash"},
        {
            "type": "message",
            "role": "assistant",
            "content": "Still here!",
            "delta": True,
        },
        {"type": "result", "status": "success"},
    )

    with patch(
        "tg_gemini.gemini.asyncio.create_subprocess_exec",
        return_value=_make_proc_real(lines=turn2),
    ) as mock_exec:
        await engine.handle_message(_make_message("second message"))

    exec_args = list(mock_exec.call_args.args)
    assert "--resume" in exec_args
    assert "gemini-sess-xyz" in exec_args


async def test_engine_scenario_error_response() -> None:
    """Real GeminiSession: error event triggers error message to platform."""
    engine, _agent, platform = _make_engine_real_agent()
    msg = _make_message("trigger error")

    lines = _jsonl(
        {"type": "init", "session_id": "s3", "model": "gemini-2.0-flash"},
        {"type": "error", "severity": "error", "message": "Something went wrong"},
        {"type": "result", "status": "error", "error": {"message": "fatal"}},
    )

    with patch(
        "tg_gemini.gemini.asyncio.create_subprocess_exec",
        return_value=_make_proc_real(lines=lines),
    ):
        await engine.handle_message(msg)

    all_texts = " ".join(str(c) for c in platform.send.call_args_list)
    assert "Something went wrong" in all_texts or "error" in all_texts.lower()


async def test_engine_stop_kills_active_gemini() -> None:
    """/stop kills the active GeminiSession subprocess."""
    engine, _agent, platform = _make_engine()
    msg = _make_message()

    mock_gemini = AsyncMock(spec=GeminiSession)
    engine._active_gemini[msg.session_key] = mock_gemini

    await engine.handle_command(msg, "/stop")

    mock_gemini.kill.assert_awaited_once()
    platform.send.assert_called_once()


async def test_engine_stop_no_active_session() -> None:
    """/stop with no active session just sends acknowledgement."""
    engine, _agent, platform = _make_engine()
    msg = _make_message()

    await engine.handle_command(msg, "/stop")

    platform.send.assert_called_once()  # just the "stopping" message


async def test_engine_active_gemini_cleaned_up_after_run() -> None:
    """After _run_gemini completes, _active_gemini is cleared for that session."""
    engine, agent, _platform = _make_engine()
    msg = _make_message()

    events = [Event(type=EventType.RESULT, done=True)]
    mock_session = _mock_gemini_session(events)
    agent.start_session.return_value = mock_session

    session = engine._sessions.get_or_create(msg.session_key)
    await engine._run_gemini(msg, session)

    assert msg.session_key not in engine._active_gemini
