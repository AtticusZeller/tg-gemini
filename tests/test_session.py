"""Tests for Session and SessionManager classes."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from tg_gemini.session import Session, SessionManager


class TestSession:
    """Tests for the Session class."""

    def test_session_creation(self) -> None:
        """Test basic session creation."""
        session = Session(id="test-id")
        assert session.id == "test-id"
        assert session.agent_session_id == ""
        assert not session.busy
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)

    def test_session_with_agent_id(self) -> None:
        """Test session creation with agent session ID."""
        session = Session(id="test-id", agent_session_id="agent-123")
        assert session.agent_session_id == "agent-123"

    async def test_try_lock_not_busy(self) -> None:
        """Test try_lock returns True when not busy."""
        session = Session(id="test-id")
        result = await session.try_lock()
        assert result is True
        assert session.busy

    async def test_try_lock_when_busy(self) -> None:
        """Test try_lock returns False when already busy."""
        session = Session(id="test-id")
        await session.try_lock()
        result = await session.try_lock()
        assert result is False
        assert session.busy

    async def test_unlock_releases_lock(self) -> None:
        """Test unlock releases the lock."""
        session = Session(id="test-id")
        await session.try_lock()
        assert session.busy
        await session.unlock()
        assert not session.busy

    async def test_unlock_updates_timestamp(self) -> None:
        """Test unlock updates the updated_at timestamp."""
        session = Session(id="test-id")
        old_time = session.updated_at
        await session.try_lock()
        await asyncio.sleep(0.01)  # Small delay to ensure time changes
        await session.unlock()
        assert session.updated_at > old_time

    async def test_lock_can_be_reacquired_after_unlock(self) -> None:
        """Test lock can be reacquired after unlock."""
        session = Session(id="test-id")
        await session.try_lock()
        await session.unlock()
        result = await session.try_lock()
        assert result is True
        assert session.busy

    def test_busy_property(self) -> None:
        """Test busy property reflects lock state."""
        session = Session(id="test-id")
        assert not session.busy


class TestSessionManager:
    """Tests for the SessionManager class."""

    def test_get_or_create_new_session(self) -> None:
        """Test get_or_create creates a new session."""
        manager = SessionManager()
        session = manager.get_or_create("user1")
        assert isinstance(session, Session)
        assert session.id
        assert "user1" in manager._sessions

    def test_get_or_create_returns_same_session(self) -> None:
        """Test get_or_create returns the same session on second call."""
        manager = SessionManager()
        session1 = manager.get_or_create("user1")
        session2 = manager.get_or_create("user1")
        assert session1.id == session2.id
        assert session1 is session2

    def test_get_or_create_different_users(self) -> None:
        """Test get_or_create creates different sessions for different users."""
        manager = SessionManager()
        session1 = manager.get_or_create("user1")
        session2 = manager.get_or_create("user2")
        assert session1.id != session2.id

    def test_new_session_creates_fresh_session(self) -> None:
        """Test new_session creates a fresh session."""
        manager = SessionManager()
        old_session = manager.get_or_create("user1")
        new_session = manager.new_session("user1")
        assert new_session.id != old_session.id

    def test_new_session_replaces_old(self) -> None:
        """Test new_session replaces the old session."""
        manager = SessionManager()
        manager.get_or_create("user1")
        new_session = manager.new_session("user1")
        retrieved = manager.get("user1")
        assert retrieved is new_session

    def test_get_existing_session(self) -> None:
        """Test get returns existing session."""
        manager = SessionManager()
        created = manager.get_or_create("user1")
        retrieved = manager.get("user1")
        assert retrieved is created

    def test_get_nonexistent_session(self) -> None:
        """Test get returns None for non-existent session."""
        manager = SessionManager()
        result = manager.get("nonexistent")
        assert result is None

    def test_manager_without_store_path(self) -> None:
        """Test SessionManager works without a store path."""
        manager = SessionManager()
        session = manager.get_or_create("user1")
        assert session.id
        # No file I/O should occur


class TestSessionManagerPersistence:
    """Tests for SessionManager persistence."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """Test _save creates the store file."""
        store_path = tmp_path / "sessions.json"
        manager = SessionManager(store_path=store_path)
        manager.get_or_create("user1")
        manager._save()
        assert store_path.exists()

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test _save creates parent directories."""
        store_path = tmp_path / "subdir" / "sessions.json"
        manager = SessionManager(store_path=store_path)
        manager.get_or_create("user1")
        manager._save()
        assert store_path.exists()

    def test_save_content(self, tmp_path: Path) -> None:
        """Test _save writes correct content."""
        store_path = tmp_path / "sessions.json"
        manager = SessionManager(store_path=store_path)
        session = manager.get_or_create("user1")
        session.agent_session_id = "agent-123"
        manager._save()

        data = json.loads(store_path.read_text())
        assert "user1" in data
        assert data["user1"]["id"] == session.id
        assert data["user1"]["agent_session_id"] == "agent-123"
        assert "created_at" in data["user1"]
        assert "updated_at" in data["user1"]

    def test_load_on_init(self, tmp_path: Path) -> None:
        """Test sessions are loaded on manager creation."""
        store_path = tmp_path / "sessions.json"

        # Create and save sessions
        manager1 = SessionManager(store_path=store_path)
        session = manager1.get_or_create("user1")
        session.agent_session_id = "agent-123"
        manager1._save()

        # Load in new manager
        manager2 = SessionManager(store_path=store_path)
        loaded_session = manager2.get("user1")
        assert loaded_session is not None
        assert loaded_session.id == session.id
        assert loaded_session.agent_session_id == "agent-123"

    def test_load_preserves_timestamps(self, tmp_path: Path) -> None:
        """Test load preserves created_at and updated_at."""
        store_path = tmp_path / "sessions.json"

        manager1 = SessionManager(store_path=store_path)
        session = manager1.get_or_create("user1")
        original_created = session.created_at
        original_updated = session.updated_at
        manager1._save()

        manager2 = SessionManager(store_path=store_path)
        loaded_session = manager2.get("user1")
        assert loaded_session.created_at == original_created
        assert loaded_session.updated_at == original_updated

    def test_load_corrupt_file(self, tmp_path: Path) -> None:
        """Test _load handles corrupt file gracefully."""
        store_path = tmp_path / "sessions.json"
        store_path.write_text("not valid json")
        # Should not raise
        manager = SessionManager(store_path=store_path)
        assert manager.get("any") is None

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Test _load handles missing file gracefully."""
        store_path = tmp_path / "nonexistent" / "sessions.json"
        # Should not raise
        manager = SessionManager(store_path=store_path)
        assert manager.get("any") is None

    def test_new_session_saves(self, tmp_path: Path) -> None:
        """Test new_session triggers a save."""
        store_path = tmp_path / "sessions.json"
        manager = SessionManager(store_path=store_path)
        manager.get_or_create("user1")
        manager.new_session("user1")

        data = json.loads(store_path.read_text())
        assert "user1" in data

    def test_load_no_store_path(self) -> None:
        """Test _load does nothing when no store_path."""
        manager = SessionManager()
        # Should not raise
        manager._load()

    def test_save_no_store_path(self) -> None:
        """Test _save does nothing when no store_path."""
        manager = SessionManager()
        manager.get_or_create("user1")
        # Should not raise
        manager._save()


class TestConcurrentLocking:
    """Tests for concurrent session locking behavior."""

    async def test_concurrent_try_lock(self) -> None:
        """Test concurrent try_lock calls."""
        session = Session(id="test-id")

        results = await asyncio.gather(
            session.try_lock(), session.try_lock(), session.try_lock()
        )

        # Only one should succeed
        assert sum(1 for r in results if r) == 1
        assert sum(1 for r in results if not r) == 2

    async def test_concurrent_lock_unlock(self) -> None:
        """Test concurrent lock and unlock operations."""
        session = Session(id="test-id")
        lock_count = [0]

        async def locker() -> None:
            for _ in range(10):
                if await session.try_lock():
                    lock_count[0] += 1
                    await asyncio.sleep(0.001)
                    await session.unlock()

        await asyncio.gather(*[locker() for _ in range(5)])
        # With concurrent access, not all 50 attempts can succeed (only one lock holder at a time)
        # But at least some should have succeeded
        assert 1 <= lock_count[0] <= 50

    async def test_session_isolation(self) -> None:
        """Test sessions are isolated from each other."""
        manager = SessionManager()
        session1 = manager.get_or_create("user1")
        session2 = manager.get_or_create("user2")

        # Lock session1
        assert await session1.try_lock()
        # session2 should still be available
        assert await session2.try_lock()

        await session1.unlock()
        await session2.unlock()

    async def test_manager_concurrent_access(self) -> None:
        """Test concurrent access to SessionManager."""
        manager = SessionManager()

        async def create_and_lock(user_key: str) -> bool:
            session = manager.get_or_create(user_key)
            return await session.try_lock()

        results = await asyncio.gather(
            create_and_lock("user1"), create_and_lock("user2"), create_and_lock("user3")
        )

        # All should succeed since they're different sessions
        assert all(results)

    async def test_lock_released_after_exception(self) -> None:
        """Test lock state after exception in locked block."""
        session = Session(id="test-id")
        await session.try_lock()

        try:
            raise ValueError("test error")
        except ValueError:
            pass

        # Lock should still be held (unlock must be called explicitly)
        assert session.busy
        await session.unlock()
        assert not session.busy
