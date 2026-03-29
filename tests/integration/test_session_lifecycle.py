"""Integration tests for session lifecycle flows.

These tests simulate real user interaction flows end-to-end,
covering the entire path from bot command to agent invocation.
Tests are written against the committed (HEAD) version of bot.py.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Message, User

from tg_gemini.bot import SessionManager, _process_stream, cmd_delete, cmd_list, cmd_name, cmd_new, cmd_resume
from tg_gemini.events import InitEvent
from tg_gemini.gemini import SessionInfo
from tests.integration.conftest import make_message_event, make_result


class TestNewSessionFlow:
    """User starts a new conversation (no session_id on first message)."""

    @pytest.mark.asyncio
    async def test_first_message_no_session_id(self) -> None:
        """The very first message invokes gemini WITHOUT -r flag."""
        sessions = SessionManager()
        agent = MagicMock()
        captured: list[Any] = []

        async def capture_stream(prompt: str, session_id: str | None, model: str | None) -> Any:
            captured.append({"prompt": prompt, "session_id": session_id, "model": model})
            yield make_message_event("Hello!", delta=False)
            yield make_result()

        agent.run_stream = capture_stream

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "Hello gemini"
        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()
        reply.delete = AsyncMock()
        msg.answer = AsyncMock(return_value=reply)

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(msg, sessions.get(1), agent)

        assert len(captured) == 1
        assert captured[0]["session_id"] is None, "First message must NOT pass session_id"

    @pytest.mark.asyncio
    async def test_init_event_captures_session_id(self) -> None:
        """InitEvent.session_id from gemini is stored in UserSession."""
        sessions = SessionManager()
        agent = MagicMock()

        async def stream(*_: Any) -> Any:
            yield InitEvent(session_id="session-abc-123", model="flash")
            yield make_message_event("Hi!", delta=False)
            yield make_result()

        agent.run_stream = stream

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "hello"
        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()
        msg.answer = AsyncMock(return_value=reply)

        session = sessions.get(1)
        assert session.session_id is None

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(msg, session, agent)

        assert session.session_id == "session-abc-123"

    @pytest.mark.asyncio
    async def test_second_message_uses_session_id(self) -> None:
        """After init, subsequent messages pass the captured session_id."""
        sessions = SessionManager()
        agent = MagicMock()
        captured_session_ids: list[str | None] = []

        async def capture(prompt: str, session_id: str | None, model: str | None) -> Any:
            captured_session_ids.append(session_id)
            if session_id is None:
                yield InitEvent(session_id="sess-xyz", model="flash")
                yield make_message_event("R1", delta=False)
                yield make_result()
            else:
                yield make_message_event("R2", delta=False)
                yield make_result()

        agent.run_stream = capture

        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()

        def make_msg(text: str) -> MagicMock:
            m = MagicMock(spec=Message)
            m.from_user = User(id=1, is_bot=False, first_name="Test")
            m.bot = MagicMock()
            m.chat = Chat(id=1, type="private")
            m.text = text
            m.answer = AsyncMock(return_value=reply)
            return m

        session = sessions.get(1)
        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(make_msg("first"), session, agent)
            await _process_stream(make_msg("second"), session, agent)

        assert captured_session_ids == [None, "sess-xyz"], "Second message must pass captured session_id"


class TestNewCommandFlow:
    """/new clears session_id so next message starts fresh."""

    @pytest.mark.asyncio
    async def test_new_clears_session_id(self) -> None:
        """After /new, session_id is reset to None."""
        sessions = SessionManager()
        sessions.get(1).session_id = "old-session"

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.answer = AsyncMock()
        await cmd_new(msg, MagicMock(args=None), sessions)

        assert sessions.get(1).session_id is None

    @pytest.mark.asyncio
    async def test_new_with_name_pending(self) -> None:
        """/new with a name stores it in pending_name."""
        sessions = SessionManager()
        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.answer = AsyncMock()

        command = MagicMock()
        command.args = "My Project"
        await cmd_new(msg, command, sessions)

        assert sessions.get(1).pending_name == "My Project"
        assert "My Project" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_new_then_send_starts_fresh(self) -> None:
        """After /new, a message should invoke gemini without -r."""
        sessions = SessionManager()
        captured: list[str | None] = []
        agent = MagicMock()

        async def capture(prompt: str, session_id: str | None, model: str | None) -> Any:
            captured.append(session_id)
            yield InitEvent(session_id="new-session", model="flash")
            yield make_message_event("ok", delta=False)
            yield make_result()

        agent.run_stream = capture

        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "new topic"
        msg.answer = AsyncMock(return_value=reply)

        # /new clears session_id
        await cmd_new(msg, MagicMock(args=None), sessions)
        assert sessions.get(1).session_id is None

        # Then send message
        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(msg, sessions.get(1), agent)

        assert captured == [None]


class TestResumeFlow:
    """/resume sets session_id for subsequent messages."""

    @pytest.mark.asyncio
    async def test_resume_with_id(self) -> None:
        """/resume <id> passes that session_id to gemini."""
        sessions = SessionManager()
        sessions.get(1).last_sessions = [SessionInfo(1, "Old chat", "1 day ago", "target-id")]
        captured: list[str | None] = []
        agent = MagicMock()

        async def capture(prompt: str, session_id: str | None, model: str | None) -> Any:
            captured.append(session_id)
            yield make_message_event("ok", delta=False)
            yield make_result()

        agent.run_stream = capture

        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "continue"
        msg.answer = AsyncMock(return_value=reply)

        command = MagicMock()
        command.args = "target-id"
        await cmd_resume(msg, command, sessions)

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(msg, sessions.get(1), agent)

        assert captured == ["target-id"]

    @pytest.mark.asyncio
    async def test_resume_with_index_resolves(self) -> None:
        """/resume 1 resolves index 1 to the correct session_id."""
        sessions = SessionManager()
        sessions.get(1).last_sessions = [
            SessionInfo(1, "Chat A", "1d", "id-a"),
            SessionInfo(2, "Chat B", "2d", "id-b"),
        ]
        captured: list[str | None] = []
        agent = MagicMock()

        async def capture(prompt: str, session_id: str | None, model: str | None) -> Any:
            captured.append(session_id)
            yield make_message_event("ok", delta=False)
            yield make_result()

        agent.run_stream = capture

        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "resume"
        msg.answer = AsyncMock(return_value=reply)

        command = MagicMock()
        command.args = "2"  # Index 2 → "id-b"
        await cmd_resume(msg, command, sessions)

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(msg, sessions.get(1), agent)

        assert captured == ["id-b"]

    @pytest.mark.asyncio
    async def test_resume_no_args_sets_latest(self) -> None:
        """/resume with no args sets session_id to 'latest'."""
        sessions = SessionManager()
        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.answer = AsyncMock()

        await cmd_resume(msg, MagicMock(args=None), sessions)
        assert sessions.get(1).session_id == "latest"


class TestNameFlow:
    """Pending names are applied when the init event arrives."""

    @pytest.mark.asyncio
    async def test_pending_name_applied_on_init(self) -> None:
        """A pending name from /new is stored under the new session_id."""
        sessions = SessionManager()
        sessions.get(1).session_id = "old"
        sessions.get(1).pending_name = "My Session"
        captured: list[str | None] = []
        agent = MagicMock()

        async def capture(prompt: str, session_id: str | None, model: str | None) -> Any:
            captured.append(session_id)
            yield InitEvent(session_id="new-session", model="flash")
            yield make_message_event("hello", delta=False)
            yield make_result()

        agent.run_stream = capture

        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "hello"
        msg.answer = AsyncMock(return_value=reply)

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(msg, sessions.get(1), agent)

        # pending_name consumed
        assert sessions.get(1).pending_name is None
        # name stored under new session_id
        assert sessions.get(1).custom_names.get("new-session") == "My Session"


class TestDeleteFlow:
    """/delete removes sessions and clears active session if needed."""

    @pytest.mark.asyncio
    async def test_delete_active_clears_session_id(self) -> None:
        """Deleting the active session resets session_id to None."""
        sessions = SessionManager()
        sessions.get(1).session_id = "to-delete"
        sessions.get(1).last_sessions = [SessionInfo(1, "T", "t", "to-delete")]
        sessions.get(1).custom_names = {"to-delete": "Name"}

        agent = MagicMock()
        agent.delete_session = AsyncMock(return_value=True)

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.answer = AsyncMock()

        command = MagicMock()
        command.args = "to-delete"
        await cmd_delete(msg, command, sessions, agent)

        assert sessions.get(1).session_id is None
        assert "to-delete" not in sessions.get(1).custom_names

    @pytest.mark.asyncio
    async def test_delete_inactive_preserves_active_session(self) -> None:
        """Deleting a different session does not affect the active one."""
        sessions = SessionManager()
        sessions.get(1).session_id = "active-session"
        sessions.get(1).last_sessions = [
            SessionInfo(1, "Active", "t", "active-session"),
            SessionInfo(2, "Old", "t", "other-session"),
        ]

        agent = MagicMock()
        agent.delete_session = AsyncMock(return_value=True)

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.answer = AsyncMock()

        command = MagicMock()
        command.args = "other-session"
        await cmd_delete(msg, command, sessions, agent)

        assert sessions.get(1).session_id == "active-session"


class TestModelOverride:
    """session.model overrides the config default and is passed to gemini."""

    @pytest.mark.asyncio
    async def test_session_model_passed_to_agent(self) -> None:
        """When session.model is set, it is forwarded to run_stream."""
        sessions = SessionManager()
        sessions.get(1).model = "pro"
        captured: list[Any] = []
        agent = MagicMock()

        async def capture(prompt: str, session_id: str | None, model: str | None) -> Any:
            captured.append(model)
            yield make_message_event("hi", delta=False)
            yield make_result()

        agent.run_stream = capture

        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=1, is_bot=False, first_name="Test")
        msg.bot = MagicMock()
        msg.chat = Chat(id=1, type="private")
        msg.text = "hello"
        msg.answer = AsyncMock(return_value=reply)

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await _process_stream(msg, sessions.get(1), agent)

        assert captured == ["pro"]


class TestConcurrency:
    """Concurrent messages from the same user are serialized by session lock."""

    @pytest.mark.asyncio
    async def test_same_user_serialized_by_lock(self) -> None:
        """Two messages from the same user are processed sequentially."""
        import asyncio

        sessions = SessionManager()
        order: list[str] = []
        agent = MagicMock()

        async def slow_stream(prompt: str, *_: Any) -> Any:
            order.append(f"start:{prompt}")
            yield make_message_event("ok", delta=False)
            yield make_result()
            order.append(f"end:{prompt}")

        agent.run_stream = slow_stream

        reply = MagicMock(spec=Message)
        reply.answer = AsyncMock()
        reply.edit_text = AsyncMock()

        def make_msg(text: str) -> MagicMock:
            m = MagicMock(spec=Message)
            m.from_user = User(id=1, is_bot=False, first_name="Test")
            m.bot = MagicMock()
            m.chat = Chat(id=1, type="private")
            m.text = text
            m.answer = AsyncMock(return_value=reply)
            return m

        with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()):
            await asyncio.gather(
                _process_stream(make_msg("msg1"), sessions.get(1), agent),
                _process_stream(make_msg("msg2"), sessions.get(1), agent),
            )

        # Both streams start before any end (serialized by lock)
        starts = [o for o in order if o.startswith("start")]
        ends = [o for o in order if o.startswith("end")]
        assert starts == ["start:msg1", "start:msg2"]
        assert ends == ["end:msg1", "end:msg2"]


import asyncio
