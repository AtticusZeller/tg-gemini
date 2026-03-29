"""Integration tests for tool-use message ordering flows.

These tests verify that the UI correctly handles the ordering of
tool_use, tool_result, and final response messages.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Message, User

from tests.integration.conftest import (
    make_message_event,
    make_result,
    make_tool_result,
    make_tool_use,
)
from tg_gemini.bot import SessionManager, _handle_event, _process_stream
from tg_gemini.events import InitEvent
from tg_gemini.sessions import SessionStore


def _make_tool_msg() -> MagicMock:
    """Create a MagicMock for a tool message (the "sent message" mock)."""
    m = MagicMock(spec=Message)
    m.delete = AsyncMock()
    m.edit_text = AsyncMock()
    return m


def _make_reply_mock(tool_count: int) -> tuple[MagicMock, MagicMock]:
    """Create mocks for a tool-use test.

    Returns (msg, reply) where:
    - msg.answer is AsyncMock that returns reply (the "Thinking..." message)
    - reply.answer is AsyncMock that returns a fresh MagicMock on each call
      (simulates Telegram API returning a new Message object for each send_message call)
    """
    reply = MagicMock(spec=Message)
    reply.delete = AsyncMock()
    reply.edit_text = AsyncMock()
    reply.chat = MagicMock()
    reply.message_id = 1
    # reply.answer must be AsyncMock so "await reply.answer(...)" works
    reply.answer = AsyncMock(
        side_effect=[
            MagicMock(spec=Message, chat=MagicMock(), message_id=i + 1)
            for i in range(tool_count + 1)
        ]
    )

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1, is_bot=False, first_name="Test")
    msg.bot = MagicMock()
    msg.chat = Chat(id=1, type="private")
    msg.answer = AsyncMock(return_value=reply)
    return msg, reply


class TestToolMessageOrdering:
    """When Gemini uses tools, the final response appears AFTER tool messages."""

    @pytest.mark.asyncio
    async def test_tools_used_deletes_thinking_sends_new(self) -> None:
        """With tools: Thinking is deleted, final response sent as new message."""
        sessions = SessionManager(MagicMock(spec=SessionStore))
        agent = MagicMock()

        async def stream(
            prompt: str = "",
            session_id: str | None = None,
            model: str | None = None,
            **_: Any,
        ) -> Any:
            yield InitEvent(session_id="s1", model="flash")
            yield make_tool_use(tool_id="c1", tool_name="read_file")
            yield make_tool_result(tool_id="c1", status="success", output="content")
            yield make_message_event("Here is what I found.", delta=False)
            yield make_result()

        agent.run_stream = stream

        msg, reply = _make_reply_mock(tool_count=1)
        msg.text = "read the file"

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            s = sessions.get(1)
            await _process_stream(msg, s, agent, s.session_id, s.model, sessions)

        # Thinking deleted
        reply.delete.assert_called_once()
        # 1 tool message call via reply.answer
        assert reply.answer.call_count >= 1

    @pytest.mark.asyncio
    async def test_no_tools_edits_in_place(self) -> None:
        """Without tools: Thinking is edited in-place, no extra messages sent."""
        sessions = SessionManager(MagicMock(spec=SessionStore))
        agent = MagicMock()

        async def stream(
            prompt: str = "",
            session_id: str | None = None,
            model: str | None = None,
            **_: Any,
        ) -> Any:
            yield InitEvent(session_id="s1", model="flash")
            yield make_message_event("Hello!", delta=False)
            yield make_result()

        agent.run_stream = stream

        reply = MagicMock(spec=Message)
        reply.delete = AsyncMock()
        reply.edit_text = AsyncMock()
        reply.chat = MagicMock()
        reply.message_id = 1

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "hello"
        msg.answer = AsyncMock(return_value=reply)

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            s = sessions.get(1)
            await _process_stream(msg, s, agent, s.session_id, s.model, sessions)

        reply.delete.assert_not_called()
        reply.edit_text.assert_called()
        assert msg.answer.call_count == 1

    @pytest.mark.asyncio
    async def test_tool_result_icon_swap(self) -> None:
        """Tool result swaps 🔧 to ✅ on success or ❌ on failure in tool_html."""
        from tg_gemini.bot import _StreamState

        session = SessionManager(MagicMock(spec=SessionStore)).get(1)
        state = _StreamState()

        # Create a tool message mock and store it
        tool_msg = _make_tool_msg()
        state.tool_messages["c1"] = tool_msg
        state.tool_html["c1"] = "🔧 <b>read_file</b>: <code>f.txt</code>"

        reply = MagicMock(spec=Message)

        # Success: icon should be swapped
        await _handle_event(
            make_tool_result(tool_id="c1", status="success", output="content"),
            session,
            state,
            reply,
        )
        tool_msg.edit_text.assert_called_once()
        edited = tool_msg.edit_text.call_args[0][0]
        assert "✅" in edited
        assert edited.startswith("✅")  # Icon is swapped at the start

        # Reset for failure test
        tool_msg.reset_mock()
        tool_msg.edit_text = AsyncMock()
        state.tool_html["c1"] = "🔧 <b>read_file</b>: <code>f.txt</code>"

        # Failure: icon should be swapped to ❌
        await _handle_event(
            make_tool_result(tool_id="c1", status="error", output=None),
            session,
            state,
            reply,
        )
        tool_msg.edit_text.assert_called_once()
        edited = tool_msg.edit_text.call_args[0][0]
        assert "❌" in edited


class TestMultipleToolCalls:
    """Multiple sequential tool calls are each displayed as separate messages."""

    @pytest.mark.asyncio
    async def test_multiple_tools_all_displayed(self) -> None:
        """Each tool call gets its own message via reply.answer."""
        sessions = SessionManager(MagicMock(spec=SessionStore))
        agent = MagicMock()

        async def stream(
            prompt: str = "",
            session_id: str | None = None,
            model: str | None = None,
            **_: Any,
        ) -> Any:
            yield InitEvent(session_id="s1", model="flash")
            yield make_tool_use(tool_id="c1", tool_name="read_file")
            yield make_tool_result(tool_id="c1", status="success", output="content1")
            yield make_tool_use(
                tool_id="c2", tool_name="grep_search", parameters={"pattern": "func"}
            )
            yield make_tool_result(tool_id="c2", status="success", output="found line")
            yield make_message_event("Done.", delta=False)
            yield make_result()

        agent.run_stream = stream

        msg, reply = _make_reply_mock(tool_count=2)
        msg.text = "analyze"

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            s = sessions.get(1)
            await _process_stream(msg, s, agent, s.session_id, s.model, sessions)

        # Thinking deleted after tools
        reply.delete.assert_called_once()
        # 2 tool message calls
        min_tool_calls = 2
        assert reply.answer.call_count >= min_tool_calls
