"""Tests for events.py based on real gemini-cli stream-json output.

References:
- Event schemas: packages/core/src/output/types.ts
- JSONL formatter: packages/core/src/output/stream-json-formatter.ts
- Integration snapshots: packages/cli/src/__snapshots__/nonInteractiveCli.test.ts.snap
- CLI event emission: packages/cli/src/nonInteractiveCli.ts

Test data derived from actual JSONL output captured in snapshot tests.
"""

import pytest

from tg_gemini.events import (
    ErrorEvent,
    EventType,
    InitEvent,
    MessageEvent,
    ModelStats,
    ResultEvent,
    StreamStats,
    ToolResultEvent,
    ToolUseEvent,
    parse_event,
)


class TestParseInitEvent:
    """Init event tests based on real gemini-cli output."""

    def test_parse_init_minimal(self) -> None:
        data = {
            "type": "init",
            "timestamp": "2026-03-15T10:00:00Z",
            "session_id": "abc123",
            "model": "gemini-2.5-flash",
        }
        event = parse_event(data)
        assert isinstance(event, InitEvent)
        assert event.session_id == "abc123"
        assert event.model == "gemini-2.5-flash"
        assert event.type_ == EventType.INIT

    def test_parse_init_with_long_session_id(self) -> None:
        data = {
            "type": "init",
            "timestamp": "2026-03-15T10:00:00Z",
            "session_id": "01j9x8k4m2n3p5q6r7s8t9u0v",
            "model": "gemini-pro",
        }
        event = parse_event(data)
        assert isinstance(event, InitEvent)
        assert len(event.session_id) > 20


class TestParseMessageEvent:
    """Message event tests covering delta streaming and roles."""

    def test_parse_message_user_role(self) -> None:
        data = {
            "type": "message",
            "timestamp": "2026-03-15T10:00:00Z",
            "role": "user",
            "content": "Hello, Gemini!",
        }
        event = parse_event(data)
        assert isinstance(event, MessageEvent)
        assert event.role == "user"
        assert event.content == "Hello, Gemini!"
        assert event.delta is None

    def test_parse_message_assistant_complete(self) -> None:
        data = {
            "type": "message",
            "timestamp": "2026-03-15T10:00:00Z",
            "role": "assistant",
            "content": "Here is a comprehensive answer.",
        }
        event = parse_event(data)
        assert isinstance(event, MessageEvent)
        assert event.role == "assistant"
        assert event.delta is None

    def test_parse_message_assistant_delta_streaming(self) -> None:
        """Delta=true indicates a streaming chunk from the CLI."""
        data = {
            "type": "message",
            "timestamp": "2026-03-15T10:00:00Z",
            "role": "assistant",
            "content": "Think",
            "delta": True,
        }
        event = parse_event(data)
        assert isinstance(event, MessageEvent)
        assert event.delta is True
        assert event.content == "Think"

    def test_parse_message_delta_false(self) -> None:
        data = {
            "type": "message",
            "timestamp": "2026-03-15T10:00:00Z",
            "role": "assistant",
            "content": "Final response",
            "delta": False,
        }
        event = parse_event(data)
        assert isinstance(event, MessageEvent)
        assert event.delta is False

    def test_parse_message_with_special_chars(self) -> None:
        """Content may include markdown, code blocks, etc."""
        data = {
            "type": "message",
            "timestamp": "2026-03-15T10:00:00Z",
            "role": "assistant",
            "content": "```python\nprint('hello')\n```\n**Bold** and *italic*",
        }
        event = parse_event(data)
        assert isinstance(event, MessageEvent)
        assert "```python" in event.content
        assert "**Bold**" in event.content

    def test_parse_message_unicode_content(self) -> None:
        data = {
            "type": "message",
            "timestamp": "2026-03-15T10:00:00Z",
            "role": "user",
            "content": "你好世界 🌍 αβγδ",
        }
        event = parse_event(data)
        assert isinstance(event, MessageEvent)
        assert "你好世界" in event.content
        assert "🌍" in event.content

    def test_parse_message_empty_content(self) -> None:
        """Empty content chunks can occur during streaming."""
        data = {
            "type": "message",
            "timestamp": "2026-03-15T10:00:00Z",
            "role": "assistant",
            "content": "",
        }
        event = parse_event(data)
        assert isinstance(event, MessageEvent)
        assert event.content == ""


class TestParseToolUseEvent:
    """Tool use event tests with real tool names from gemini-cli."""

    def test_parse_tool_use_bash(self) -> None:
        data = {
            "type": "tool_use",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_name": "bash",
            "tool_id": "tool-abc123",
            "parameters": {"command": "ls -la /home"},
        }
        event = parse_event(data)
        assert isinstance(event, ToolUseEvent)
        assert event.tool_name == "bash"
        assert event.tool_id == "tool-abc123"
        assert event.parameters["command"] == "ls -la /home"

    def test_parse_tool_use_read_file(self) -> None:
        data = {
            "type": "tool_use",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_name": "read_file",
            "tool_id": "tool-def456",
            "parameters": {"path": "/etc/config.toml", "limit": 100},
        }
        event = parse_event(data)
        assert isinstance(event, ToolUseEvent)
        assert event.tool_name == "read_file"
        assert event.parameters["path"] == "/etc/config.toml"

    def test_parse_tool_use_mcp_server(self) -> None:
        """MCP tools have namespaced format: mcp_toolName."""
        data = {
            "type": "tool_use",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_name": "mcp_filesystem_read_file",
            "tool_id": "tool-mcp-001",
            "parameters": {"path": "/data/input.txt"},
        }
        event = parse_event(data)
        assert isinstance(event, ToolUseEvent)
        assert event.tool_name == "mcp_filesystem_read_file"

    def test_parse_tool_use_write_file(self) -> None:
        data = {
            "type": "tool_use",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_name": "write_file",
            "tool_id": "tool-write-789",
            "parameters": {
                "path": "/tmp/output.json",
                "content": '{"key": "value"}',
            },
        }
        event = parse_event(data)
        assert isinstance(event, ToolUseEvent)
        assert event.parameters["content"] == '{"key": "value"}'

    def test_parse_tool_use_no_parameters(self) -> None:
        """Some tools may be called with empty parameters."""
        data = {
            "type": "tool_use",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_name": "list_directory",
            "tool_id": "tool-list-001",
            "parameters": {},
        }
        event = parse_event(data)
        assert isinstance(event, ToolUseEvent)
        assert event.parameters == {}

    def test_parse_tool_use_complex_parameters(self) -> None:
        """Tools may have complex nested parameters."""
        data = {
            "type": "tool_use",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_name": "multi_tool",
            "tool_id": "tool-complex",
            "parameters": {
                "nested": {"deep": {"value": 42}},
                "list": [1, 2, 3],
                "flag": True,
            },
        }
        event = parse_event(data)
        assert isinstance(event, ToolUseEvent)
        assert event.parameters["nested"]["deep"]["value"] == 42
        assert event.parameters["list"] == [1, 2, 3]
        assert event.parameters["flag"] is True


class TestParseToolResultEvent:
    """Tool result event tests covering success and error cases."""

    def test_parse_tool_result_success(self) -> None:
        data = {
            "type": "tool_result",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_id": "tool-abc123",
            "status": "success",
            "output": "file1.txt\nfile2.txt\nfile3.txt",
        }
        event = parse_event(data)
        assert isinstance(event, ToolResultEvent)
        assert event.tool_id == "tool-abc123"
        assert event.status == "success"
        assert event.output == "file1.txt\nfile2.txt\nfile3.txt"
        assert event.error is None

    def test_parse_tool_result_success_no_output(self) -> None:
        """Success may have no output (e.g., write_file completing)."""
        data = {
            "type": "tool_result",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_id": "tool-write",
            "status": "success",
        }
        event = parse_event(data)
        assert isinstance(event, ToolResultEvent)
        assert event.status == "success"
        assert event.output is None

    def test_parse_tool_result_error(self) -> None:
        """Error status includes error object with type and message."""
        data = {
            "type": "tool_result",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_id": "tool-err-001",
            "status": "error",
            "error": {"type": "FileNotFoundError", "message": "No such file: /missing"},
        }
        event = parse_event(data)
        assert isinstance(event, ToolResultEvent)
        assert event.status == "error"
        assert event.error is not None
        assert event.error.message == "No such file: /missing"

    def test_parse_tool_result_error_with_output(self) -> None:
        """Error may still include partial output."""
        data = {
            "type": "tool_result",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_id": "tool-partial",
            "status": "error",
            "output": "Partial data read before error",
            "error": {"type": "TimeoutError", "message": "Operation timed out"},
        }
        event = parse_event(data)
        assert isinstance(event, ToolResultEvent)
        assert event.status == "error"
        assert event.output == "Partial data read before error"
        assert "timed out" in event.error.message.lower()

    def test_parse_tool_result_json_output(self) -> None:
        """Tool output may be JSON string."""
        data = {
            "type": "tool_result",
            "timestamp": "2026-03-15T10:00:00Z",
            "tool_id": "tool-json",
            "status": "success",
            "output": '{"name": "config", "version": 1, "items": []}',
        }
        event = parse_event(data)
        assert isinstance(event, ToolResultEvent)
        assert '"name": "config"' in event.output


class TestParseErrorEvent:
    """Error event tests for system warnings and errors."""

    def test_parse_error_warning_severity(self) -> None:
        """Warning severity for non-fatal issues like loop detection."""
        data = {
            "type": "error",
            "timestamp": "2026-03-15T10:00:00Z",
            "severity": "warning",
            "message": "Loop detected, stopping execution",
        }
        event = parse_event(data)
        assert isinstance(event, ErrorEvent)
        assert event.severity == "warning"
        assert "Loop detected" in event.message

    def test_parse_error_error_severity(self) -> None:
        """Error severity for fatal issues."""
        data = {
            "type": "error",
            "timestamp": "2026-03-15T10:00:00Z",
            "severity": "error",
            "message": "Maximum session turns exceeded",
        }
        event = parse_event(data)
        assert isinstance(event, ErrorEvent)
        assert event.severity == "error"

    def test_parse_error_empty_message(self) -> None:
        data = {
            "type": "error",
            "timestamp": "2026-03-15T10:00:00Z",
            "severity": "warning",
            "message": "",
        }
        event = parse_event(data)
        assert isinstance(event, ErrorEvent)
        assert event.message == ""


class TestParseResultEvent:
    """Result event tests with comprehensive stats from real CLI output."""

    def test_parse_result_success_with_stats(self) -> None:
        data = {
            "type": "result",
            "timestamp": "2026-03-15T10:00:00Z",
            "status": "success",
            "stats": {
                "total_tokens": 1500,
                "input_tokens": 800,
                "output_tokens": 700,
                "cached": 200,
                "input": 800,
                "duration_ms": 2500,
                "tool_calls": 3,
                "models": {
                    "gemini-2.5-flash": {
                        "total_tokens": 1500,
                        "input_tokens": 800,
                        "output_tokens": 700,
                        "cached": 200,
                        "input": 800,
                    }
                },
            },
        }
        event = parse_event(data)
        assert isinstance(event, ResultEvent)
        assert event.status == "success"
        assert event.stats is not None
        assert event.stats.total_tokens == 1500
        assert event.stats.input_tokens == 800
        assert event.stats.output_tokens == 700
        assert event.stats.cached == 200
        assert event.stats.duration_ms == 2500
        assert event.stats.tool_calls == 3

    def test_parse_result_success_no_stats(self) -> None:
        """Result may omit stats field."""
        data = {
            "type": "result",
            "timestamp": "2026-03-15T10:00:00Z",
            "status": "success",
        }
        event = parse_event(data)
        assert isinstance(event, ResultEvent)
        assert event.status == "success"
        assert event.stats is None

    def test_parse_result_error_with_stats(self) -> None:
        """Result can have error status with stats (partial success)."""
        data = {
            "type": "result",
            "timestamp": "2026-03-15T10:00:00Z",
            "status": "error",
            "error": {"type": "SessionError", "message": "Turn limit reached"},
            "stats": {
                "total_tokens": 500,
                "input_tokens": 400,
                "output_tokens": 100,
                "cached": 0,
                "input": 400,
                "duration_ms": 1000,
                "tool_calls": 1,
                "models": {},
            },
        }
        event = parse_event(data)
        assert isinstance(event, ResultEvent)
        assert event.status == "error"
        assert event.error is not None
        assert "Turn limit" in event.error["message"]

    def test_parse_result_error_no_stats(self) -> None:
        data = {
            "type": "result",
            "timestamp": "2026-03-15T10:00:00Z",
            "status": "error",
            "error": {"type": "ApiError", "message": "Invalid API key"},
        }
        event = parse_event(data)
        assert isinstance(event, ResultEvent)
        assert event.status == "error"
        assert event.stats is None

    def test_parse_result_multiple_models(self) -> None:
        """Result may include stats from multiple model providers."""
        data = {
            "type": "result",
            "timestamp": "2026-03-15T10:00:00Z",
            "status": "success",
            "stats": {
                "total_tokens": 3000,
                "input_tokens": 1500,
                "output_tokens": 1500,
                "cached": 500,
                "input": 1500,
                "duration_ms": 5000,
                "tool_calls": 5,
                "models": {
                    "gemini-2.5-flash": {
                        "total_tokens": 2000,
                        "input_tokens": 1000,
                        "output_tokens": 1000,
                        "cached": 500,
                        "input": 1000,
                    },
                    "claude-3-5-sonnet": {
                        "total_tokens": 1000,
                        "input_tokens": 500,
                        "output_tokens": 500,
                        "cached": 0,
                        "input": 500,
                    },
                },
            },
        }
        event = parse_event(data)
        assert isinstance(event, ResultEvent)
        assert event.stats is not None
        assert len(event.stats.models) == 2
        assert "gemini-2.5-flash" in event.stats.models
        assert "claude-3-5-sonnet" in event.stats.models

    def test_parse_result_zero_stats(self) -> None:
        """Stats may contain zero values for empty sessions."""
        data = {
            "type": "result",
            "timestamp": "2026-03-15T10:00:00Z",
            "status": "success",
            "stats": {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached": 0,
                "input": 0,
                "duration_ms": 0,
                "tool_calls": 0,
                "models": {},
            },
        }
        event = parse_event(data)
        assert isinstance(event, ResultEvent)
        assert event.stats.total_tokens == 0
        assert event.stats.duration_ms == 0


class TestParseUnknown:
    """Tests for unknown event handling."""

    def test_parse_unknown_event_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown event type"):
            parse_event({"type": "ghost_event"})

    def test_parse_unknown_event_type_none(self) -> None:
        with pytest.raises(ValueError, match="Unknown event type"):
            parse_event({"type": None})

    def test_parse_missing_type(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            parse_event({"session_id": "abc"})


class TestModelStats:
    """Tests for ModelStats nested model."""

    def test_model_stats_all_fields(self) -> None:
        stats = ModelStats(
            total_tokens=100,
            input_tokens=50,
            output_tokens=50,
            cached=10,
            _input=50,
        )
        assert stats.total_tokens == 100
        assert stats.input_tokens == 50
        assert stats.output_tokens == 50
        assert stats.cached == 10


class TestStreamStats:
    """Tests for StreamStats nested model."""

    def test_stream_stats_all_fields(self) -> None:
        stats = StreamStats(
            total_tokens=1000,
            input_tokens=500,
            output_tokens=500,
            cached=100,
            _input=500,
            duration_ms=3000,
            tool_calls=2,
            models={},
        )
        assert stats.total_tokens == 1000
        assert stats.duration_ms == 3000
        assert stats.tool_calls == 2


class TestRealWorldJsonlSequence:
    """Tests simulating a real JSONL stream from gemini-cli.

    Based on actual snapshot tests in:
    packages/cli/src/__snapshots__/nonInteractiveCli.test.ts.snap
    """

    def test_full_conversation_stream_sequence(self) -> None:
        """Simulates a full conversation with multiple events."""
        jsonl_lines = [
            {
                "type": "init",
                "timestamp": "2026-03-15T10:00:00Z",
                "session_id": "test-session-id",
                "model": "test-model",
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:01Z",
                "role": "user",
                "content": "Stream test",
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:02Z",
                "role": "assistant",
                "content": "Thinking...",
                "delta": True,
            },
            {
                "type": "tool_use",
                "timestamp": "2026-03-15T10:00:03Z",
                "tool_name": "testTool",
                "tool_id": "tool-1",
                "parameters": {"arg1": "value1"},
            },
            {
                "type": "tool_result",
                "timestamp": "2026-03-15T10:00:04Z",
                "tool_id": "tool-1",
                "status": "success",
                "output": "Tool executed successfully",
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:05Z",
                "role": "assistant",
                "content": "Final answer",
                "delta": True,
            },
            {
                "type": "result",
                "timestamp": "2026-03-15T10:00:06Z",
                "status": "success",
                "stats": {
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached": 0,
                    "input": 0,
                    "duration_ms": 100,
                    "tool_calls": 1,
                    "models": {},
                },
            },
        ]

        events = [parse_event(line) for line in jsonl_lines]

        assert len(events) == 7
        assert isinstance(events[0], InitEvent)
        assert isinstance(events[1], MessageEvent)
        assert events[1].role == "user"
        assert isinstance(events[2], MessageEvent)
        assert events[2].delta is True
        assert isinstance(events[3], ToolUseEvent)
        assert events[3].tool_name == "testTool"
        assert isinstance(events[4], ToolResultEvent)
        assert events[4].status == "success"
        assert isinstance(events[5], MessageEvent)
        assert isinstance(events[6], ResultEvent)

    def test_loop_detection_warning_sequence(self) -> None:
        """Simulates loop detection warning from real CLI."""
        jsonl_lines = [
            {
                "type": "init",
                "timestamp": "2026-03-15T10:00:00Z",
                "session_id": "loop-test",
                "model": "test-model",
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:01Z",
                "role": "user",
                "content": "Loop test",
            },
            {
                "type": "error",
                "timestamp": "2026-03-15T10:00:02Z",
                "severity": "warning",
                "message": "Loop detected, stopping execution",
            },
            {
                "type": "result",
                "timestamp": "2026-03-15T10:00:03Z",
                "status": "success",
                "stats": {
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached": 0,
                    "input": 0,
                    "duration_ms": 50,
                    "tool_calls": 0,
                    "models": {},
                },
            },
        ]

        events = [parse_event(line) for line in jsonl_lines]

        assert len(events) == 4
        assert isinstance(events[2], ErrorEvent)
        assert events[2].severity == "warning"
        assert "Loop detected" in events[2].message

    def test_max_turns_error_sequence(self) -> None:
        """Simulates max turns exceeded error."""
        jsonl_lines = [
            {
                "type": "init",
                "timestamp": "2026-03-15T10:00:00Z",
                "session_id": "max-turns-test",
                "model": "test-model",
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:01Z",
                "role": "user",
                "content": "Max turns test",
            },
            {
                "type": "error",
                "timestamp": "2026-03-15T10:00:02Z",
                "severity": "error",
                "message": "Maximum session turns exceeded",
            },
            {
                "type": "result",
                "timestamp": "2026-03-15T10:00:03Z",
                "status": "success",
                "stats": {
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached": 0,
                    "input": 0,
                    "duration_ms": 50,
                    "tool_calls": 0,
                    "models": {},
                },
            },
        ]

        events = [parse_event(line) for line in jsonl_lines]

        assert len(events) == 4
        assert isinstance(events[2], ErrorEvent)
        assert events[2].severity == "error"
        assert "Maximum" in events[2].message

    def test_multi_chunk_message_streaming(self) -> None:
        """Simulates a message being streamed in multiple delta chunks."""
        jsonl_lines = [
            {
                "type": "init",
                "timestamp": "2026-03-15T10:00:00Z",
                "session_id": "stream-test",
                "model": "test-model",
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:01Z",
                "role": "user",
                "content": "Explain something",
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:02Z",
                "role": "assistant",
                "content": "Here ",
                "delta": True,
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:03Z",
                "role": "assistant",
                "content": "is ",
                "delta": True,
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:04Z",
                "role": "assistant",
                "content": "my ",
                "delta": True,
            },
            {
                "type": "message",
                "timestamp": "2026-03-15T10:00:05Z",
                "role": "assistant",
                "content": "complete answer.",
                "delta": True,
            },
            {
                "type": "result",
                "timestamp": "2026-03-15T10:00:06Z",
                "status": "success",
                "stats": {
                    "total_tokens": 50,
                    "input_tokens": 10,
                    "output_tokens": 40,
                    "cached": 0,
                    "input": 10,
                    "duration_ms": 2000,
                    "tool_calls": 0,
                    "models": {},
                },
            },
        ]

        events = [parse_event(line) for line in jsonl_lines]

        assert len(events) == 7
        delta_events = [e for e in events if isinstance(e, MessageEvent) and e.delta]
        assert len(delta_events) == 4

        # Verify chunks accumulate in order
        assert delta_events[0].content == "Here "
        assert delta_events[1].content == "is "
        assert delta_events[2].content == "my "
        assert delta_events[3].content == "complete answer."
