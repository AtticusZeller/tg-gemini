# Session Management & Concurrency Improvements

## Context

Four architectural limitations were identified in the tg-gemini bot:

1. **Problem 1 — Coarse lock**: `session.lock` is held for the entire `_process_stream` (seconds-long streaming duration), blocking commands like `/list`, `/status`, `/model` from running
2. **Problem 2 — Race conditions**: Command handlers (`cmd_list`, `cmd_delete`, `cmd_resume`, `cmd_model`, `cmd_name`) mutate `session.session_id`, `session.model`, `session.custom_names` without any lock, racing against `handle_message` → `_handle_event` which also writes these fields
3. **Problem 3 — No persistence**: All `UserSession` state is in-memory `dict[int, UserSession]`, lost on every restart
4. **Problem 4 — No auto-recovery**: After restart, `session.session_id = None` and users must manually `/resume`

**Root cause**: Single `asyncio.Lock` used for two orthogonal concerns — serializing concurrent stream operations (needs long hold) and protecting session state mutations (needs short hold).

---

## Design

### Architecture

```
~/.config/tg-gemini/
  config.toml          ← existing
  sessions.json        ← NEW: per-user session metadata

SessionStore (sessions.py)        ← async JSON persistence
  .load() → dict[int, PersistedSession]
  .save(user_id, session)
  .save_all(sessions)

SessionManager (bot.py)
  .create(store) → loads persisted sessions on startup
  .save(user_id) → persists one user's session after mutations
  .shutdown()    → persists all sessions on SIGTERM/SIGINT

UserSession (bot.py)
  session_id: str | None      ← persisted
  model: str | None            ← persisted
  custom_names: dict           ← persisted
  mutation_lock: asyncio.Lock  ← guards ALL mutations (microseconds)
  last_sessions: list         ← NOT persisted (fetched fresh from gemini CLI)
  pending_name: str | None     ← NOT persisted (runtime only)
  active: bool                 ← NOT persisted (runtime only)

handle_message → captures session_id/model BEFORE streaming
                 → streams WITHOUT holding any lock
                 → commands completely unblocked

_handle_event → InitEvent: acquires mutation_lock briefly, saves session

Commands → acquire mutation_lock for brief mutations → save to disk
```

### Persisted JSON schema

```jsonc
{
  "123456": {
    "session_id": "abc-123-def",   // null = new session
    "model": "pro",                // null = use config default
    "custom_names": {
      "abc-123-def": "Project X"
    }
  }
}
```

Fields NOT persisted (runtime-only): `active`, `pending_name`, `last_sessions`, `lock`, `mutation_lock`.

---

## Implementation

### Step 1: Create `src/tg_gemini/sessions.py` (NEW FILE)

Pure utility, no dependencies on bot.py.

- `PersistedSession` dataclass — frozen, subset of `UserSession` fields
- `SessionStore` class:
  - `load()` → async read via `asyncio.to_thread` (non-blocking), returns `dict[int, PersistedSession]`
  - `save(user_id, session)` → read-modify-write under `_lock`, atomic (temp + rename)
  - `save_all(sessions)` → full overwrite (used on shutdown)
  - `_dirty` set for future lazy-save debouncing
  - All errors caught, logged, and degraded gracefully (empty dict returned)

Key design: all file I/O on thread pool (`asyncio.to_thread`) — never blocks the event loop.

### Step 2: Update `src/tg_gemini/bot.py`

#### 2a. Add `mutation_lock` to `UserSession`; remove `lock`

```python
@dataclass
class UserSession:
    session_id: str | None = None
    model: str | None = None
    active: bool = True
    mutation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_sessions: list[SessionInfo] = field(default_factory=list)
    custom_names: dict[str, str] = field(default_factory=dict)
    pending_name: str | None = None
```

#### 2b. Update `SessionManager`

```python
class SessionManager:
    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._sessions: dict[int, UserSession] = {}

    @classmethod
    async def create(cls, store: SessionStore) -> SessionManager:
        self = cls(store)
        persisted = await store.load()
        for uid, data in persisted.items():
            self._sessions[uid] = UserSession(
                session_id=data.session_id,
                model=data.model,
                custom_names=data.custom_names,
            )
        return self

    def get(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]

    async def save(self, user_id: int) -> None:
        session = self._sessions.get(user_id)
        if session is None:
            return
        await self._store.save(
            user_id,
            PersistedSession(
                session_id=session.session_id,
                model=session.model,
                custom_names=session.custom_names,
            ),
        )

    async def shutdown(self) -> None:
        all_sessions = {
            uid: PersistedSession(session_id=s.session_id, model=s.model, custom_names=s.custom_names)
            for uid, s in self._sessions.items()
        }
        await self._store.save_all(all_sessions)
```

#### 2c. Restructure `handle_message` — capture state, stream unlocked

```python
@router.message(F.text & ~F.text.startswith("/"))
async def handle_message(
    message: Message, sessions: SessionManager, agent: GeminiAgent, config: AppConfig
) -> None:
    if not message.from_user or not message.text:
        return
    if not _is_authorized(message.from_user.id, config.telegram.allowed_user_ids):
        return

    session = sessions.get(message.from_user.id)
    if not session.active:
        return

    # Capture state BEFORE streaming — these locals remain stable even if
    # concurrent commands mutate the session object.
    session_id = session.session_id
    model = session.model

    # Stream WITHOUT holding any lock — commands are unblocked
    await _process_stream(message, session, agent, session_id, model)
```

#### 2d. Update `_process_stream` signature

```python
async def _process_stream(
    message: Message,
    session: UserSession,
    agent: GeminiAgent,
    session_id: str | None,
    model: str | None,
) -> tuple[str, list[str]]:
    # ...
    async for event in agent.run_stream(message.text or "", session_id, model):
    # ...
```

#### 2e. Update `_handle_event` — use `mutation_lock` for InitEvent write

```python
async def _handle_event(
    event: object, session: UserSession, state: _StreamState, reply: Message
) -> None:
    if isinstance(event, InitEvent):
        async with session.mutation_lock:
            session.session_id = event.session_id
            if session.pending_name and event.session_id:
                session.custom_names[event.session_id] = session.pending_name
                session.pending_name = None
        # Persist immediately after session_id is set
        # NOTE: sessions.save() must be called by the caller (see below)
    # ...
```

**Save strategy (user choice)**: Save once after `_process_stream` completes. `handle_message` calls `sessions.save(user_id)` after the stream finishes. Simpler than saving inside `_handle_event`. Risk: if bot crashes mid-stream, the session_id from InitEvent is lost — recoverable via `/resume`.

#### 2f. Update all command handlers — lock + save

```python
# cmd_new
async with session.mutation_lock:
    session.session_id = None
    session.pending_name = command.args or None
await sessions.save(message.from_user.id)

# cmd_resume
async with session.mutation_lock:
    session.session_id = target_id
await sessions.save(message.from_user.id)

# cmd_model
async with session.mutation_lock:
    session.model = command.args
await sessions.save(message.from_user.id)

# cmd_name
async with session.mutation_lock:
    session.custom_names[session.session_id] = command.args
await sessions.save(message.from_user.id)

# cmd_delete
success = await agent.delete_session(target_id)
if success:
    async with session.mutation_lock:
        if session.session_id == target_id:
            session.session_id = None
        session.custom_names.pop(target_id, None)
    await sessions.save(message.from_user.id)
```

`cmd_list`: No lock needed — `last_sessions` is not persisted and is overwritten entirely.

#### 2g. Update `start_bot` — create store, load sessions, register shutdown

```python
import signal

async def start_bot(config: AppConfig) -> None:
    bot = Bot(token=config.telegram.bot_token)
    # ... set_my_commands unchanged ...

    # Create store and load persisted sessions
    sessions_path = Path.home() / ".config" / "tg-gemini" / "sessions.json"
    store = SessionStore(_path=sessions_path)
    sessions = await SessionManager.create(store)

    dp = Dispatcher()
    dp.include_router(router)

    agent = GeminiAgent(config.gemini)

    # Register graceful shutdown
    async def _shutdown() -> None:
        logger.info("shutdown_signal_received")
        await sessions.shutdown()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_shutdown()))

    try:
        await dp.start_polling(bot, sessions=sessions, agent=agent, config=config)
    finally:
        await sessions.shutdown()
```

**Note**: `signal.SIGTERM` doesn't work on Windows consoles, but `SIGINT` (Ctrl+C) works everywhere. For a Linux VPS this is fine.

### Step 3: Update `tests/test_bot.py`

1. **`SessionManager()` constructor**: `SessionManager` now takes a `store` parameter. Existing tests using `SessionManager()` directly need `SessionManager(MagicMock(spec=SessionStore))` or a mock store.
2. **`_process_stream` signature**: Tests calling `_process_stream` directly need to add `session_id` and `model` args.
3. **Add tests for `mutation_lock`**: Verify lock is held briefly during `_handle_event`.
4. **Add tests for `start_bot`**: Mock `SessionManager.create()` and `sessions.shutdown()`.

### Step 4: Create `tests/test_sessions.py` (NEW FILE)

Unit tests for `SessionStore`:
- Missing file → empty dict
- Valid file → correct `PersistedSession` objects
- Missing keys → defaults
- Invalid JSON → empty dict + warning log
- Non-integer user IDs → skipped
- `save()` creates file, preserves other users
- `save_all()` overwrites atomically
- Atomic write (no `.tmp` left behind)

### Step 5: Update `tests/integration/test_session_lifecycle.py`

1. **Fix `SessionManager()` calls**: Add mock store parameter.
2. **Fix `_process_stream` calls**: Add `session_id` and `model` args.
3. **`TestConcurrency`**: Update `test_same_user_serialized_by_lock` — the test calls `_process_stream` directly without aiogram's queue. After removing `session.lock`, this test no longer needs to verify lock-based serialization. Instead, verify that `agent.run_stream` is called with the correct captured `session_id`/`model` values.
4. **Add `TestPersistenceRecovery`**: Tests for auto-resume from disk, `sessions.save()`, `sessions.shutdown()`.

---

## Verification

### Running tests
```bash
bash dev.sh check    # format + lint + test (full pipeline)
```

### Manual testing
1. Start bot, set a model (`/model pro`) and a session name (`/new`, send a message, `/name MySession`)
2. Send SIGTERM or Ctrl+C
3. Restart bot — verify `/current` shows the persisted model and session
4. Send a new message — verify Gemini resumes the conversation (no `/new` needed)

### Key invariants to verify
- Commands run while a stream is in progress (verify with a slow Gemini response)
- `session_id` is correct after concurrent `/resume` during streaming
- `sessions.json` contains correct data after mutations
- Bot recovers correctly from corrupt/missing `sessions.json`

---

## Critical Files

| File | Changes |
|---|---|
| `src/tg_gemini/sessions.py` | **NEW** — `SessionStore`, `PersistedSession` |
| `src/tg_gemini/bot.py` | Restructure lock, `SessionManager` factory, persistence hooks, all commands |
| `src/tg_gemini/cli.py` | No changes needed (already calls `asyncio.run(start_bot(cfg))`) |
| `tests/test_sessions.py` | **NEW** — `SessionStore` unit tests |
| `tests/test_bot.py` | Fix `SessionManager()` constructor, `_process_stream` signature, add new tests |
| `tests/integration/test_session_lifecycle.py` | Fix constructor calls, `_process_stream` args, add `TestPersistenceRecovery` |
