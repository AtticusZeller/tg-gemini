"""Session management for Telegram bot users.

Provides per-user session tracking with optional JSON persistence.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class Session:
    """A user session with locking capability.

        Sessions track the conversation state with Gemini CLI and can be locked
    to prevent concurrent access.
    """

    id: str
    agent_session_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _busy: bool = field(default=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def try_lock(self) -> bool:
        """Try to acquire the session lock. Returns False if already busy."""
        async with self._lock:
            if self._busy:
                return False
            self._busy = True
            return True

    async def unlock(self) -> None:
        """Release the session lock and update timestamp."""
        async with self._lock:
            self._busy = False
            self.updated_at = datetime.now(UTC)

    @property
    def busy(self) -> bool:
        """Check if the session is currently busy."""
        return self._busy


class SessionManager:
    """Manages one session per user key with optional JSON persistence."""

    def __init__(self, store_path: Path | None = None) -> None:
        """Initialize the session manager.

        Args:
            store_path: Optional path to a JSON file for persisting sessions.
        """
        self._sessions: dict[str, Session] = {}
        self._store_path = store_path
        if store_path and store_path.exists():
            self._load()

    def get_or_create(self, user_key: str) -> Session:
        """Get existing session or create a new one for the user.

        Args:
            user_key: Unique identifier for the user.

        Returns:
            The existing or newly created session.
        """
        if user_key not in self._sessions:
            self._sessions[user_key] = Session(id=str(uuid.uuid4()))
        return self._sessions[user_key]

    def new_session(self, user_key: str) -> Session:
        """Create a fresh session for user_key, replacing any existing one.

        Args:
            user_key: Unique identifier for the user.

        Returns:
            The newly created session.
        """
        session = Session(id=str(uuid.uuid4()))
        self._sessions[user_key] = session
        self._save()
        return session

    def get(self, user_key: str) -> Session | None:
        """Get the session for a user if it exists.

        Args:
            user_key: Unique identifier for the user.

        Returns:
            The session if it exists, otherwise None.
        """
        return self._sessions.get(user_key)

    def _save(self) -> None:
        """Persist sessions to the store file."""
        if not self._store_path:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, dict[str, str]] = {
            key: {
                "id": s.id,
                "agent_session_id": s.agent_session_id,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for key, s in self._sessions.items()
        }
        self._store_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        """Load sessions from the store file."""
        if not self._store_path:
            return
        try:
            data: dict[str, dict[str, str]] = json.loads(self._store_path.read_text())
            for key, s in data.items():
                session = Session(
                    id=s["id"],
                    agent_session_id=s.get("agent_session_id", ""),
                    created_at=datetime.fromisoformat(s["created_at"]),
                    updated_at=datetime.fromisoformat(s["updated_at"]),
                )
                self._sessions[key] = session
        except Exception:
            pass  # ignore corrupt store
