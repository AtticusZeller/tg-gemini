"""Tests for claude.py: ClaudeAgent and ClaudeSession."""

import json
from typing import Any, Self
from unittest.mock import MagicMock

import pytest

from tg_gemini.claude import (
    ClaudeAgent,
    ClaudeSession,
    _compute_line_diff,
    _format_tool_params,
    _normalize_mode,
)
from tg_gemini.models import EventType


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


# --- _compute_line_diff ---


def test_compute_line_diff_no_changes() -> None:
    assert _compute_line_diff("abc", "abc") == ""


def test_compute_line_diff_simple() -> None:
    result = _compute_line_diff("a\nb\nc", "a\nX\nc")
    assert "- b" in result
    assert "+ X" in result


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
            "content": [
                {"type": "text", "text": "Hello world"},
            ],
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
                {
                    "type": "tool_use",
                    "name": "Read",
                    "input": {"file_path": "/x.py"},
                },
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
                },
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
    session._handle_event(
        {"type": "control_cancel_request", "request_id": "req-789"}
    )
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
    j2 = json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}})
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
