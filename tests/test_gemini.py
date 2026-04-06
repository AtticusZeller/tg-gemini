"""Tests for gemini.py: GeminiAgent and GeminiSession."""

import asyncio
import json
from typing import Any, Self
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_gemini.gemini import (
    GeminiAgent,
    GeminiSession,
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


def test_normalize_mode_yolo() -> None:
    assert _normalize_mode("yolo") == "yolo"
    assert _normalize_mode("auto") == "yolo"
    assert _normalize_mode("force") == "yolo"
    assert _normalize_mode("YOLO") == "yolo"


def test_normalize_mode_auto_edit() -> None:
    assert _normalize_mode("auto_edit") == "auto_edit"
    assert _normalize_mode("autoedit") == "auto_edit"
    assert _normalize_mode("edit") == "auto_edit"


def test_normalize_mode_plan() -> None:
    assert _normalize_mode("plan") == "plan"


def test_normalize_mode_default() -> None:
    assert _normalize_mode("default") == "default"
    assert _normalize_mode("unknown") == "default"
    assert _normalize_mode("") == "default"


# --- _format_tool_params ---


def test_format_tool_params_empty() -> None:
    assert _format_tool_params("any", {}) == ""


def test_format_tool_params_shell() -> None:
    assert _format_tool_params("shell", {"command": "ls -la"}) == "```bash\nls -la\n```"
    assert (
        _format_tool_params("Bash", {"command": "echo hi"}) == "```bash\necho hi\n```"
    )
    assert (
        _format_tool_params("run_shell_command", {"command": "pwd"})
        == "```bash\npwd\n```"
    )


def test_format_tool_params_shell_no_command() -> None:
    result = _format_tool_params("shell", {"other": "value"})
    assert "other" in result


def test_format_tool_params_write_file() -> None:
    result = _format_tool_params(
        "write_file", {"file_path": "/tmp/f.py", "content": "x=1"}
    )
    assert "/tmp/f.py" in result
    assert "x=1" in result


def test_format_tool_params_write_file_no_content() -> None:
    result = _format_tool_params("write_file", {"file_path": "/tmp/f.py"})
    assert result == "/tmp/f.py"


def test_format_tool_params_write_file_path_alias() -> None:
    result = _format_tool_params("WriteFile", {"path": "/tmp/f.py", "content": "x=1"})
    assert "/tmp/f.py" in result


def test_format_tool_params_write_file_no_path() -> None:
    result = _format_tool_params("write_file", {"content": "x=1"})
    # Falls through to fallback
    assert "content" in result


def test_format_tool_params_replace() -> None:
    result = _format_tool_params(
        "replace", {"file_path": "/f.py", "old_string": "a", "new_string": "b"}
    )
    assert "/f.py" in result
    assert "diff" in result


def test_format_tool_params_replace_alt_keys() -> None:
    result = _format_tool_params(
        "ReplaceInFile", {"path": "/f.py", "old_str": "a", "new_str": "b"}
    )
    assert "/f.py" in result


def test_format_tool_params_replace_no_diff() -> None:
    result = _format_tool_params("replace", {"file_path": "/f.py"})
    assert result == "/f.py"


def test_format_tool_params_replace_no_path() -> None:
    result = _format_tool_params("replace", {"old_string": "a", "new_string": "b"})
    # No file_path → fallback
    assert "old_string" in result or "a" in result


def test_format_tool_params_read_file() -> None:
    assert _format_tool_params("read_file", {"file_path": "/f.py"}) == "/f.py"
    assert _format_tool_params("ReadFile", {"path": "/f.py"}) == "/f.py"


def test_format_tool_params_read_file_no_path() -> None:
    result = _format_tool_params("read_file", {"other": "x"})
    assert "other" in result


def test_format_tool_params_list_directory() -> None:
    assert _format_tool_params("list_directory", {"dir_path": "/tmp"}) == "/tmp"
    assert _format_tool_params("ListDirectory", {"path": "/tmp"}) == "/tmp"
    assert _format_tool_params("list_directory", {"directory": "/tmp"}) == "/tmp"


def test_format_tool_params_list_directory_no_path() -> None:
    result = _format_tool_params("list_directory", {"other": "x"})
    assert "other" in result


def test_format_tool_params_web_fetch() -> None:
    assert _format_tool_params("web_fetch", {"prompt": "hello"}) == "hello"
    assert _format_tool_params("WebFetch", {"url": "http://x.com"}) == "http://x.com"


def test_format_tool_params_web_fetch_no_prompt() -> None:
    result = _format_tool_params("web_fetch", {"other": "x"})
    assert "other" in result


def test_format_tool_params_web_search() -> None:
    assert _format_tool_params("google_web_search", {"query": "foo"}) == "foo"
    assert _format_tool_params("GoogleWebSearch", {"query": "bar"}) == "bar"


def test_format_tool_params_web_search_no_query() -> None:
    result = _format_tool_params("google_web_search", {"other": "x"})
    assert "other" in result


def test_format_tool_params_activate_skill() -> None:
    assert _format_tool_params("activate_skill", {"name": "commit"}) == "commit"


def test_format_tool_params_activate_skill_no_name() -> None:
    result = _format_tool_params("activate_skill", {"other": "x"})
    assert "other" in result


def test_format_tool_params_search() -> None:
    assert _format_tool_params("Glob", {"pattern": "*.py"}) == "*.py"
    assert _format_tool_params("Grep", {"query": "foo"}) == "foo"
    assert _format_tool_params("grep_search", {"pattern": "bar"}) == "bar"


def test_format_tool_params_search_no_key() -> None:
    result = _format_tool_params("Glob", {"other": "x"})
    assert "other" in result


def test_format_tool_params_save_memory() -> None:
    assert (
        _format_tool_params("save_memory", {"fact": "remember this"}) == "remember this"
    )


def test_format_tool_params_save_memory_no_fact() -> None:
    result = _format_tool_params("save_memory", {"other": "x"})
    assert "other" in result


def test_format_tool_params_ask_user() -> None:
    params = {"questions": [{"question": "What is it?"}]}
    assert _format_tool_params("ask_user", params) == "What is it?"


def test_format_tool_params_ask_user_empty() -> None:
    result = _format_tool_params("ask_user", {"questions": []})
    # Falls through to fallback
    assert "questions" in result or result == ""


def test_format_tool_params_ask_user_no_questions_key() -> None:
    result = _format_tool_params("ask_user", {"other": "x"})
    assert "other" in result


def test_format_tool_params_enter_plan_mode() -> None:
    assert _format_tool_params("enter_plan_mode", {"reason": "planning"}) == "planning"


def test_format_tool_params_enter_plan_mode_no_reason() -> None:
    result = _format_tool_params("enter_plan_mode", {"other": "x"})
    assert "other" in result


def test_format_tool_params_exit_plan_mode() -> None:
    assert (
        _format_tool_params("exit_plan_mode", {"plan_path": "/plan.md"}) == "/plan.md"
    )


def test_format_tool_params_exit_plan_mode_no_path() -> None:
    result = _format_tool_params("exit_plan_mode", {"other": "x"})
    assert "other" in result


def test_format_tool_params_fallback_non_string() -> None:
    result = _format_tool_params("unknown_tool", {"count": 42, "flag": True})
    assert "count" in result
    assert "flag" in result


def test_format_tool_params_fallback_string() -> None:
    result = _format_tool_params("unknown_tool", {"key": "value"})
    assert "key: value" in result


# --- _compute_line_diff ---


def test_compute_line_diff_no_changes() -> None:
    assert _compute_line_diff("abc", "abc") == ""


def test_compute_line_diff_simple() -> None:
    result = _compute_line_diff("a\nb\nc", "a\nX\nc")
    assert "- b" in result
    assert "+ X" in result


def test_compute_line_diff_all_different() -> None:
    result = _compute_line_diff("a\nb", "c\nd")
    assert "- a" in result
    assert "- b" in result
    assert "+ c" in result
    assert "+ d" in result


def test_compute_line_diff_context_truncated() -> None:
    old = "ctx1\nctx2\nold_line\nctx3\nctx4"
    new = "ctx1\nctx2\nnew_line\nctx3\nctx4"
    result = _compute_line_diff(old, new)
    assert "- old_line" in result
    assert "+ new_line" in result


def test_compute_line_diff_prefix_ellipsis() -> None:
    old = "a\nb\nc\nd\ne"
    new = "a\nb\nc\nX\ne"
    result = _compute_line_diff(old, new)
    assert "..." in result


# --- GeminiAgent ---


def test_gemini_agent_defaults() -> None:
    agent = GeminiAgent()
    assert agent.model == ""
    assert agent.mode == "default"


def test_gemini_agent_setters() -> None:
    agent = GeminiAgent(model="flash", mode="yolo")
    assert agent.model == "flash"
    agent.model = "pro"
    assert agent.model == "pro"
    agent.mode = "plan"
    assert agent.mode == "plan"


def test_gemini_agent_available_models() -> None:
    agent = GeminiAgent()
    models = agent.available_models()
    assert len(models) > 0
    assert any("gemini" in m.name for m in models)


def test_gemini_agent_start_session() -> None:
    agent = GeminiAgent(model="flash", mode="yolo", cmd="gemini")
    session = agent.start_session()
    assert session is not None
    assert session.current_session_id == ""


def test_gemini_agent_start_session_with_resume() -> None:
    agent = GeminiAgent()
    session = agent.start_session(resume_id="test-session-123")
    assert session.current_session_id == "test-session-123"


# --- GeminiSession ---


def test_gemini_session_alive() -> None:
    session = GeminiSession(
        cmd="gemini", work_dir=".", model="", mode="default", api_key="", timeout_mins=0
    )
    assert session.alive is True


async def test_gemini_session_close() -> None:
    session = GeminiSession(
        cmd="gemini", work_dir=".", model="", mode="default", api_key="", timeout_mins=0
    )
    await session.close()
    assert session.alive is False


async def test_gemini_session_send_raises_when_closed() -> None:
    session = GeminiSession(
        cmd="gemini", work_dir=".", model="", mode="default", api_key="", timeout_mins=0
    )
    await session.close()
    with pytest.raises(RuntimeError, match="closed"):
        await session.send("hello")


def _make_session(**kwargs: object) -> GeminiSession:
    defaults = {
        "cmd": "gemini",
        "work_dir": ".",
        "model": "",
        "mode": "default",
        "api_key": "",
        "timeout_mins": 0,
    }
    defaults.update(kwargs)  # type: ignore[arg-type]
    return GeminiSession(**defaults)  # type: ignore[arg-type]


def test_session_handle_init() -> None:
    session = _make_session()
    session._handle_init({"type": "init", "session_id": "sid123", "model": "flash"})
    assert session.current_session_id == "sid123"
    evt = session._events.get_nowait()
    assert evt.type == EventType.TEXT
    assert evt.session_id == "sid123"
    assert evt.tool_name == "flash"


def test_session_handle_init_no_sid() -> None:
    session = _make_session()
    session._handle_init({"type": "init"})
    assert session.current_session_id == ""
    assert session._events.empty()


def test_session_handle_message_delta() -> None:
    session = _make_session()
    session._handle_message({"role": "assistant", "content": "hello", "delta": True})
    evt = session._events.get_nowait()
    assert evt.type == EventType.TEXT
    assert evt.content == "hello"


def test_session_handle_message_non_delta() -> None:
    session = _make_session()
    session._handle_message({"role": "assistant", "content": "buffered"})
    assert session._events.empty()
    assert "buffered" in session._pending_msgs


def test_session_handle_message_user_role() -> None:
    session = _make_session()
    session._handle_message({"role": "user", "content": "hello"})
    assert session._events.empty()
    assert not session._pending_msgs


def test_session_handle_message_empty_content() -> None:
    session = _make_session()
    session._handle_message({"role": "assistant", "content": ""})
    assert session._events.empty()


def test_session_handle_tool_use() -> None:
    session = _make_session()
    session._pending_msgs = ["thinking text"]
    session._handle_tool_use(
        {"tool_name": "read_file", "tool_id": "id1", "parameters": {"file_path": "/x"}}
    )
    # Pending should have been flushed as thinking first
    thinking_evt = session._events.get_nowait()
    assert thinking_evt.type == EventType.THINKING
    assert thinking_evt.content == "thinking text"
    # Then tool_use event
    tool_evt = session._events.get_nowait()
    assert tool_evt.type == EventType.TOOL_USE
    assert tool_evt.tool_name == "read_file"


def test_session_handle_tool_use_non_dict_params() -> None:
    session = _make_session()
    session._handle_tool_use(
        {"tool_name": "run_shell_command", "tool_id": "id1", "parameters": "not a dict"}
    )
    evt = session._events.get_nowait()
    assert evt.type == EventType.TOOL_USE
    assert evt.tool_input == ""


def test_session_handle_tool_result_success() -> None:
    session = _make_session()
    session._handle_tool_result(
        {"tool_id": "id1", "status": "success", "output": "file content"}
    )
    evt = session._events.get_nowait()
    assert evt.type == EventType.TOOL_RESULT
    assert "file content" in evt.content


def test_session_handle_tool_result_truncates() -> None:
    session = _make_session()
    long_output = "x" * 600
    session._handle_tool_result(
        {"tool_id": "id1", "status": "success", "output": long_output}
    )
    evt = session._events.get_nowait()
    assert len(evt.content) <= 505  # 500 + "..."


def test_session_handle_tool_result_error() -> None:
    session = _make_session()
    session._handle_tool_result(
        {"tool_id": "id1", "status": "error", "error": {"message": "file not found"}}
    )
    evt = session._events.get_nowait()
    assert "Error: file not found" in evt.content


def test_session_handle_tool_result_error_no_message() -> None:
    session = _make_session()
    session._handle_tool_result(
        {"tool_id": "id1", "status": "error", "output": "err msg"}
    )
    evt = session._events.get_nowait()
    assert evt.content == "err msg"


def test_session_handle_tool_result_empty_output() -> None:
    session = _make_session()
    session._handle_tool_result({"tool_id": "id1", "status": "success", "output": ""})
    assert session._events.empty()


def test_session_handle_error() -> None:
    session = _make_session()
    session._handle_error({"severity": "error", "message": "something failed"})
    evt = session._events.get_nowait()
    assert evt.type == EventType.ERROR
    assert evt.error is not None
    assert "something failed" in str(evt.error)


def test_session_handle_error_empty_message() -> None:
    session = _make_session()
    session._handle_error({"severity": "error", "message": ""})
    assert session._events.empty()


def test_session_handle_result_success() -> None:
    session = _make_session()
    session._pending_msgs = ["final answer"]
    session._session_id = "sid1"
    session._handle_result({"status": "success", "stats": {}})
    # Pending flushed as text
    text_evt = session._events.get_nowait()
    assert text_evt.type == EventType.TEXT
    assert text_evt.content == "final answer"
    # Then result event
    result_evt = session._events.get_nowait()
    assert result_evt.type == EventType.RESULT
    assert result_evt.done is True
    assert result_evt.session_id == "sid1"
    assert result_evt.error is None


def test_session_handle_result_error() -> None:
    session = _make_session()
    session._handle_result(
        {"status": "error", "error": {"message": "turn limit exceeded"}}
    )
    evt = session._events.get_nowait()
    assert evt.type == EventType.RESULT
    assert evt.done is True
    assert evt.error is not None


def test_session_handle_result_error_no_message() -> None:
    session = _make_session()
    session._handle_result({"status": "error"})
    evt = session._events.get_nowait()
    assert evt.type == EventType.RESULT
    assert evt.done is True
    assert evt.error is None


def test_session_flush_pending_as_thinking_empty() -> None:
    session = _make_session()
    session._flush_pending_as_thinking()
    assert session._events.empty()


def test_session_flush_pending_as_text_empty() -> None:
    session = _make_session()
    session._flush_pending_as_text()
    assert session._events.empty()


def test_session_parse_line_valid_json() -> None:
    session = _make_session()
    line = json.dumps({"type": "init", "session_id": "s1", "model": "flash"})
    session._parse_line(line)
    evt = session._events.get_nowait()
    assert evt.session_id == "s1"


def test_session_parse_line_multiple_json() -> None:
    session = _make_session()
    j1 = json.dumps({"type": "init", "session_id": "s1", "model": "flash"})
    j2 = json.dumps(
        {"type": "message", "role": "assistant", "content": "hi", "delta": True}
    )
    session._parse_line(j1 + j2)
    assert not session._events.empty()
    session._events.get_nowait()  # init evt
    evt = session._events.get_nowait()  # text evt
    assert evt.content == "hi"


def test_session_parse_line_invalid_json() -> None:
    session = _make_session()
    session._parse_line("{invalid json}")
    assert session._events.empty()


def test_session_parse_line_no_braces() -> None:
    session = _make_session()
    session._parse_line("no json here")
    assert session._events.empty()


def test_session_parse_line_non_dict_json() -> None:
    session = _make_session()
    session._parse_line(json.dumps([1, 2, 3]))
    assert session._events.empty()


def test_session_handle_event_unknown_type() -> None:
    session = _make_session()
    session._handle_event({"type": "unknown_type_xyz"})
    assert session._events.empty()


def test_session_decode_first_json() -> None:
    text = json.dumps({"key": "val"}) + " extra"
    obj, end = GeminiSession._decode_first_json(text)
    assert obj == {"key": "val"}
    assert text[end:].strip() == "extra"


def test_session_decode_first_json_non_dict() -> None:
    with pytest.raises(TypeError, match="not a dict"):
        GeminiSession._decode_first_json("[1, 2, 3]")


class _AsyncBytesStream:
    """Helper: async iterable over a list of byte lines for mocking proc.stdout."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._lines)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _make_proc(
    lines: list[bytes] = [],  # noqa: B006
    returncode: int = 0,
    stderr: bytes = b"",
) -> AsyncMock:
    """Create an AsyncMock process with a proper async stdout iterator."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.stdout = _AsyncBytesStream(lines)
    # stderr is drained via async-for; split into lines for iteration
    stderr_lines = [line + b"\n" for line in stderr.split(b"\n") if line]
    proc.stderr = _AsyncBytesStream(stderr_lines)
    proc.wait = AsyncMock(return_value=returncode)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


def _jsonl(*events: dict[str, Any]) -> list[bytes]:
    """Build a list of JSONL byte lines from dicts."""
    return [json.dumps(e).encode() + b"\n" for e in events]


async def test_session_send_with_images_and_files() -> None:
    """Test that send() creates temp files for images/files and launches subprocess."""
    session = _make_session(mode="yolo")
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()) as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        img = ImageAttachment(mime_type="image/jpeg", data=b"fake_jpg")
        f = FileAttachment(
            mime_type="text/plain", data=b"content", file_name="test.txt"
        )
        await session.send("test prompt", images=[img], files=[f])
        assert mock_exec.called
        args_list = list(mock_exec.call_args.args)
        assert "-y" in args_list


async def test_session_send_auto_edit_mode() -> None:
    session = _make_session(mode="auto_edit")
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()) as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("test")
        args_list = list(mock_exec.call_args.args)
        assert "--approval-mode" in args_list
        assert "auto_edit" in args_list


async def test_session_send_plan_mode() -> None:
    session = _make_session(mode="plan")
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()) as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("test")
        args_list = list(mock_exec.call_args.args)
        assert "plan" in args_list


async def test_session_send_default_mode() -> None:
    session = _make_session(mode="default")
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()) as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("test")
        args_list = list(mock_exec.call_args.args)
        assert "-y" not in args_list
        assert "--approval-mode" not in args_list


async def test_session_send_with_model() -> None:
    session = _make_session(model="gemini-2.5-flash")
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()) as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("test")
        args_list = list(mock_exec.call_args.args)
        assert "-m" in args_list
        assert "gemini-2.5-flash" in args_list


async def test_session_send_with_resume_id() -> None:
    session = _make_session(resume_id="my-session-id")
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()) as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("test")
        args_list = list(mock_exec.call_args.args)
        assert "--resume" in args_list
        assert "my-session-id" in args_list


async def test_session_send_with_api_key() -> None:
    session = _make_session(api_key="my_api_key")
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()) as mock_exec,
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("test")
        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("env", {}).get("GEMINI_API_KEY") == "my_api_key"


async def test_session_send_with_timeout() -> None:
    session = _make_session(timeout_mins=1)
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()),
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("test")


async def test_read_loop_stderr_error() -> None:
    """Test that stderr errors are emitted as EventError."""
    session = _make_session()
    lines = [json.dumps({"type": "result", "status": "success"}).encode() + b"\n"]
    proc = _make_proc(lines=lines, returncode=1, stderr=b"gemini: command failed")
    await session._read_loop(proc)

    events = []
    while not session._events.empty():
        events.append(session._events.get_nowait())
    error_events = [e for e in events if e.type == EventType.ERROR]
    assert len(error_events) == 1
    assert "gemini: command failed" in str(error_events[0].error)


async def test_read_loop_no_stderr() -> None:
    """Test read_loop when subprocess exits with 0 and empty stderr."""
    session = _make_session()
    lines = [
        json.dumps({"type": "init", "session_id": "s1", "model": "flash"}).encode()
        + b"\n",
        json.dumps({"type": "result", "status": "success"}).encode() + b"\n",
    ]
    proc = _make_proc(lines=lines, returncode=0)
    await session._read_loop(proc)

    events = []
    while not session._events.empty():
        events.append(session._events.get_nowait())
    assert any(e.session_id == "s1" for e in events)
    assert any(e.type == EventType.RESULT for e in events)


async def test_read_loop_nonzero_exit_empty_stderr() -> None:
    """Non-zero exit but empty stderr → no error event."""
    session = _make_session()
    proc = _make_proc(lines=[], returncode=1, stderr=b"")
    await session._read_loop(proc)
    assert session._events.empty()


async def test_session_image_mime_types() -> None:
    """Test that different image MIME types get correct extensions."""
    for mime, expected_ext in [
        ("image/jpeg", ".jpg"),
        ("image/gif", ".gif"),
        ("image/webp", ".webp"),
        ("image/png", ".png"),
    ]:
        session = _make_session()
        with (
            patch(
                "asyncio.create_subprocess_exec", return_value=_make_proc()
            ) as mock_exec,
            patch("asyncio.create_task", side_effect=_close_coro),
        ):
            img = ImageAttachment(mime_type=mime, data=b"data")
            await session.send("test", images=[img])
            args_list = list(mock_exec.call_args.args)
            p_idx = args_list.index("-p")
            prompt = str(args_list[p_idx + 1])
            assert expected_ext in prompt


# --- Additional coverage tests ---


def test_session_events_property() -> None:
    """Test the events property."""
    session = _make_session()
    q = session.events
    assert isinstance(q, asyncio.Queue)


def test_session_handle_event_dispatches_tool_use() -> None:
    session = _make_session()
    raw = {
        "type": "tool_use",
        "tool_name": "read_file",
        "tool_id": "id1",
        "parameters": {"file_path": "/x"},
    }
    session._handle_event(raw)
    assert not session._events.empty()
    evt = session._events.get_nowait()
    assert evt.type == EventType.TOOL_USE


def test_session_handle_event_dispatches_tool_result() -> None:
    session = _make_session()
    raw = {
        "type": "tool_result",
        "tool_id": "id1",
        "status": "success",
        "output": "result",
    }
    session._handle_event(raw)
    assert not session._events.empty()
    evt = session._events.get_nowait()
    assert evt.type == EventType.TOOL_RESULT


def test_session_handle_event_dispatches_error() -> None:
    session = _make_session()
    raw = {"type": "error", "severity": "error", "message": "bad thing happened"}
    session._handle_event(raw)
    assert not session._events.empty()
    evt = session._events.get_nowait()
    assert evt.type == EventType.ERROR


async def test_read_loop_empty_line_skipped() -> None:
    """Empty lines in stdout should be silently skipped."""
    session = _make_session()
    lines = [
        b"\n",  # empty line
        b"  \n",  # whitespace-only line
        json.dumps({"type": "result", "status": "success"}).encode() + b"\n",
    ]
    proc = _make_proc(lines=lines, returncode=0)
    await session._read_loop(proc)

    events = []
    while not session._events.empty():
        events.append(session._events.get_nowait())
    assert any(e.type == EventType.RESULT for e in events)


async def test_read_loop_oserror_on_cleanup() -> None:
    """OSError during temp file cleanup should be silently ignored."""
    session = _make_session()
    session._temp_files = ["/nonexistent/file/that/does/not/exist.tmp"]

    lines = [json.dumps({"type": "result", "status": "success"}).encode() + b"\n"]
    proc = _make_proc(lines=lines, returncode=0)
    await session._read_loop(proc)

    events = []
    while not session._events.empty():
        events.append(session._events.get_nowait())
    assert any(e.type == EventType.RESULT for e in events)
    assert session._temp_files == []  # Cleaned up even with error


def test_format_tool_params_ask_user_non_dict_question() -> None:
    """ask_user with non-dict first question falls through to fallback."""
    params = {"questions": ["not a dict"]}
    result = _format_tool_params("ask_user", params)
    # Falls through to fallback since q0 is not a dict
    assert "questions" in result or result == ""


def test_session_handle_tool_result_error_with_none_error() -> None:
    """tool_result with status=error but error field is not a dict."""
    session = _make_session()
    session._handle_tool_result(
        {"tool_id": "id1", "status": "error", "error": None, "output": "err"}
    )
    evt = session._events.get_nowait()
    assert evt.content == "err"


# ---------------------------------------------------------------------------
# JSONL fixture integration tests — full event sequences through _read_loop
# ---------------------------------------------------------------------------


def _drain(session: GeminiSession) -> list[Any]:
    events = []
    while not session._events.empty():
        events.append(session._events.get_nowait())
    return events


async def test_read_loop_normal_flow() -> None:
    """Normal flow: init → user msg (skipped) → assistant delta → tool → result."""
    lines = _jsonl(
        {"type": "init", "session_id": "sess-abc", "model": "gemini-2.0-flash"},
        {"type": "message", "role": "user", "content": "hello"},
        {"type": "message", "role": "assistant", "content": "I'll help", "delta": True},
        {
            "type": "tool_use",
            "tool_name": "read_file",
            "parameters": {"path": "foo.py"},
        },
        {
            "type": "tool_result",
            "tool_id": "tu-1",
            "status": "success",
            "output": "print('hi')",
        },
        {"type": "message", "role": "assistant", "content": " Done!", "delta": True},
        {"type": "result", "status": "success", "session_id": "sess-abc"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert types == [
        EventType.TEXT,  # init
        EventType.TEXT,  # assistant delta 1
        EventType.TOOL_USE,  # tool_use
        EventType.TOOL_RESULT,
        EventType.TEXT,  # assistant delta 2
        EventType.RESULT,
    ]
    assert events[0].session_id == "sess-abc"
    assert events[1].content == "I'll help"
    assert events[2].tool_name == "read_file"
    assert "print('hi')" in (events[3].content or "")
    assert events[4].content == " Done!"
    assert events[5].done is True
    # session_id must be stored on the session object
    assert session.current_session_id == "sess-abc"


async def test_read_loop_warning_non_fatal() -> None:
    """Warning severity error followed by success result."""
    lines = _jsonl(
        {"type": "init", "session_id": "sess-warn", "model": "gemini-2.0-flash"},
        {
            "type": "error",
            "severity": "warning",
            "message": "Context limit approaching",
        },
        {"type": "result", "status": "success", "session_id": "sess-warn"},
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert EventType.TEXT in types  # init
    assert EventType.ERROR in types  # warning emitted as ERROR
    assert EventType.RESULT in types  # still succeeds
    result = next(e for e in events if e.type == EventType.RESULT)
    assert result.done is True
    assert result.error is None


async def test_read_loop_turn_limit_fatal() -> None:
    """Turn-limit error + result:error (FatalTurnLimitedError)."""
    lines = _jsonl(
        {"type": "init", "session_id": "sess-limit", "model": "gemini-2.0-flash"},
        {"type": "error", "severity": "error", "message": "Turn limit exceeded"},
        {
            "type": "result",
            "status": "error",
            "session_id": "sess-limit",
            "error": {"type": "FatalTurnLimitedError", "message": "Turn limit reached"},
        },
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert types[0] == EventType.TEXT  # init
    assert EventType.ERROR in types  # turn limit error event
    result = next(e for e in events if e.type == EventType.RESULT)
    assert result.done is True
    assert result.error is not None


async def test_read_loop_fatal_auth_error() -> None:
    """Fatal auth error: only init + result:error, no intermediate events."""
    lines = _jsonl(
        {"type": "init", "session_id": "sess-auth", "model": "gemini-2.0-flash"},
        {
            "type": "result",
            "status": "error",
            "session_id": "sess-auth",
            "error": {"type": "FatalAuthenticationError", "message": "Auth failed"},
        },
    )
    session = _make_session()
    await session._read_loop(_make_proc(lines=lines))

    events = _drain(session)
    types = [e.type for e in events]
    assert types[0] == EventType.TEXT  # init
    result = next(e for e in events if e.type == EventType.RESULT)
    assert result.done is True
    assert result.error is not None
    assert len([e for e in events if e.type == EventType.ERROR]) == 0


async def test_read_loop_result_stats_logged(caplog: Any) -> None:
    """result event with stats triggers a log entry."""
    import logging

    lines = _jsonl(
        {"type": "init", "session_id": "sess-stats", "model": "gemini-2.0-flash"},
        {
            "type": "result",
            "status": "success",
            "session_id": "sess-stats",
            "stats": {"input_tokens": 100, "output_tokens": 50},
        },
    )
    session = _make_session()
    with caplog.at_level(logging.INFO, logger="tg_gemini.gemini"):
        await session._read_loop(_make_proc(lines=lines))
    # The stats are logged via loguru — verify result event was emitted
    events = _drain(session)
    assert any(e.type == EventType.RESULT for e in events)


async def test_read_loop_timeout_kills_process() -> None:
    """When timeout fires, proc.kill() is called and ERROR event is emitted."""
    session = _make_session(timeout_mins=1)  # _timeout_secs = 60
    proc = _make_proc()

    def _timeout_with_close(coro: Any, **_: Any) -> None:
        if hasattr(coro, "close"):
            coro.close()
        raise TimeoutError

    with patch("tg_gemini.gemini.asyncio.wait_for", side_effect=_timeout_with_close):
        await session._read_loop(proc)

    proc.kill.assert_called_once()
    events = _drain(session)
    error_events = [e for e in events if e.type == EventType.ERROR]
    assert len(error_events) == 1
    assert "timed out" in str(error_events[0].error).lower()


async def test_session_kill_terminates_proc() -> None:
    """kill() sends SIGTERM then waits; falls back to SIGKILL on timeout."""
    session = _make_session()
    proc = _make_proc()
    proc.returncode = None  # process still running
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
    proc.returncode = 0  # already finished
    session._proc = proc

    await session.kill()
    proc.terminate.assert_not_called()


async def test_session_close_calls_kill() -> None:
    """close() sets alive=False and calls kill()."""
    session = _make_session()
    proc = _make_proc()
    proc.returncode = None
    session._proc = proc

    await session.close()

    assert not session.alive
    proc.terminate.assert_called_once()


async def test_read_loop_task_done_callback_on_exception() -> None:
    """Fire-and-forget task's done_callback logs errors from _read_loop."""
    session = _make_session()
    callback_exc: list[BaseException | None] = []

    def capture_callback(t: Any) -> None:
        callback_exc.append(t.exception() if not t.cancelled() else None)

    proc = _make_proc()

    with (
        patch(
            "tg_gemini.gemini.GeminiSession._stream_stdout",
            side_effect=RuntimeError("boom"),
        ),
        patch("asyncio.create_subprocess_exec", return_value=proc),
    ):
        task_holder: list[Any] = []

        original_create_task = asyncio.create_task

        def capture_task(coro: Any, **kwargs: Any) -> Any:
            t = original_create_task(coro, **kwargs)
            t.add_done_callback(capture_callback)
            task_holder.append(t)
            return t

        with patch("asyncio.create_task", side_effect=capture_task):
            await session.send("hello")

        if task_holder:
            with pytest.raises(RuntimeError):
                await task_holder[0]

    # The callback was invoked with the exception
    assert len(callback_exc) > 0


# ---------------------------------------------------------------------------
# Regression tests for stderr pipe-buffer deadlock (GH bug)
# ---------------------------------------------------------------------------


async def test_read_loop_stderr_drained_concurrently_with_stdout() -> None:
    """Regression: stderr must be drained alongside stdout to avoid pipe deadlock.

    Before the fix, _read_loop only read stdout; stderr was consumed after the
    process exited.  If the process wrote enough to stderr to fill the OS pipe
    buffer (~64 KB), it would block on stderr write, stop producing stdout, and
    the whole pipeline would hang silently until the engine timeout.
    """
    session = _make_session()
    # Simulate a process that writes both stdout JSONL events AND stderr output
    lines = _jsonl(
        {"type": "init", "session_id": "s-stderr-test", "model": "flash"},
        {"type": "message", "role": "assistant", "content": "working…", "delta": True},
        {"type": "result", "status": "success", "session_id": "s-stderr-test"},
    )
    proc = _make_proc(
        lines=lines, stderr=b"debug: step 1\ndebug: step 2\nwarning: something\n"
    )
    await session._read_loop(proc)

    events = _drain(session)
    types = [e.type for e in events]
    # All stdout events were processed despite concurrent stderr output
    assert EventType.TEXT in types  # init
    assert EventType.RESULT in types
    assert events[-1].done is True


async def test_read_loop_large_stderr_does_not_block_events() -> None:
    """Regression: even large stderr output should not block stdout event flow.

    This simulates the actual deadlock scenario: Gemini writes progress/debug
    info to stderr that fills the pipe buffer. Without concurrent draining,
    stdout events would stop arriving.
    """
    session = _make_session()
    lines = _jsonl(
        {"type": "init", "session_id": "s-big-stderr", "model": "pro"},
        {"type": "message", "role": "assistant", "content": "done", "delta": True},
        {"type": "result", "status": "success", "session_id": "s-big-stderr"},
    )
    # Large stderr output (simulating debug logging that fills pipe buffer)
    big_stderr = "\n".join(f"[debug] line {i}" for i in range(5000)).encode()
    proc = _make_proc(lines=lines, stderr=big_stderr)
    await session._read_loop(proc)

    events = _drain(session)
    # Verify all events came through despite large stderr
    result_events = [e for e in events if e.type == EventType.RESULT]
    assert len(result_events) == 1
    assert result_events[0].done is True


async def test_send_stores_read_task_on_session() -> None:
    """Regression: send() must store the _read_loop task for later cancellation.

    Before the fix, the task was created as fire-and-forget with no reference
    stored, making it impossible for close() to cancel it.  This caused
    'Task was destroyed but it is pending!' warnings.
    """
    session = _make_session()
    with (
        patch("asyncio.create_subprocess_exec", return_value=_make_proc()),
        patch("asyncio.create_task", side_effect=_close_coro),
    ):
        await session.send("hello")

    assert session._read_task is not None


async def test_close_cancels_read_task() -> None:
    """Regression: close() must cancel and await the stored _read_loop task.

    Without this, the _read_loop task outlives the session and produces
    'Task was destroyed but it is pending!' at GC time.
    """
    session = _make_session()

    # Simulate a read_task that is still running (never completed)
    async def _hang_forever() -> None:
        await asyncio.Event().wait()  # blocks forever

    mock_task = asyncio.create_task(_hang_forever())
    session._read_task = mock_task
    session._proc = _make_proc()

    await session.close()

    # The task must have been cancelled and cleared
    assert session._read_task is None
    assert mock_task.cancelled()


async def test_close_handles_already_done_read_task() -> None:
    """close() should be safe when _read_task has already completed."""
    session = _make_session()

    async def _already_done() -> None:
        pass

    done_task = asyncio.create_task(_already_done())
    # Let the task actually complete
    await asyncio.sleep(0)
    session._read_task = done_task
    session._proc = _make_proc()

    await session.close()

    assert session._read_task is None
    assert done_task.done()


async def test_close_noop_when_no_read_task() -> None:
    """close() is safe when _read_task is None (session never used)."""
    session = _make_session()
    session._proc = _make_proc()

    await session.close()

    assert session._read_task is None
    assert not session.alive


async def test_read_loop_stderr_multiline_on_error() -> None:
    """Multi-line stderr on non-zero exit is captured and emitted as ERROR."""
    session = _make_session()
    lines = [json.dumps({"type": "result", "status": "success"}).encode() + b"\n"]
    proc = _make_proc(
        lines=lines,
        returncode=1,
        stderr=b"Error: line 1\nError: line 2\nError: line 3\n",
    )
    await session._read_loop(proc)

    events = _drain(session)
    error_events = [e for e in events if e.type == EventType.ERROR]
    assert len(error_events) == 1
    err_str = str(error_events[0].error)
    assert "Error: line 1" in err_str
    assert "Error: line 2" in err_str
    assert "Error: line 3" in err_str


async def test_stream_stdout_handles_line_too_long() -> None:
    """Regression: ValueError from LimitOverrunError in StreamReader should be caught.

    When a JSONL line exceeds the StreamReader limit, readline() raises
    LimitOverrunError which is re-raised as ValueError. Without the catch,
    this crashes the _read_loop and the whole session hangs until timeout.
    """
    session = _make_session()

    class _OverrunStream:
        """Simulates a StreamReader that raises ValueError on iteration."""

        def __aiter__(self) -> Self:
            return self

        async def __anext__(self) -> bytes:
            raise ValueError("Separator is not found, and chunk exceed the limit")

    await session._stream_stdout(_OverrunStream())
    # Should not raise — the ValueError is caught and logged


async def test_read_loop_with_limit_overrun() -> None:
    """Full _read_loop should survive a LimitOverrunError from stdout."""
    session = _make_session()

    # Build a proc whose stdout immediately raises ValueError
    class _OverrunStream:
        def __aiter__(self) -> Self:
            return self

        async def __anext__(self) -> bytes:
            raise ValueError("Separator is not found, and chunk exceed the limit")

    proc = AsyncMock()
    proc.stdout = _OverrunStream()
    proc.stderr = _AsyncBytesStream([])
    proc.wait = AsyncMock(return_value=0)
    proc.returncode = 0

    await session._read_loop(proc)

    # _read_loop should complete without hanging or crashing
    events = _drain(session)
    # No events produced (stdout failed), but no crash either
    assert all(e.type != EventType.ERROR for e in events)
