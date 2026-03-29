"""Tests for Session and SessionManager (v2: multi-session + history)."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tg_gemini.session import HistoryEntry, Session, SessionManager

# ── Session ────────────────────────────────────────────────────────────────


class TestSession:
    def test_session_creation(self) -> None:
        session = Session(id="test-id")
        assert session.id == "test-id"
        assert session.agent_session_id == ""
        assert session.user_key == ""
        assert session.name == ""
        assert session.history == []
        assert not session.busy
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)

    def test_session_with_agent_id(self) -> None:
        session = Session(id="test-id", agent_session_id="agent-123")
        assert session.agent_session_id == "agent-123"

    async def test_try_lock_not_busy(self) -> None:
        session = Session(id="test-id")
        result = await session.try_lock()
        assert result is True
        assert session.busy

    async def test_try_lock_when_busy(self) -> None:
        session = Session(id="test-id")
        await session.try_lock()
        result = await session.try_lock()
        assert result is False
        assert session.busy

    async def test_unlock_releases_lock(self) -> None:
        session = Session(id="test-id")
        await session.try_lock()
        assert session.busy
        await session.unlock()
        assert not session.busy

    async def test_unlock_updates_timestamp(self) -> None:
        session = Session(id="test-id")
        old_time = session.updated_at
        await session.try_lock()
        await asyncio.sleep(0.01)
        await session.unlock()
        assert session.updated_at > old_time

    async def test_lock_can_be_reacquired_after_unlock(self) -> None:
        session = Session(id="test-id")
        await session.try_lock()
        await session.unlock()
        result = await session.try_lock()
        assert result is True
        assert session.busy

    def test_busy_property(self) -> None:
        session = Session(id="test-id")
        assert not session.busy


# ── HistoryEntry + Session.add_history ────────────────────────────────────


class TestHistoryEntry:
    def test_creation(self) -> None:
        h = HistoryEntry(role="user", content="hello")
        assert h.role == "user"
        assert h.content == "hello"
        assert isinstance(h.timestamp, datetime)

    def test_timestamp_is_utc(self) -> None:
        h = HistoryEntry(role="assistant", content="hi")
        assert h.timestamp.tzinfo is not None


class TestAddHistory:
    def test_appends_entry(self) -> None:
        s = Session(id="x")
        s.add_history("user", "hello")
        assert len(s.history) == 1
        assert s.history[0].role == "user"
        assert s.history[0].content == "hello"

    def test_trims_oldest_on_overflow(self) -> None:
        s = Session(id="x")
        for i in range(5):
            s.add_history("user", str(i))
        s.add_history("user", "extra", max_entries=5)
        assert len(s.history) == 5
        assert s.history[0].content == "1"  # oldest "0" removed

    def test_max_entries_zero_no_trim(self) -> None:
        s = Session(id="x")
        for i in range(200):
            s.add_history("user", str(i), max_entries=0)
        assert len(s.history) == 200

    def test_multiple_roles(self) -> None:
        s = Session(id="x")
        s.add_history("user", "q")
        s.add_history("assistant", "a")
        assert s.history[0].role == "user"
        assert s.history[1].role == "assistant"


# ── Session.summary ────────────────────────────────────────────────────────


class TestSessionSummary:
    def test_name_takes_priority(self) -> None:
        s = Session(id="abc-123", name="My Project")
        s.add_history("user", "hello world this is a long message")
        assert s.summary == "My Project"

    def test_first_user_message_preview(self) -> None:
        s = Session(id="abc-12345678")
        s.add_history("assistant", "intro")
        s.add_history("user", "Short msg")
        assert s.summary == "Short msg"

    def test_long_first_user_message_truncated(self) -> None:
        s = Session(id="abc-123")
        s.add_history("user", "a" * 40)
        assert s.summary.endswith("…")
        assert len(s.summary) == 31  # 30 chars + ellipsis

    def test_fallback_truncated_id(self) -> None:
        s = Session(id="abcdef1234567890")
        assert s.summary == "abcdef12"

    def test_empty_session(self) -> None:
        s = Session(id="xyz-123")
        assert s.summary == "xyz-123"[:8]


# ── SessionManager v1 API (backward-compatible) ────────────────────────────


class TestSessionManagerV1API:
    def test_get_or_create_new_session(self) -> None:
        manager = SessionManager()
        session = manager.get_or_create("user1")
        assert isinstance(session, Session)
        assert session.id
        assert session.user_key == "user1"

    def test_get_or_create_returns_same_session(self) -> None:
        manager = SessionManager()
        session1 = manager.get_or_create("user1")
        session2 = manager.get_or_create("user1")
        assert session1.id == session2.id
        assert session1 is session2

    def test_get_or_create_different_users(self) -> None:
        manager = SessionManager()
        session1 = manager.get_or_create("user1")
        session2 = manager.get_or_create("user2")
        assert session1.id != session2.id

    def test_new_session_creates_fresh_session(self) -> None:
        manager = SessionManager()
        old_session = manager.get_or_create("user1")
        new_session = manager.new_session("user1")
        assert new_session.id != old_session.id

    def test_new_session_becomes_active(self) -> None:
        manager = SessionManager()
        manager.get_or_create("user1")
        new_session = manager.new_session("user1")
        retrieved = manager.get("user1")
        assert retrieved is new_session

    def test_new_session_with_name(self) -> None:
        manager = SessionManager()
        s = manager.new_session("user1", name="Sprint 1")
        assert s.name == "Sprint 1"

    def test_get_existing_session(self) -> None:
        manager = SessionManager()
        created = manager.get_or_create("user1")
        retrieved = manager.get("user1")
        assert retrieved is created

    def test_get_nonexistent_session(self) -> None:
        manager = SessionManager()
        result = manager.get("nonexistent")
        assert result is None

    def test_manager_without_store_path(self) -> None:
        manager = SessionManager()
        session = manager.get_or_create("user1")
        assert session.id


# ── SessionManager v2 API ─────────────────────────────────────────────────


class TestListSessions:
    def test_empty(self) -> None:
        manager = SessionManager()
        assert manager.list_sessions("user1") == []

    def test_single_session(self) -> None:
        manager = SessionManager()
        s = manager.get_or_create("user1")
        result = manager.list_sessions("user1")
        assert len(result) == 1
        assert result[0].id == s.id

    def test_multiple_sessions_sorted_by_updated_at_desc(self) -> None:
        manager = SessionManager()
        s1 = manager.new_session("u")
        s2 = manager.new_session("u")
        s3 = manager.new_session("u")
        # Tweak timestamps: s2 most recent
        s2.updated_at = datetime(2026, 3, 20, tzinfo=UTC)
        s1.updated_at = datetime(2026, 3, 18, tzinfo=UTC)
        s3.updated_at = datetime(2026, 3, 19, tzinfo=UTC)
        result = manager.list_sessions("u")
        assert result[0].id == s2.id
        assert result[1].id == s3.id
        assert result[2].id == s1.id


class TestSwitchSession:
    def test_switch_by_index(self) -> None:
        manager = SessionManager()
        s1 = manager.new_session("u")
        s2 = manager.new_session("u")
        # s2 is most recent → index 1, s1 → index 2
        s2.updated_at = datetime(2026, 3, 20, tzinfo=UTC)
        s1.updated_at = datetime(2026, 3, 18, tzinfo=UTC)
        result = manager.switch_session("u", "2")  # switch to index 2 (s1)
        assert result is not None
        assert result.id == s1.id
        assert manager.active_session_id("u") == s1.id

    def test_switch_by_id_prefix(self) -> None:
        manager = SessionManager()
        s = manager.new_session("u")
        manager.new_session("u")
        switched = manager.switch_session("u", s.id[:8])
        assert switched is not None
        assert switched.id == s.id

    def test_switch_by_name_substring(self) -> None:
        manager = SessionManager()
        s1 = manager.new_session("u", name="Alpha Project")
        manager.new_session("u", name="Beta Project")
        result = manager.switch_session("u", "alpha")
        assert result is not None
        assert result.id == s1.id

    def test_switch_invalid_target(self) -> None:
        manager = SessionManager()
        manager.new_session("u")
        result = manager.switch_session("u", "zzz-not-found")
        assert result is None

    def test_switch_out_of_range_index(self) -> None:
        manager = SessionManager()
        manager.new_session("u")
        result = manager.switch_session("u", "99")
        assert result is None

    def test_switch_empty_sessions(self) -> None:
        manager = SessionManager()
        result = manager.switch_session("u", "1")
        assert result is None


class TestDeleteSession:
    def test_delete_existing(self) -> None:
        manager = SessionManager()
        s = manager.get_or_create("u")
        result = manager.delete_session(s.id)
        assert result is True
        assert manager.find_session(s.id) is None

    def test_delete_nonexistent(self) -> None:
        manager = SessionManager()
        result = manager.delete_session("no-such-id")
        assert result is False

    def test_delete_active_promotes_next(self) -> None:
        manager = SessionManager()
        s1 = manager.new_session("u")
        s2 = manager.new_session("u")
        # s2 is active and more recent
        s2.updated_at = datetime(2026, 3, 20, tzinfo=UTC)
        s1.updated_at = datetime(2026, 3, 18, tzinfo=UTC)
        manager.delete_session(s2.id)
        assert manager.active_session_id("u") == s1.id

    def test_delete_last_clears_active(self) -> None:
        manager = SessionManager()
        s = manager.get_or_create("u")
        manager.delete_session(s.id)
        assert manager.active_session_id("u") == ""

    def test_delete_non_active_preserves_active(self) -> None:
        manager = SessionManager()
        s1 = manager.new_session("u")
        s2 = manager.new_session("u")  # s2 active
        manager.delete_session(s1.id)
        assert manager.active_session_id("u") == s2.id


class TestDeleteSessions:
    def test_delete_multiple(self) -> None:
        manager = SessionManager()
        s1 = manager.new_session("u")
        s2 = manager.new_session("u")
        count = manager.delete_sessions([s1.id, s2.id])
        assert count == 2

    def test_delete_partial(self) -> None:
        manager = SessionManager()
        s = manager.new_session("u")
        count = manager.delete_sessions([s.id, "nonexistent"])
        assert count == 1


class TestSetSessionName:
    def test_rename_success(self) -> None:
        manager = SessionManager()
        s = manager.get_or_create("u")
        result = manager.set_session_name(s.id, "New Name")
        assert result is True
        assert s.name == "New Name"

    def test_rename_nonexistent(self) -> None:
        manager = SessionManager()
        result = manager.set_session_name("no-id", "Name")
        assert result is False


class TestSessionCount:
    def test_zero_initially(self) -> None:
        manager = SessionManager()
        assert manager.session_count("u") == 0

    def test_increments_with_new_sessions(self) -> None:
        manager = SessionManager()
        manager.new_session("u")
        manager.new_session("u")
        assert manager.session_count("u") == 2

    def test_decrements_on_delete(self) -> None:
        manager = SessionManager()
        s = manager.new_session("u")
        manager.new_session("u")
        manager.delete_session(s.id)
        assert manager.session_count("u") == 1


# ── Persistence ────────────────────────────────────────────────────────────


class TestV2SaveLoad:
    def test_save_creates_v2_format(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        manager = SessionManager(store_path=store)
        s = manager.get_or_create("user1")
        s.add_history("user", "hello")
        manager._save()

        data = json.loads(store.read_text())
        assert data["version"] == 2
        assert "sessions" in data
        assert "active_sessions" in data
        assert "session_counter" in data

    def test_v2_round_trip(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        m1 = SessionManager(store_path=store)
        s = m1.new_session("user1", name="Proj A")
        s.agent_session_id = "agent-xyz"
        s.add_history("user", "first message")
        m1._save()

        m2 = SessionManager(store_path=store)
        loaded = m2.get("user1")
        assert loaded is not None
        assert loaded.id == s.id
        assert loaded.name == "Proj A"
        assert loaded.agent_session_id == "agent-xyz"
        assert len(loaded.history) == 1
        assert loaded.history[0].content == "first message"

    def test_v2_active_session_preserved(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        m1 = SessionManager(store_path=store)
        m1.new_session("u")
        s2 = m1.new_session("u")
        m1._save()

        m2 = SessionManager(store_path=store)
        assert m2.active_session_id("u") == s2.id

    def test_corrupt_file_silent(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        store.write_text("corrupted")
        manager = SessionManager(store_path=store)
        assert manager.get("any") is None

    def test_no_store_path_save_noop(self) -> None:
        manager = SessionManager()
        manager.get_or_create("user1")
        manager._save()  # should not raise

    def test_no_store_path_load_noop(self) -> None:
        manager = SessionManager()
        manager._load()  # should not raise


class TestV1Migration:
    def _make_v1_file(self, tmp_path: Path) -> tuple[Path, str, str]:
        """Create a v1-format sessions.json, return (path, user_key, session_id)."""
        store = tmp_path / "sessions.json"
        sid = "11111111-0000-0000-0000-000000000001"
        data = {
            "telegram:1:100": {
                "id": sid,
                "agent_session_id": "gemini-session-abc",
                "created_at": "2026-03-01T10:00:00+00:00",
                "updated_at": "2026-03-01T11:00:00+00:00",
            }
        }
        store.write_text(json.dumps(data))
        return store, "telegram:1:100", sid

    def test_v1_auto_migrates(self, tmp_path: Path) -> None:
        store, user_key, sid = self._make_v1_file(tmp_path)
        manager = SessionManager(store_path=store)
        session = manager.get(user_key)
        assert session is not None
        assert session.id == sid

    def test_v1_agent_session_preserved(self, tmp_path: Path) -> None:
        store, user_key, _ = self._make_v1_file(tmp_path)
        manager = SessionManager(store_path=store)
        session = manager.get(user_key)
        assert session is not None
        assert session.agent_session_id == "gemini-session-abc"

    def test_v1_migrated_saved_as_v2(self, tmp_path: Path) -> None:
        store, _, _ = self._make_v1_file(tmp_path)
        SessionManager(store_path=store)
        data = json.loads(store.read_text())
        assert data.get("version") == 2

    def test_v1_timestamps_preserved(self, tmp_path: Path) -> None:
        store, user_key, _ = self._make_v1_file(tmp_path)
        manager = SessionManager(store_path=store)
        session = manager.get(user_key)
        assert session is not None
        assert session.created_at.year == 2026

    def test_v1_invalid_entries_skipped(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        store.write_text(json.dumps({"bad-entry": "not a dict"}))
        manager = SessionManager(store_path=store)
        assert manager.get("bad-entry") is None

    def test_new_session_saves_v2(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        manager = SessionManager(store_path=store)
        manager.new_session("user1")
        data = json.loads(store.read_text())
        assert data["version"] == 2


# ── Concurrent locking ─────────────────────────────────────────────────────


class TestConcurrentLocking:
    async def test_concurrent_try_lock(self) -> None:
        session = Session(id="test-id")
        results = await asyncio.gather(
            session.try_lock(), session.try_lock(), session.try_lock()
        )
        assert sum(1 for r in results if r) == 1
        assert sum(1 for r in results if not r) == 2

    async def test_concurrent_lock_unlock(self) -> None:
        session = Session(id="test-id")
        lock_count = [0]

        async def locker() -> None:
            for _ in range(10):
                if await session.try_lock():
                    lock_count[0] += 1
                    await asyncio.sleep(0.001)
                    await session.unlock()

        await asyncio.gather(*[locker() for _ in range(5)])
        assert 1 <= lock_count[0] <= 50

    async def test_session_isolation(self) -> None:
        manager = SessionManager()
        session1 = manager.get_or_create("user1")
        session2 = manager.get_or_create("user2")
        assert await session1.try_lock()
        assert await session2.try_lock()
        await session1.unlock()
        await session2.unlock()

    async def test_manager_concurrent_access(self) -> None:
        manager = SessionManager()

        async def create_and_lock(user_key: str) -> bool:
            session = manager.get_or_create(user_key)
            return await session.try_lock()

        results = await asyncio.gather(
            create_and_lock("user1"), create_and_lock("user2"), create_and_lock("user3")
        )
        assert all(results)

    async def test_lock_released_after_exception(self) -> None:
        session = Session(id="test-id")
        await session.try_lock()
        try:
            msg = "test error"
            raise ValueError(msg)
        except ValueError:
            pass
        assert session.busy
        await session.unlock()
        assert not session.busy

    async def test_concurrent_locking_across_sessions(self) -> None:
        manager = SessionManager()
        sessions = [manager.new_session(f"user{i}") for i in range(5)]
        results = await asyncio.gather(*(s.try_lock() for s in sessions))
        assert all(results)


# ── Regression: old test_save_content adapted for v2 ─────────────────────


class TestSaveContentV2:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        manager = SessionManager(store_path=store)
        manager.get_or_create("user1")
        manager._save()
        assert store.exists()

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        store = tmp_path / "subdir" / "sessions.json"
        manager = SessionManager(store_path=store)
        manager.get_or_create("user1")
        manager._save()
        assert store.exists()

    def test_load_preserves_timestamps(self, tmp_path: Path) -> None:
        store = tmp_path / "sessions.json"
        m1 = SessionManager(store_path=store)
        session = m1.get_or_create("user1")
        orig_created = session.created_at
        orig_updated = session.updated_at
        m1._save()

        m2 = SessionManager(store_path=store)
        loaded = m2.get("user1")
        assert loaded is not None
        assert loaded.created_at == orig_created
        assert loaded.updated_at == orig_updated

    def test_missing_file_graceful(self, tmp_path: Path) -> None:
        store = tmp_path / "nonexistent" / "sessions.json"
        manager = SessionManager(store_path=store)
        assert manager.get("any") is None

    @pytest.mark.parametrize("user_key", ["user1", "telegram:100:200", "tg:0:0"])
    def test_various_user_keys(self, user_key: str) -> None:
        manager = SessionManager()
        s = manager.get_or_create(user_key)
        assert s.user_key == user_key
