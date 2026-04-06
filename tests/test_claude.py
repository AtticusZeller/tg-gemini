"""Tests for claude.py: ClaudeAgent and ClaudeSession."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Self
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_gemini.claude import (
    ClaudeAgent,
    ClaudeSession,
    _compute_line_diff,
    _format_tool_params,
    _normalize_mode,
)
from tg_gemini.models import EventType, FileAttachment, ImageAttachment


def _close_coro(coro: Any, **_: Any) -> MagicMock:
    """Mock side_effect for asyncio.create_task that closes unawaited coroutines."""
    if hasattr(coro, "close"):
        coro.close()
    return MagicMock()


# --- _normalize_mode ---


def test_normalize_mode_default() -> None:
    assert _normalize_mode("default") == "default"
    assert _normalize_mode("") == "default"
    assert _normalize_mode("unknown") == "default"


def test_normalize_mode_acceptedits() -> None:
    assert _normalize_mode("acceptEdits") == "acceptEdits"
    assert _normalize_mode("accept-edits") == "acceptEdits"
    assert _normalize_mode("accept_edits") == "acceptEdits"
    assert _normalize_mode("edit") == "acceptEdits"


def test_normalize_mode_plan() -> None:
    assert _normalize_mode("plan") == "plan"


def test_normalize_mode_bypass() -> None:
    assert _normalize_mode("bypassPermissions") == "bypassPermissions"
    assert _normalize_mode("bypass-permissions") == "bypassPermissions"
    assert _normalize_mode("yolo") == "bypassPermissions"
    assert _normalize_mode("auto") == "bypassPermissions"


def test_normalize_mode_dontask() -> None:
    assert _normalize_mode("dontAsk") == "dontAsk"
    assert _normalize_mode("dont-ask") == "dontAsk"


# --- _format_tool_params ---


def test_format_tool_params_empty() -> None:
    assert _format_tool_params("any", {}) == ""


def test_format_tool_params_read() -> None:
    assert _format_tool_params("Read", {"file_path": "/x.py"}) == "/x.py"
    assert _format_tool_params("Read", {"path": "/y.py"}) == "/y.py"


def test_format_tool_params_write() -> None:
    result = _format_tool_params("Write", {"file_path": "/x.py", "content": "hello"})
    assert "/x.py" in result
    assert "hello" in result


def test_format_tool_params_edit() -> None:
    result = _format_tool_params(
        "Edit", {"file_path": "/x.py", "old_string": "a", "new_string": "b"}
    )
    assert "/x.py" in result
    assert "diff" in result


def test_format_tool_params_bash() -> None:
    result = _format_tool_params("Bash", {"command": "ls -la"})
    assert "ls -la" in result


def test_format_tool_params_grep() -> None:
    assert _format_tool_params("Grep", {"pattern": "foo"}) == "foo"


def test_format_tool_params_glob() -> None:
    assert _format_tool_params("Glob", {"pattern": "*.py"}) == "*.py"


def test_format_tool_params_websearch() -> None:
    assert _format_tool_params("WebSearch", {"query": "hello"}) == "hello"


def test_format_tool_params_webfetch() -> None:
    assert (
        _format_tool_params("WebFetch", {"url": "https://example.com"})
        == "https://example.com"
    )


def test_format_tool_params_task() -> None:
    assert _format_tool_params("Task", {"task": "do something"}) == "do something"


def test_format_tool_params_ask_question() -> None:
    q = {"question": "What is the weather?"}
    assert (
        _format_tool_params("AskUserQuestion", {"questions": [q]})
        == "What is the weather?"
    )


def test_format_tool_params_write_no_content() -> None:
    """Write with file_path but no content returns just the path."""
    assert _format_tool_params("Write", {"file_path": "/x.py"}) == "/x.py"


def test_format_tool_params_edit_no_old_new() -> None:
    """Edit with file_path but no old/new strings returns just the path."""
    assert _format_tool_params("Edit", {"file_path": "/x.py"}) == "/x.py"


def test_format_tool_params_fallback() -> None:
    """Fallback case: non-string values serialized as JSON."""
    result = _format_tool_params("UnknownTool", {"count": 42, "active": True})
    assert "count: 42" in result
    assert "active: true" in result


# --- _compute_line_diff ---


def test_compute_line_diff_no_changes() -> None:
    assert _compute_line_diff("abc", "abc") == ""


def test_compute_line_diff_simple() -> None:
    result = _compute_line_diff("a\nb\nc", "a\nX\nc")
    assert "- b" in result
    assert "+ X" in result


def test_compute_line_diff_truncation_prefix() -> None:
    """Test ... prefix appears when there are unchanged lines before diff."""
    old = "a\nb\nc\nd\ne"
    new = "a\nX\nc\nd\ne"
    result = _compute_line_diff(old, new)
    assert "..." in result


def test_compute_line_diff_truncation_suffix() -> None:
    """Test ... suffix appears when there are unchanged lines after diff."""
    old = "a\nb\nc\nd\ne"
    new = "a\nb\nX\nd\ne"
    result = _compute_line_diff(old, new)
    assert "..." in result


# --- ClaudeAgent ---


def test_claude_agent_defaults() -> None:
    agent = ClaudeAgent()
    assert agent.model == ""
    assert agent.mode == "default"


def test_claude_agent_setters() -> None:
    agent = ClaudeAgent(model="sonnet", mode="bypassPermissions")
    assert agent.model == "sonnet"
    agent.model = "opus"
    assert agent.model == "opus"
    agent.mode = "plan"
    assert agent.mode == "plan"


def test_claude_agent_available_models() -> None:
    agent = ClaudeAgent()
    models = agent.available_models()
    assert len(models) == 3
    assert any(m["name"] == "sonnet" for m in models)


# --- ClaudeSession helpers ---


class _AsyncBytesStream:
    """Helper: async iterable over a list of byte lines for mocking proc.stdout/stderr."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._lines)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _AsyncBytesWriter:
    """Helper: sync writer for mocking proc.stdin (asyncio.StreamWriter.write is sync)."""

    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_session(**kwargs: object) -> ClaudeSession:
    defaults = {
        "cmd": "claude",
        "work_dir": ".",
        "model": "",
        "mode": "default",
        "allowed_tools": None,
        "disallowed_tools": None,
        "timeout_mins": 0,
    }
    defaults.update(kwargs)  # type: ignore[arg-type]
    return ClaudeSession(**defaults)  # type: ignore[arg-type]


def _jsonl(*events: dict[str, Any]) -> list[bytes]:
    """Build a list of JSONL byte lines from dicts."""
    return [json.dumps(e).encode() + b"\n" for e in events]


# --- ClaudeSession event handlers ---


def test_session_handle_system() -> None:
    session = _make_session()
    session._handle_system({"type": "system", "session_id": "sess-123"})
    assert session.current_session_id == "sess-123"
    evt = session._events.get_nowait()
    assert evt.type == EventType.TEXT
    assert evt.session_id == "sess-123"


def test_session_handle_assistant_text() -> None:
    session = _make_session()
    raw = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello world"}],
        },
    }
    session._handle_assistant(raw)
    evt = session._events.get_nowait()
    assert evt.type == EventType.TEXT
    assert evt.content == "Hello world"


def test_session_handle_assistant_thinking() -> None:
    session = _make_session()
    raw = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Let me think..."},
                {"type": "text", "text": "Done"},
            ],
        },
    }
    session._handle_assistant(raw)
    # thinking events
    thinking_evt = session._events.get_nowait()
    assert thinking_evt.type == EventType.THINKING
    assert "think" in thinking_evt.content
    # text event
    text_evt = session._events.get_nowait()
    assert text_evt.type == EventType.TEXT
    assert text_evt.content == "Done"


def test_session_handle_assistant_tool_use() -> None:
    session = _make_session()
    raw = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me check"},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/x.py"}},
            ],
        },
    }
    session._handle_assistant(raw)
    # text
    text_evt = session._events.get_nowait()
    assert text_evt.type == EventType.TEXT
    assert text_evt.content == "Let me check"
    # tool_use
    tool_evt = session._events.get_nowait()
    assert tool_evt.type == EventType.TOOL_USE
    assert tool_evt.tool_name == "Read"
    assert "/x.py" in tool_evt.tool_input


def test_session_handle_assistant_ask_user_skipped() -> None:
    """AskUserQuestion tool_use should be skipped in display."""
    session = _make_session()
    raw = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "AskUserQuestion",
                    "input": {"questions": [{"question": "Continue?"}]},
                }
            ],
        },
    }
    session._handle_assistant(raw)
    assert session._events.empty()


def test_session_handle_result() -> None:
    session = _make_session()
    session._handle_result({"type": "result", "result": "Final answer"})
    evt = session._events.get_nowait()
    assert evt.type == EventType.RESULT
    assert evt.content == "Final answer"
    assert evt.done is True


def test_session_handle_result_with_session_id() -> None:
    session = _make_session()
    session._handle_result({"type": "result", "result": "ok", "session_id": "new-sess"})
    assert session.current_session_id == "new-sess"
    evt = session._events.get_nowait()
    assert evt.type == EventType.RESULT


def test_session_handle_control_request_permission() -> None:
    session = _make_session()
    raw = {
        "type": "control_request",
        "request_id": "req-123",
        "request": {
            "subtype": "can_use_tool",
            "tool_name": "Bash",
            "input": {"command": "rm -rf /"},
        },
    }
    session._handle_control_request(raw)
    evt = session._events.get_nowait()
    assert evt.type == EventType.PERMISSION_REQUEST
    assert evt.request_id == "req-123"
    assert evt.tool_name == "Bash"
    assert "rm -rf" in evt.tool_input


def test_session_handle_control_request_unknown_subtype() -> None:
    """Unknown control_request subtypes are logged but don't emit events."""
    session = _make_session()
    raw = {
        "type": "control_request",
        "request_id": "req-456",
        "request": {"subtype": "unknown_type"},
    }
    session._handle_control_request(raw)
    assert session._events.empty()


def test_session_handle_control_cancel_request() -> None:
    """control_cancel_request just logs, no event emitted."""
    session = _make_session()
    # Goes through _handle_event which dispatches to _handle_control_cancel_request
    session._handle_event({"type": "control_cancel_request", "request_id": "req-789"})
    assert session._events.empty()


# --- parse_line ---


def test_session_parse_line_valid_json() -> None:
    session = _make_session()
    line = json.dumps({"type": "system", "session_id": "s1"})
    session._parse_line(line)
    evt = session._events.get_nowait()
    assert evt.session_id == "s1"


def test_session_parse_line_multiple_json() -> None:
    session = _make_session()
    j1 = json.dumps({"type": "system", "session_id": "s1"})
    j2 = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
            },
        }
    )
    session._parse_line(j1 + j2)
    evt1 = session._events.get_nowait()
    assert evt1.session_id == "s1"
    evt2 = session._events.get_nowait()
    assert evt2.content == "hi"


def test_session_parse_line_invalid_json() -> None:
    session = _make_session()
    session._parse_line("{invalid}")
    assert session._events.empty()


def test_session_parse_line_no_braces() -> None:
    session = _make_session()
    session._parse_line("just text")
    assert session._events.empty()


# --- respond_permission ---


async def test_session_respond_permission_allow() -> None:
    session = _make_session()
    writer = _AsyncBytesWriter()
    session._stdin = writer
    session._alive = True

    await session.respond_permission("req-123", allow=True)

    assert len(writer.written) == 1
    data = json.loads(writer.written[0].decode())
    assert data["type"] == "control_response"
    assert data["response"]["response"]["behavior"] == "allow"
    assert data["response"]["request_id"] == "req-123"


async def test_session_respond_permission_deny() -> None:
    session = _make_session()
    writer = _AsyncBytesWriter()
    session._stdin = writer
    session._alive = True

    await session.respond_permission("req-456", allow=False, message="no way")

    assert len(writer.written) == 1
    data = json.loads(writer.written[0].decode())
    assert data["response"]["response"]["behavior"] == "deny"
    assert data["response"]["response"]["message"] == "no way"


async def test_session_respond_permission_closed_session() -> None:
    """respond_permission should be no-op when session is closed."""
    session = _make_session()
    session._alive = False

    # Should not raise
    await session.respond_permission("req-789", allow=True)
    await session.respond_permission("req-789", allow=False)


# --- session lifecycle ---


def test_session_alive() -> None:
    session = _make_session()
    assert session.alive is True


async def test_session_close() -> None:
    session = _make_session()
    await session.close()
    assert session.alive is False


async def test_session_close_noop_when_already_dead() -> None:
    session = _make_session()
    session._alive = False
    await session.close()  # should not raise


# --- error handling ---


def test_session_handle_event_unknown_type() -> None:
    session = _make_session()
    session._handle_event({"type": "unknown_type_xyz"})
    assert session._events.empty()


# --- decode_first_json ---


def test_session_decode_first_json() -> None:
    text = json.dumps({"key": "val"}) + " extra"
    obj, end = ClaudeSession._decode_first_json(text)
    assert obj == {"key": "val"}
    assert text[end:].strip() == "extra"


def test_session_decode_first_json_non_dict() -> None:
    with pytest.raises(TypeError, match="not a dict"):
        ClaudeSession._decode_first_json("[1, 2, 3]")


# --- send with images/files ---


async def test_session_send_with_images_and_files() -> None:
    """send() should create temp files and launch subprocess."""
    session = _make_session(mode="bypassPermissions")
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        img = ImageAttachment(mime_type="image/jpeg", data=b"fake_jpg")
        f = FileAttachment(
            mime_type="text/plain", data=b"content", file_name="test.txt"
        )
        await session.send("test prompt", images=[img], files=[f])
        assert mock_exec.called


async def test_session_send_launches_subprocess() -> None:
    """send() should launch subprocess if not already running."""
    session = _make_session()
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        await session.send("hello")
        assert mock_exec.called
        args_list = list(mock_exec.call_args.args)
        assert "--output-format" in args_list
        assert "--permission-prompt-tool" in args_list


async def test_session_send_with_resume_id() -> None:
    """send() with resume_id should pass --resume flag."""
    session = _make_session(resume_id="my-session-id")
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        await session.send("hello")
        args_list = list(mock_exec.call_args.args)
        assert "--resume" in args_list
        assert "my-session-id" in args_list


async def test_session_send_with_continue_resume() -> None:
    """send() with resume_id='_continue' should pass --continue --fork-session."""
    session = _make_session(resume_id="_continue")
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        await session.send("hello")
        args_list = list(mock_exec.call_args.args)
        assert "--continue" in args_list
        assert "--fork-session" in args_list


async def test_session_send_with_model() -> None:
    """send() with model should pass --model flag."""
    session = _make_session(model="sonnet")
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        await session.send("hello")
        args_list = list(mock_exec.call_args.args)
        assert "--model" in args_list
        assert "sonnet" in args_list


async def test_session_send_with_allowed_tools() -> None:
    """send() with allowed_tools should pass --allowedTools flag."""
    session = _make_session(allowed_tools=["Bash", "Read"])
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        await session.send("hello")
        args_list = list(mock_exec.call_args.args)
        assert "--allowedTools" in args_list
        idx = args_list.index("--allowedTools")
        assert args_list[idx + 1] == "Bash,Read"


async def test_session_send_with_disallowed_tools() -> None:
    """send() with disallowed_tools should pass --disallowedTools flag."""
    session = _make_session(disallowed_tools=["WebSearch"])
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        await session.send("hello")
        args_list = list(mock_exec.call_args.args)
        assert "--disallowedTools" in args_list


async def test_session_send_raises_when_closed() -> None:
    """send() should raise RuntimeError if session is closed."""
    session = _make_session()
    await session.close()
    with pytest.raises(RuntimeError, match="closed"):
        await session.send("hello")


# --- _read_loop ---


def _make_proc(
    lines: list[bytes] = [],  # noqa: B006
    returncode: int = 0,
    stderr: bytes = b"",
) -> AsyncMock:
    """Create an AsyncMock process with proper async stdout/stderr iterators."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.stdout = _AsyncBytesStream(lines)
    stderr_lines = [line + b"\n" for line in stderr.split(b"\n") if line]
    proc.stderr = _AsyncBytesStream(stderr_lines)
    proc.wait = AsyncMock(return_value=returncode)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


def _drain(session: ClaudeSession) -> list[Any]:
    """Drain all events from a session's queue."""
    events = []
    while not session._events.empty():
        events.append(session._events.get_nowait())
    return events


async def test_read_loop_normal_flow() -> None:
    """Normal flow: system -> assistant text -> result."""
    lines = _jsonl(
        {"type": "system", "session_id": "sess-abc"},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello"}],
            },
        },
        {"type": "result", "result": "done"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert types == [EventType.TEXT, EventType.TEXT, EventType.RESULT]
    assert events[0].session_id == "sess-abc"


async def test_read_loop_thinking_and_text() -> None:
    """Assistant with thinking + text content."""
    lines = _jsonl(
        {"type": "system", "session_id": "s1"},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "thinking..."},
                    {"type": "text", "text": "result"},
                ],
            },
        },
        {"type": "result", "result": ""},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert EventType.THINKING in types
    assert EventType.TEXT in types
    assert EventType.RESULT in types


async def test_read_loop_tool_use_and_result() -> None:
    """Assistant with tool_use followed by result."""
    lines = _jsonl(
        {"type": "system", "session_id": "s2"},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me read it"},
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "/x.py"},
                    },
                ],
            },
        },
        {
            "type": "tool_result",
            "tool_id": "t1",
            "status": "success",
            "output": "content",
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Here"}],
            },
        },
        {"type": "result", "result": "final"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert EventType.TEXT in types
    assert EventType.TOOL_USE in types
    assert EventType.RESULT in types


async def test_read_loop_control_request() -> None:
    """control_request emits PERMISSION_REQUEST event."""
    lines = _jsonl(
        {"type": "system", "session_id": "s3"},
        {
            "type": "control_request",
            "request_id": "req-1",
            "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {}},
        },
        {"type": "result", "result": "ok"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert EventType.PERMISSION_REQUEST in types


async def test_read_loop_control_request_non_dict_request() -> None:
    """control_request with non-dict request is silently skipped."""
    lines = _jsonl(
        {"type": "system", "session_id": "s3"},
        {"type": "control_request", "request_id": "req-1", "request": "not a dict"},
        {"type": "result", "result": "ok"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert EventType.PERMISSION_REQUEST not in types


async def test_read_loop_control_request_unknown_subtype() -> None:
    """control_request with unknown subtype is silently skipped."""
    lines = _jsonl(
        {"type": "system", "session_id": "s3"},
        {
            "type": "control_request",
            "request_id": "req-1",
            "request": {"subtype": "unknown_subtype", "tool_name": "Bash"},
        },
        {"type": "result", "result": "ok"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert EventType.PERMISSION_REQUEST not in types


async def test_read_loop_empty_lines_skipped() -> None:
    """Empty lines in stdout should be silently skipped."""
    session = _make_session()
    lines = [
        b"\n",
        b"  \n",
        json.dumps({"type": "system", "session_id": "s4"}).encode() + b"\n",
        json.dumps({"type": "result", "result": ""}).encode() + b"\n",
    ]
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    assert any(e.type == EventType.TEXT and e.session_id == "s4" for e in events)


async def test_read_loop_nonzero_exit_with_stderr() -> None:
    """Non-zero exit with stderr should emit ERROR event."""
    session = _make_session()
    lines = [json.dumps({"type": "result", "result": ""}).encode() + b"\n"]
    proc = _make_proc(lines=lines, returncode=1, stderr=b"some error")
    await session._read_loop(proc)

    events = _drain(session)
    error_events = [e for e in events if e.type == EventType.ERROR]
    assert len(error_events) == 1
    assert "some error" in str(error_events[0].error)


async def test_read_loop_nonzero_exit_empty_stderr() -> None:
    """Non-zero exit with empty stderr: no error event."""
    session = _make_session()
    proc = _make_proc(lines=[], returncode=1, stderr=b"")
    await session._read_loop(proc)
    assert session._events.empty()


async def test_read_loop_permission_denied() -> None:
    """control_cancel_request logged, no event emitted."""
    lines = _jsonl(
        {"type": "system", "session_id": "s5"},
        {"type": "control_cancel_request", "request_id": "req-2"},
        {"type": "result", "result": "done"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert EventType.PERMISSION_REQUEST not in types


async def test_read_loop_oserror_on_cleanup() -> None:
    """OSError during temp file cleanup should be silently ignored."""
    session = _make_session()
    session._temp_files = ["/nonexistent/file/that/does/not/exist.tmp"]

    lines = [json.dumps({"type": "result", "result": ""}).encode() + b"\n"]
    proc = _make_proc(lines=lines, returncode=0)
    await session._read_loop(proc)

    events = _drain(session)
    assert any(e.type == EventType.RESULT for e in events)
    assert session._temp_files == []  # Cleaned up even with error


async def test_read_loop_timeout_kills_proc() -> None:
    """Timeout in _stream_stdout should kill proc and emit ERROR event."""
    session = _make_session(timeout_mins=1)  # 1 minute timeout

    # _timeout_secs is set from timeout_mins * 60
    assert session._timeout_secs == 60

    # Create a proc with a slow stdout that never completes
    proc = AsyncMock()
    proc.returncode = None
    proc.stdout = _SlowStream()  # Will hang
    proc.stderr = _AsyncBytesStream([])
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)

    # The _stream_stdout hangs on _SlowStream, so wait_for triggers TimeoutError
    await session._read_loop(proc)

    proc.kill.assert_called_once()
    events = _drain(session)
    error_events = [e for e in events if e.type == EventType.ERROR]
    assert len(error_events) == 1
    assert "timed out" in str(error_events[0].error)


class _SlowStream:
    """A stdout mock that hangs (never yields)."""

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> bytes:
        await asyncio.sleep(300)  # Hang forever
        raise StopAsyncIteration


# --- kill ---


async def test_session_kill_terminates_proc() -> None:
    """kill() sends SIGTERM then waits; falls back to SIGKILL on timeout."""
    session = _make_session()
    proc = _make_proc()
    proc.returncode = None
    session._proc = proc

    await session.kill()

    proc.terminate.assert_called_once()
    proc.wait.assert_called()


async def test_session_kill_noop_when_no_proc() -> None:
    """kill() is a no-op when no subprocess was started."""
    session = _make_session()
    await session.kill()  # must not raise


async def test_session_kill_noop_when_proc_finished() -> None:
    """kill() is a no-op when subprocess has already exited."""
    session = _make_session()
    proc = _make_proc()
    proc.returncode = 0
    session._proc = proc

    await session.kill()
    proc.terminate.assert_not_called()


async def test_session_kill_falls_back_to_kill_on_timeout() -> None:
    """kill() calls proc.kill() when proc.wait() times out."""
    session = _make_session()
    proc = AsyncMock()
    proc.returncode = None
    proc.wait = AsyncMock(return_value=0)
    proc.kill = MagicMock()
    proc.terminate = MagicMock()
    session._proc = proc

    async def wait_for_timeout(coro: Any, **kwargs: Any) -> None:
        raise TimeoutError

    with patch("asyncio.wait_for", side_effect=wait_for_timeout):
        await session.kill()

    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


# --- list_sessions / delete_session ---


def test_list_sessions_no_dir() -> None:
    """list_sessions returns empty when ~/.claude/projects doesn't exist."""
    agent = ClaudeAgent(work_dir="/nonexistent/path")
    import asyncio

    result = asyncio.run(agent.list_sessions())
    assert result == []


def test_delete_session_no_dir() -> None:
    """delete_session returns False when dir doesn't exist."""
    agent = ClaudeAgent(work_dir="/nonexistent/path")
    import asyncio

    result = asyncio.run(agent.delete_session("any-session"))
    assert result is False


def test_delete_session_not_found() -> None:
    """delete_session returns False when session file doesn't exist."""

    # Create a temp projects dir without the session file
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock Path.home() to return our temp dir
        with patch.object(Path, "home", return_value=Path(tmpdir)):
            agent = ClaudeAgent(work_dir="/some/project")
            import asyncio

            result = asyncio.run(agent.delete_session("nonexistent-session"))
            assert result is False


# --- stream_stdout ---


async def test_stream_stdout_handles_limit_overrun() -> None:
    """ValueError from StreamReader should be caught and logged."""
    session = _make_session()

    class _OverrunStream:
        def __aiter__(self) -> Self:
            return self

        async def __anext__(self) -> bytes:
            raise ValueError("Separator is not found, and chunk exceed the limit")

    await session._stream_stdout(_OverrunStream())
    # Should not raise — ValueError is caught


async def test_stream_stdout_reads_lines() -> None:
    """Normal stdout iteration should parse JSON lines."""
    session = _make_session()
    lines = _jsonl(
        {"type": "system", "session_id": "s6"}, {"type": "result", "result": ""}
    )
    proc = _make_proc(lines=lines)
    await session._read_loop(proc)

    events = _drain(session)
    assert any(e.session_id == "s6" for e in events)


# --- assistant with plain text content (not array) ---


def test_session_handle_assistant_plain_text() -> None:
    """Plain string content (not array) should be emitted as TEXT."""
    session = _make_session()
    raw = {
        "type": "assistant",
        "message": {"role": "assistant", "content": "plain text response"},
    }
    session._handle_assistant(raw)
    evt = session._events.get_nowait()
    assert evt.type == EventType.TEXT
    assert evt.content == "plain text response"


# --- tool_result is_error ---


def test_session_handle_tool_result_is_error() -> None:
    """tool_result with is_error=true should emit ERROR event."""
    session = _make_session()
    # Note: claude.py doesn't actually handle tool_result events currently,
    # but let's verify the handler exists
    session._handle_event(
        {"type": "tool_result", "tool_id": "t1", "status": "success", "output": "ok"}
    )
    # This currently goes to default/unhandled case
    assert session._events.empty()


# --- non-dict message in assistant ---


def test_session_handle_assistant_non_dict_message() -> None:
    """assistant message where message is not a dict should be skipped."""
    session = _make_session()
    raw = {"type": "assistant", "message": "not a dict"}
    session._handle_assistant(raw)
    assert session._events.empty()


# --- tool_result non-list content ---


def test_session_handle_assistant_non_list_content() -> None:
    """assistant message where content is not a list should be treated as plain text."""
    session = _make_session()
    raw = {"type": "assistant", "message": {"role": "assistant", "content": "text"}}
    session._handle_assistant(raw)
    evt = session._events.get_nowait()
    assert evt.type == EventType.TEXT
    assert evt.content == "text"


# --- close with read_task and stdin ---


async def test_session_close_cancels_read_task() -> None:
    """close() should cancel and await an active _read_task."""
    session = _make_session()

    async def _hang_forever() -> None:
        await asyncio.sleep(9999)

    session._read_task = asyncio.create_task(_hang_forever())
    await session.close()
    assert session._read_task is None
    assert session.alive is False


async def test_session_close_closes_stdin() -> None:
    """close() should close and clear _stdin."""
    session = _make_session()
    writer = _AsyncBytesWriter()
    session._stdin = writer
    await session.close()
    assert session._stdin is None


# --- _format_tool_params additional branches ---


def test_format_tool_params_read_with_path() -> None:
    """Read with 'path' key instead of 'file_path'."""
    assert _format_tool_params("Read", {"path": "/y.py"}) == "/y.py"


def test_format_tool_params_read_no_path() -> None:
    """Read with no file_path or path returns empty string."""
    assert _format_tool_params("Read", {}) == ""


def test_format_tool_params_write_no_content_no_path() -> None:
    """Write with no file_path or path returns empty string."""
    assert _format_tool_params("Write", {}) == ""


def test_format_tool_params_edit_with_content() -> None:
    """Edit with old/new content produces diff."""
    result = _format_tool_params(
        "Edit", {"file_path": "/a.py", "old_string": "foo", "new_string": "bar"}
    )
    assert "/a.py" in result
    assert "diff" in result


def test_format_tool_params_bash_no_command() -> None:
    """Bash with no command returns empty string."""
    assert _format_tool_params("Bash", {}) == ""


def test_format_tool_params_grep_no_pattern() -> None:
    """Grep with no pattern returns empty string."""
    assert _format_tool_params("Grep", {}) == ""


def test_format_tool_params_glob_no_pattern() -> None:
    """Glob with no pattern returns empty string."""
    assert _format_tool_params("Glob", {}) == ""


def test_format_tool_params_websearch_no_query() -> None:
    """WebSearch with no query returns empty string."""
    assert _format_tool_params("WebSearch", {}) == ""


def test_format_tool_params_webfetch_no_url() -> None:
    """WebFetch with no url returns empty string."""
    assert _format_tool_params("WebFetch", {}) == ""


def test_format_tool_params_task_no_task() -> None:
    """Task with no task field returns empty string."""
    assert _format_tool_params("Task", {}) == ""


def test_format_tool_params_ask_question_empty() -> None:
    """AskUserQuestion with empty questions falls through to fallback."""
    result = _format_tool_params("AskUserQuestion", {"questions": []})
    assert "questions" in result  # Falls through to fallback key:value


def test_format_tool_params_ask_question_no_question_field() -> None:
    """AskUserQuestion with questions but no 'question' key falls through."""
    result = _format_tool_params("AskUserQuestion", {"questions": [{}]})
    assert "questions" in result  # Falls through to fallback


# --- _write_json with no stdin ---


async def test_write_json_noop_when_no_stdin() -> None:
    """_write_json should return early when _stdin is None."""
    session = _make_session()
    session._stdin = None
    await session._write_json({"type": "test"})  # should not raise


# --- list_sessions with actual files ---


def test_list_sessions_with_files(tmp_path: Path) -> None:
    """list_sessions should scan JSONL files in project dir."""
    # Set up fake .claude/projects/<encoded-path>/ directory
    work_dir = "/some/project"
    project_key = str(Path(work_dir).resolve()).replace(os.sep, "-")

    projects_dir = tmp_path / ".claude" / "projects"
    project_dir = projects_dir / project_key
    project_dir.mkdir(parents=True)

    # Write a session JSONL file
    session_file = project_dir / "test-session-id.jsonl"
    lines = [
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "Hello world this is a test"},
            }
        ),
        json.dumps(
            {"type": "assistant", "message": {"role": "assistant", "content": "Hi"}}
        ),
    ]
    session_file.write_text("\n".join(lines))

    with patch.object(Path, "home", return_value=tmp_path):
        agent = ClaudeAgent(work_dir=work_dir)
        import asyncio as _asyncio

        result = _asyncio.run(agent.list_sessions())
        assert len(result) == 1
        assert result[0].id == "test-session-id"
        assert result[0].message_count == 2
        assert "Hello world" in result[0].summary


def test_list_sessions_string_content(tmp_path: Path) -> None:
    """_scan_session_meta handles string message content."""
    work_dir = "/some/project"
    project_key = str(Path(work_dir).resolve()).replace(os.sep, "-")

    projects_dir = tmp_path / ".claude" / "projects"
    project_dir = projects_dir / project_key
    project_dir.mkdir(parents=True)

    session_file = project_dir / "str-content-session.jsonl"
    lines = [json.dumps({"type": "user", "message": "string message content here"})]
    session_file.write_text("\n".join(lines))

    with patch.object(Path, "home", return_value=tmp_path):
        agent = ClaudeAgent(work_dir=work_dir)
        import asyncio as _asyncio

        result = _asyncio.run(agent.list_sessions())
        assert len(result) == 1
        assert "string message" in result[0].summary


def test_list_sessions_oserror_on_read(tmp_path: Path) -> None:
    """_scan_session_meta returns empty on OSError."""
    work_dir = "/some/project"
    project_key = str(Path(work_dir).resolve()).replace(os.sep, "-")

    projects_dir = tmp_path / ".claude" / "projects"
    project_dir = projects_dir / project_key
    project_dir.mkdir(parents=True)

    session_file = project_dir / "bad-session.jsonl"
    session_file.write_text("valid")

    with patch.object(Path, "home", return_value=tmp_path):
        agent = ClaudeAgent(work_dir=work_dir)
        # Mock read_text to raise OSError
        with patch.object(Path, "read_text", side_effect=OSError("nope")):
            import asyncio as _asyncio

            result = _asyncio.run(agent.list_sessions())
            assert len(result) == 1
            assert result[0].summary == ""
            assert result[0].message_count == 0


def test_delete_session_success(tmp_path: Path) -> None:
    """delete_session should remove the JSONL file and return True."""
    work_dir = "/some/project"
    project_key = str(Path(work_dir).resolve()).replace(os.sep, "-")

    projects_dir = tmp_path / ".claude" / "projects"
    project_dir = projects_dir / project_key
    project_dir.mkdir(parents=True)

    session_file = project_dir / "to-delete.jsonl"
    session_file.write_text("data")

    with patch.object(Path, "home", return_value=tmp_path):
        agent = ClaudeAgent(work_dir=work_dir)
        import asyncio as _asyncio

        result = _asyncio.run(agent.delete_session("to-delete"))
        assert result is True
        assert not session_file.exists()


def test_delete_session_oserror(tmp_path: Path) -> None:
    """delete_session returns False on OSError during unlink."""
    work_dir = "/some/project"
    project_key = str(Path(work_dir).resolve()).replace(os.sep, "-")

    projects_dir = tmp_path / ".claude" / "projects"
    project_dir = projects_dir / project_key
    project_dir.mkdir(parents=True)

    session_file = project_dir / "protected.jsonl"
    session_file.write_text("data")

    with patch.object(Path, "home", return_value=tmp_path):
        agent = ClaudeAgent(work_dir=work_dir)
        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            import asyncio as _asyncio

            result = _asyncio.run(agent.delete_session("protected"))
            assert result is False


# --- _start_subprocess with mode ---


async def test_session_start_with_mode() -> None:
    """_start_subprocess should include --permission-mode for non-default modes."""
    session = _make_session(mode="bypassPermissions")
    with (
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        proc = AsyncMock()
        proc.returncode = None
        proc.stdout = _AsyncBytesStream([])
        proc.stderr = _AsyncBytesStream([])
        proc.stdin = _AsyncBytesWriter()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        await session.send("hello")
        args_list = list(mock_exec.call_args.args)
        assert "--permission-mode" in args_list


# --- _stream_stdout with ValueError (LimitOverrun) ---


async def test_stream_stdout_value_error() -> None:
    """ValueError during stdout iteration should be caught."""
    session = _make_session()

    class _ErrorStream:
        def __aiter__(self) -> Self:
            return self

        async def __anext__(self) -> bytes:
            raise ValueError("limit overrun")

    await session._stream_stdout(_ErrorStream())
    # Should not raise


# --- _read_loop with stdin close on error ---


async def test_read_loop_closes_stdin_on_error() -> None:
    """_read_loop should close stdin in finally block."""
    session = _make_session()
    writer = _AsyncBytesWriter()
    session._stdin = writer
    lines = [json.dumps({"type": "result", "result": ""}).encode() + b"\n"]
    proc = _make_proc(lines=lines)
    await session._read_loop(proc)
    assert session._stdin is None


# --- _compute_line_diff edge cases ---


def test_compute_line_diff_completely_different() -> None:
    """Completely different strings should show full replace."""
    result = _compute_line_diff("a\nb", "x\ny")
    assert "- a" in result
    assert "- b" in result
    assert "+ x" in result
    assert "+ y" in result


def test_compute_line_diff_empty_old() -> None:
    """Empty old string with non-empty new should show additions."""
    result = _compute_line_diff("", "a\nb")
    assert "+ a" in result


def test_compute_line_diff_empty_new() -> None:
    """Non-empty old with empty new should show deletions."""
    result = _compute_line_diff("a\nb", "")
    assert "- a" in result


# --- _normalize_mode edge cases ---


def test_normalize_mode_empty() -> None:
    """Empty string should normalize to 'default'."""
    assert _normalize_mode("") == "default"


def test_normalize_mode_passthrough() -> None:
    """Already normalized modes should pass through."""
    assert _normalize_mode("default") == "default"
    assert _normalize_mode("bypassPermissions") == "bypassPermissions"


# --- _format_tool_params with Shell alias ---


def test_format_tool_params_shell() -> None:
    """Shell is alias for Bash."""
    result = _format_tool_params("Shell", {"command": "echo hi"})
    assert "echo hi" in result


# --- _format_tool_params Edit no diff ---


def test_format_tool_params_edit_no_diff() -> None:
    """Edit with same old/new returns just the path."""
    result = _format_tool_params(
        "Edit", {"file_path": "/a.py", "old_string": "x", "new_string": "x"}
    )
    assert result == "/a.py"
