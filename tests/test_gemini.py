from unittest.mock import AsyncMock, patch

import pytest

from tg_gemini.config import GeminiConfig
from tg_gemini.events import ErrorEvent, InitEvent, MessageEvent
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
