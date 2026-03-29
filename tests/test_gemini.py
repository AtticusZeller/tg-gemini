from unittest.mock import AsyncMock, patch

import pytest

from tg_gemini.config import GeminiConfig
from tg_gemini.events import (
    ErrorEvent,
    InitEvent,
    MessageEvent,
    ResultEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from tg_gemini.gemini import STREAM_BUFFER_LIMIT, GeminiAgent


@pytest.mark.asyncio
async def test_agent_run_stream_missing_cli() -> None:
    agent = GeminiAgent(GeminiConfig())
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        events = [e async for e in agent.run_stream("hello")]
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert "not found" in events[0].message


@pytest.mark.asyncio
async def test_agent_run_stream_success(tmp_path: pytest.TempPathFactory) -> None:
    config = GeminiConfig(model="pro", approval_mode="yolo", working_dir=str(tmp_path))
    agent = GeminiAgent(config)

    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "init", "session_id": "123", "model": "pro"}\n',
            b"invalid json\n",
            b'{"type": "message", "role": "assistant", "content": "hi"}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        events = [e async for e in agent.run_stream("hello", session_id="prev")]

        expected_count = 2
        assert len(events) == expected_count
        assert isinstance(events[0], InitEvent)
        assert isinstance(events[1], MessageEvent)
        mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_agent_run_stream_error_exit() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")
    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"critical failure")

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.stderr = mock_stderr
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        assert isinstance(events[-1], ErrorEvent)
        assert "exited with code 1" in events[-1].message


@pytest.mark.asyncio
async def test_agent_run_stream_large_buffer_limit() -> None:
    """Verify subprocess is created with a large buffer limit for big tool outputs."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        _ = [e async for e in agent.run_stream("hello")]
        call_kwargs = mock_exec.call_args
        assert call_kwargs.kwargs["limit"] == STREAM_BUFFER_LIMIT


@pytest.mark.asyncio
async def test_agent_run_stream_trailing_buffer() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "message", "role": "assistant", "content": "trailing"}',  # No newline
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        assert len(events) == 1
        assert events[0].content == "trailing"


@pytest.mark.asyncio
async def test_agent_run_stream_empty_trailing_buffer() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[b'{"type": "message", "role": "assistant", "content": "clean"}\n', b""]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        assert len(events) == 1
        assert events[0].content == "clean"


@pytest.mark.asyncio
async def test_agent_run_stream_multi_chunk() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "message", "role": "assistant", "content": "chunk1"}\n',
            b'{"type": "message", "role": "assistant", "content": "chunk2"}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        expected_count = 2
        assert len(events) == expected_count
        assert events[0].content == "chunk1"
        assert events[1].content == "chunk2"


@pytest.mark.asyncio
async def test_agent_run_stream_no_stdout_stderr() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_proc = AsyncMock()
    mock_proc.stdout = None
    mock_proc.stderr = None
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        assert isinstance(events[-1], ErrorEvent)
        assert "exited with code 1" in events[-1].message


def test_parse_line_invalid() -> None:
    agent = GeminiAgent(GeminiConfig())
    assert agent._parse_line("") is None  # noqa: SLF001
    assert agent._parse_line("invalid json") is None  # noqa: SLF001
    assert agent._parse_line('{"no": "type"}') is None  # noqa: SLF001
    assert agent._parse_line('{"type": "unknown"}') is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_agent_list_sessions_success() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (
        b"Available sessions for this project (2):\n"
        b"  1. Title A (10m ago) [id-a]\n"
        b"  2. Title B (1h ago) [id-b]\n",
        b"",
    )
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        sessions = await agent.list_sessions()
        expected_count = 2
        assert len(sessions) == expected_count
        assert sessions[0].index == 1
        assert sessions[0].title == "Title A"
        assert sessions[0].session_id == "id-a"


@pytest.mark.asyncio
async def test_agent_list_sessions_fail() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = (b"", b"error")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        sessions = await agent.list_sessions()
        assert sessions == []


@pytest.mark.asyncio
async def test_agent_list_sessions_not_found() -> None:
    agent = GeminiAgent(GeminiConfig())
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        sessions = await agent.list_sessions()
        assert sessions == []


@pytest.mark.asyncio
async def test_agent_delete_session_success() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        success = await agent.delete_session("id-a")
        assert success is True


@pytest.mark.asyncio
async def test_agent_delete_session_fail() -> None:
    agent = GeminiAgent(GeminiConfig())
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        success = await agent.delete_session("id-a")
        assert success is False


@pytest.mark.asyncio
async def test_agent_delete_session_not_found() -> None:
    agent = GeminiAgent(GeminiConfig())
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        success = await agent.delete_session("id-a")
        assert success is False


def test_build_args_basic() -> None:
    """Test _build_args generates correct command without session_id."""
    config = GeminiConfig(model="gemini-2", approval_mode="ask")
    agent = GeminiAgent(config)
    args = agent._build_args("hello world")  # noqa: SLF001
    assert args == [
        "gemini",
        "-p",
        "hello world",
        "--output-format",
        "stream-json",
        "-m",
        "gemini-2",
        "--approval-mode",
        "ask",
    ]


def test_build_args_with_session_id() -> None:
    """Test _build_args includes -r flag when session_id is provided."""
    config = GeminiConfig(model="gemini-2", approval_mode="ask")
    agent = GeminiAgent(config)
    args = agent._build_args("continue", session_id="abc-123")  # noqa: SLF001
    assert "-r" in args
    assert "abc-123" in args


def test_build_args_with_custom_model() -> None:
    """Test _build_args uses custom model override."""
    config = GeminiConfig(model="gemini-2", approval_mode="ask")
    agent = GeminiAgent(config)
    args = agent._build_args("hello", model="gemini-pro")  # noqa: SLF001
    assert args == [
        "gemini",
        "-p",
        "hello",
        "--output-format",
        "stream-json",
        "-m",
        "gemini-pro",
        "--approval-mode",
        "ask",
    ]


def test_build_args_with_custom_approval_mode() -> None:
    """Test _build_args uses config's approval_mode and custom model override."""
    config = GeminiConfig(model="gemini-2", approval_mode="ask")
    agent = GeminiAgent(config)
    args = agent._build_args("hello", model="flash")  # noqa: SLF001
    assert args == [
        "gemini",
        "-p",
        "hello",
        "--output-format",
        "stream-json",
        "-m",
        "flash",
        "--approval-mode",
        "ask",
    ]


@pytest.mark.asyncio
async def test_agent_run_stream_with_tool_use() -> None:
    """Test stream processing with tool_use events (reference: nonInteractiveCli.ts)."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "init", "session_id": "sess-1", "model": "pro"}\n',
            b'{"type": "message", "role": "assistant", "content": "Using tool"}\n',
            b'{"type": "tool_use", "tool_name": "testTool", "tool_id": "tool-1", "parameters": {"arg1": "value1"}}\n',
            b'{"type": "tool_result", "tool_id": "tool-1", "status": "success", "output": "Tool executed"}\n',
            b'{"type": "message", "role": "assistant", "content": "Done"}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        expected_count = 5
        assert len(events) == expected_count
        assert isinstance(events[0], InitEvent)
        assert isinstance(events[1], MessageEvent)
        assert isinstance(events[2], ToolUseEvent)
        assert events[2].tool_name == "testTool"
        assert events[2].tool_id == "tool-1"
        assert events[2].parameters == {"arg1": "value1"}
        assert isinstance(events[3], ToolResultEvent)
        assert events[3].tool_id == "tool-1"
        assert events[3].status == "success"
        assert events[3].output == "Tool executed"
        assert isinstance(events[4], MessageEvent)
        assert events[4].content == "Done"


@pytest.mark.asyncio
async def test_agent_run_stream_with_tool_error() -> None:
    """Test stream processing with tool_result error status."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "tool_use", "tool_name": "badTool", "tool_id": "tool-err", "parameters": {}}\n',
            b'{"type": "tool_result", "tool_id": "tool-err", "status": "error", "error": {"message": "Tool failed"}}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        expected_count = 2
        assert len(events) == expected_count
        assert isinstance(events[0], ToolUseEvent)
        assert isinstance(events[1], ToolResultEvent)
        assert events[1].status == "error"
        assert events[1].error is not None
        assert events[1].error.message == "Tool failed"


@pytest.mark.asyncio
async def test_agent_run_stream_with_result_event() -> None:
    """Test stream processing with result event containing stats."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "message", "role": "assistant", "content": "Done"}\n',
            b'{"type": "result", "status": "success", "stats": {"total_tokens": 100, "input_tokens": 50, "output_tokens": 50, "cached": 0, "_input": 0, "duration_ms": 1000, "tool_calls": 0, "models": {}}}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        expected_count = 2
        assert len(events) == expected_count
        assert isinstance(events[0], MessageEvent)
        assert isinstance(events[1], ResultEvent)
        assert events[1].status == "success"
        assert events[1].stats is not None
        expected_tokens = 100
        assert events[1].stats.total_tokens == expected_tokens


@pytest.mark.asyncio
async def test_agent_run_stream_with_warning_error() -> None:
    """Test stream processing with warning severity error events."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "error", "severity": "warning", "message": "Loop detected"}\n',
            b'{"type": "message", "role": "assistant", "content": "stopped"}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        expected_count = 2
        assert len(events) == expected_count
        assert isinstance(events[0], ErrorEvent)
        assert events[0].severity == "warning"
        assert events[0].message == "Loop detected"
        assert isinstance(events[1], MessageEvent)


@pytest.mark.asyncio
async def test_agent_run_stream_with_user_message() -> None:
    """Test stream processing includes user message events."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "message", "role": "user", "content": "my prompt"}\n',
            b'{"type": "message", "role": "assistant", "content": "response"}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("my prompt")]
        expected_count = 2
        assert len(events) == expected_count
        assert events[0].role == "user"
        assert events[0].content == "my prompt"
        assert events[1].role == "assistant"


@pytest.mark.asyncio
async def test_agent_run_stream_with_delta_messages() -> None:
    """Test stream processing with delta flag on assistant messages."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b'{"type": "message", "role": "assistant", "content": "first", "delta": true}\n',
            b'{"type": "message", "role": "assistant", "content": "second", "delta": true}\n',
            b'{"type": "message", "role": "assistant", "content": "final", "delta": false}\n',
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        expected_count = 3
        assert len(events) == expected_count
        assert events[0].delta is True
        assert events[1].delta is True
        assert events[2].delta is False


@pytest.mark.asyncio
async def test_agent_run_stream_with_working_dir() -> None:
    """Test subprocess is created with correct working directory."""
    config = GeminiConfig(model="pro", working_dir="/custom/path")
    agent = GeminiAgent(config)
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        _ = [e async for e in agent.run_stream("hello")]
        call_kwargs = mock_exec.call_args
        assert call_kwargs.kwargs["cwd"] == "/custom/path"


@pytest.mark.asyncio
async def test_agent_run_stream_session_resume() -> None:
    """Test session resume via -r flag in command args."""
    config = GeminiConfig(model="pro")
    agent = GeminiAgent(config)
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        _ = [e async for e in agent.run_stream("continue", session_id="prev-session")]
        args, kwargs = mock_exec.call_args
        assert "-r" in args
        assert "prev-session" in args


@pytest.mark.asyncio
async def test_agent_run_stream_all_invalid_json_skip() -> None:
    """Test stream skips all invalid JSON lines and only yields valid events."""
    agent = GeminiAgent(GeminiConfig())
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b"not json at all\n",
            b'{"type": "message", "role": "assistant", "content": "valid"}\n',
            b"also not json\n",
            b"",
        ]
    )

    mock_proc = AsyncMock()
    mock_proc.stdout = mock_stdout
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        events = [e async for e in agent.run_stream("hello")]
        assert len(events) == 1
        assert events[0].content == "valid"


def test_parse_line_tool_use() -> None:
    """Test _parse_line correctly parses tool_use events."""
    agent = GeminiAgent(GeminiConfig())
    line = '{"type": "tool_use", "tool_name": "readFile", "tool_id": "t1", "parameters": {"path": "/a"}}'
    event = agent._parse_line(line)  # noqa: SLF001
    assert event is not None
    assert isinstance(event, ToolUseEvent)
    assert event.tool_name == "readFile"
    assert event.tool_id == "t1"
    assert event.parameters == {"path": "/a"}


def test_parse_line_tool_result() -> None:
    """Test _parse_line correctly parses tool_result events."""
    agent = GeminiAgent(GeminiConfig())
    line = '{"type": "tool_result", "tool_id": "t1", "status": "success", "output": "file content"}'
    event = agent._parse_line(line)  # noqa: SLF001
    assert event is not None
    assert isinstance(event, ToolResultEvent)
    assert event.tool_id == "t1"
    assert event.status == "success"
    assert event.output == "file content"


def test_parse_line_result() -> None:
    """Test _parse_line correctly parses result events."""
    agent = GeminiAgent(GeminiConfig())
    line = '{"type": "result", "status": "success", "stats": {"total_tokens": 10, "input_tokens": 5, "output_tokens": 5, "cached": 0, "_input": 0, "duration_ms": 100, "tool_calls": 0, "models": {}}}'
    event = agent._parse_line(line)  # noqa: SLF001
    assert event is not None
    assert isinstance(event, ResultEvent)
    assert event.status == "success"
    assert event.stats is not None
    expected_tokens = 10
    assert event.stats.total_tokens == expected_tokens


def test_parse_line_error() -> None:
    """Test _parse_line correctly parses error events."""
    agent = GeminiAgent(GeminiConfig())
    line = '{"type": "error", "severity": "error", "message": "something failed"}'
    event = agent._parse_line(line)  # noqa: SLF001
    assert event is not None
    assert isinstance(event, ErrorEvent)
    assert event.severity == "error"
    assert event.message == "something failed"


def test_parse_line_message_with_delta() -> None:
    """Test _parse_line correctly parses message events with delta flag."""
    agent = GeminiAgent(GeminiConfig())
    line = '{"type": "message", "role": "assistant", "content": "chunk", "delta": true}'
    event = agent._parse_line(line)  # noqa: SLF001
    assert event is not None
    assert isinstance(event, MessageEvent)
    assert event.role == "assistant"
    assert event.content == "chunk"
    assert event.delta is True
