import pytest

from tg_gemini.events import (
    ErrorEvent,
    InitEvent,
    MessageEvent,
    ResultEvent,
    ToolResultEvent,
    ToolUseEvent,
    parse_event,
)


def test_parse_init() -> None:
    data = {
        "type": "init",
        "timestamp": "2026-03-15T10:00:00Z",
        "session_id": "abc",
        "model": "gemini-pro",
    }
    event = parse_event(data)
    assert isinstance(event, InitEvent)
    assert event.session_id == "abc"
    assert event.model == "gemini-pro"


def test_parse_message() -> None:
    data = {
        "type": "message",
        "timestamp": "2026-03-15T10:00:00Z",
        "role": "assistant",
        "content": "hello",
    }
    event = parse_event(data)
    assert isinstance(event, MessageEvent)
    assert event.role == "assistant"
    assert event.content == "hello"


def test_parse_tool_use() -> None:
    data = {
        "type": "tool_use",
        "timestamp": "2026-03-15T10:00:00Z",
        "tool_name": "bash",
        "tool_id": "123",
        "parameters": {"command": "ls"},
    }
    event = parse_event(data)
    assert isinstance(event, ToolUseEvent)
    assert event.tool_name == "bash"
    assert event.parameters["command"] == "ls"


def test_parse_tool_result() -> None:
    data = {
        "type": "tool_result",
        "timestamp": "2026-03-15T10:00:00Z",
        "tool_id": "123",
        "status": "success",
        "output": "file.txt",
    }
    event = parse_event(data)
    assert isinstance(event, ToolResultEvent)
    assert event.status == "success"
    assert event.output == "file.txt"


def test_parse_error() -> None:
    data = {
        "type": "error",
        "timestamp": "2026-03-15T10:00:00Z",
        "severity": "error",
        "message": "failed",
    }
    event = parse_event(data)
    assert isinstance(event, ErrorEvent)
    assert event.severity == "error"
    assert event.message == "failed"


def test_parse_result() -> None:
    expected_tokens = 10
    data = {
        "type": "result",
        "timestamp": "2026-03-15T10:00:00Z",
        "status": "success",
        "stats": {
            "total_tokens": expected_tokens,
            "input_tokens": 5,
            "output_tokens": 5,
            "cached": 0,
            "input": 5,
            "duration_ms": 100,
            "tool_calls": 0,
            "models": {
                "gemini-pro": {
                    "total_tokens": expected_tokens,
                    "input_tokens": 5,
                    "output_tokens": 5,
                    "cached": 0,
                    "input": 5,
                }
            },
        },
    }
    event = parse_event(data)
    assert isinstance(event, ResultEvent)
    assert event.status == "success"
    assert event.stats
    assert event.stats.total_tokens == expected_tokens


def test_parse_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown event type"):
        parse_event({"type": "ghost"})
