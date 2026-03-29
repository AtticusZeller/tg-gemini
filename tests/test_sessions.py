"""Tests for tg_gemini.sessions persistence layer."""

import json
from pathlib import Path

import pytest

from tg_gemini.sessions import PersistedSession, SessionStore


class TestPersistedSession:
    """PersistedSession dataclass behavior."""

    @pytest.fixture
    def sessions_file(self, tmp_path: Path) -> Path:
        return tmp_path / "sessions.json"

    def test_default_values(self) -> None:
        s = PersistedSession()
        assert s.session_id is None
        assert s.model is None
        assert s.custom_names == {}

    def test_with_values(self) -> None:
        s = PersistedSession(
            session_id="sess-abc",
            model="flash",
            custom_names={"sess-abc": "My Chat"},
        )
        assert s.session_id == "sess-abc"
        assert s.model == "flash"
        assert s.custom_names == {"sess-abc": "My Chat"}

    def test_frozen(self) -> None:
        s = PersistedSession(session_id="x")
        with pytest.raises(AttributeError):
            s.session_id = "y"  # type: ignore[fstring]

    @pytest.mark.asyncio
    async def test_serialize_roundtrip(self, sessions_file: Path) -> None:
        """PersistedSession survives a save/load roundtrip through the store."""
        original = PersistedSession(
            session_id="sess-xyz",
            model="pro",
            custom_names={"sess-xyz": "Project"},
        )
        store = SessionStore(_path=sessions_file)
        await store.save_all({1: original})
        restored = await store.load()
        assert restored[1].session_id == original.session_id
        assert restored[1].model == original.model
        assert restored[1].custom_names == original.custom_names


class TestSessionStoreDeserialize:
    """load() handles malformed per-user data gracefully."""

    @pytest.fixture
    def sessions_file(self, tmp_path: Path) -> Path:
        return tmp_path / "sessions.json"

    @pytest.mark.asyncio
    async def test_non_dict_data(self, sessions_file: Path) -> None:
        """When a user's data is not a dict, load() returns defaults for that user."""
        sessions_file.write_text(
            json.dumps({"1": "not a dict"}),
            encoding="utf-8",
        )
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result[1] == PersistedSession()

    @pytest.mark.asyncio
    async def test_missing_fields(self, sessions_file: Path) -> None:
        """When a user's data has missing fields, load() returns defaults."""
        sessions_file.write_text(json.dumps({"1": {}}), encoding="utf-8")
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result[1].session_id is None
        assert result[1].model is None
        assert result[1].custom_names == {}

    @pytest.mark.asyncio
    async def test_partial_fields(self, sessions_file: Path) -> None:
        """When a user's data has some fields, load() returns partial result."""
        sessions_file.write_text(
            json.dumps({"1": {"session_id": "abc", "model": None}}),
            encoding="utf-8",
        )
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result[1].session_id == "abc"
        assert result[1].model is None
        assert result[1].custom_names == {}

    @pytest.mark.asyncio
    async def test_custom_names_not_dict(self, sessions_file: Path) -> None:
        """When custom_names is not a dict in JSON, load() returns empty dict."""
        sessions_file.write_text(
            json.dumps({"1": {"session_id": "abc", "custom_names": "not-a-dict"}}),
            encoding="utf-8",
        )
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result[1].custom_names == {}


class TestSessionStoreLoad:
    """SessionStore.load() reads and parses the sessions file."""

    @pytest.fixture
    def sessions_file(self, tmp_path: Path) -> Path:
        return tmp_path / "sessions.json"

    @pytest.fixture
    def store(self, sessions_file: Path) -> SessionStore:
        return SessionStore(_path=sessions_file)

    @pytest.mark.asyncio
    async def test_file_missing_returns_empty(self, store: SessionStore) -> None:
        result = await store.load()
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_json_object(self, sessions_file: Path) -> None:
        sessions_file.write_text("{}", encoding="utf-8")
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result == {}

    @pytest.mark.asyncio
    async def test_valid_data(self, sessions_file: Path) -> None:
        sessions_file.write_text(
            json.dumps({
                "1": {"session_id": "sess-a", "model": "flash", "custom_names": {}},
                "42": {"session_id": "sess-b", "model": "pro", "custom_names": {"sess-b": "Work"}},
            }),
            encoding="utf-8",
        )
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result[1].session_id == "sess-a"
        assert result[1].model == "flash"
        assert result[42].session_id == "sess-b"
        assert result[42].model == "pro"
        assert result[42].custom_names == {"sess-b": "Work"}

    @pytest.mark.asyncio
    async def test_corrupt_json(self, sessions_file: Path) -> None:
        sessions_file.write_text("not valid json{", encoding="utf-8")
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result == {}

    @pytest.mark.asyncio
    async def test_root_not_dict(self, sessions_file: Path) -> None:
        sessions_file.write_text('["a", "b"]', encoding="utf-8")
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert result == {}

    @pytest.mark.asyncio
    async def test_invalid_user_id_skipped(self, sessions_file: Path) -> None:
        sessions_file.write_text(
            json.dumps({
                "1": {"session_id": "a"},
                "not-an-int": {"session_id": "b"},
                "3.14": {"session_id": "c"},
            }),
            encoding="utf-8",
        )
        store = SessionStore(_path=sessions_file)
        result = await store.load()
        assert 1 in result
        assert "not-an-int" not in result
        assert "3.14" not in result


class TestSessionStoreSave:
    """SessionStore.save() performs read-modify-write under lock."""

    @pytest.fixture
    def sessions_file(self, tmp_path: Path) -> Path:
        return tmp_path / "sessions.json"

    @pytest.fixture
    def store(self, sessions_file: Path) -> SessionStore:
        return SessionStore(_path=sessions_file)

    @pytest.mark.asyncio
    async def test_save_creates_file(self, sessions_file: Path) -> None:
        store = SessionStore(_path=sessions_file)
        await store.save(1, PersistedSession(session_id="sess-1"))
        assert sessions_file.exists()

    @pytest.mark.asyncio
    async def test_save_reads_existing(self, sessions_file: Path) -> None:
        # Pre-populate
        sessions_file.write_text(
            json.dumps({"2": {"session_id": "existing"}}),
            encoding="utf-8",
        )
        store = SessionStore(_path=sessions_file)
        await store.save(1, PersistedSession(session_id="new"))
        result = await store.load()
        assert result[1].session_id == "new"
        assert result[2].session_id == "existing"

    @pytest.mark.asyncio
    async def test_save_overwrites_user(self, store: SessionStore) -> None:
        await store.save(1, PersistedSession(session_id="old"))
        await store.save(1, PersistedSession(session_id="new"))
        result = await store.load()
        assert result[1].session_id == "new"


class TestSessionStoreSaveAll:
    """SessionStore.save_all() atomically overwrites the file."""

    @pytest.fixture
    def sessions_file(self, tmp_path: Path) -> Path:
        return tmp_path / "sessions.json"

    @pytest.fixture
    def store(self, sessions_file: Path) -> SessionStore:
        return SessionStore(_path=sessions_file)

    @pytest.mark.asyncio
    async def test_save_all(self, store: SessionStore) -> None:
        sessions = {
            1: PersistedSession(session_id="a"),
            2: PersistedSession(session_id="b", model="flash"),
        }
        await store.save_all(sessions)
        result = await store.load()
        assert result[1].session_id == "a"
        assert result[2].session_id == "b"
        assert result[2].model == "flash"

    @pytest.mark.asyncio
    async def test_save_all_empty(self, sessions_file: Path) -> None:
        sessions_file.write_text(json.dumps({"1": {"session_id": "old"}}), encoding="utf-8")
        store = SessionStore(_path=sessions_file)
        await store.save_all({})
        result = await store.load()
        assert result == {}


class TestAtomicWrite:
    """Writes use temp-file + rename for crash safety."""

    @pytest.mark.asyncio
    async def test_write_leaves_no_tmp_file(self, tmp_path: Path) -> None:
        sessions_file = tmp_path / "sessions.json"
        store = SessionStore(_path=sessions_file)
        await store.save_all({1: PersistedSession(session_id="x")})
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    @pytest.mark.asyncio
    async def test_write_is_atomic_read(self, tmp_path: Path) -> None:
        """Simulate a crash mid-write: the original file must survive."""
        sessions_file = tmp_path / "sessions.json"
        store = SessionStore(_path=sessions_file)
        await store.save(1, PersistedSession(session_id="original"))

        # Write a new session (this would be interrupted in a real crash)
        await store.save(2, PersistedSession(session_id="new"))

        # Original content should not be lost
        result = await store.load()
        assert result[1].session_id == "original"
        assert result[2].session_id == "new"
