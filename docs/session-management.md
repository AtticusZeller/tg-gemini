# Session Management

This document describes how `tg-gemini` manages user sessions, the lifecycle of session state, persistence to disk, and how the Telegram bot and Gemini CLI coordinate to provide continuous conversations.

## 1. Overview

Sessions link a sequence of Telegram messages to a single Gemini CLI conversation. Each Telegram user gets an isolated session that tracks which Gemini session they are talking to.

**Key principle**: The `session_id` is determined by the Gemini CLI, not by `tg-gemini`. On the first message, no `session_id` is passed to the CLI, which creates a new session and announces its ID via the first `init` event. `tg-gemini` captures that ID and reuses it for all subsequent messages.

**Key architectural improvements**:
- Sessions are **persisted** to `~/.config/tg-gemini/sessions.json` — survive restarts
- Streaming does **not hold any lock** — commands remain responsive during long streams
- State mutations are **microsecond-granular** — protected by per-user `mutation_lock`, not coarse locks

## 2. Data Structures

### 2.1 `PersistedSession` (on-disk, per-user)

Defined in `src/tg_gemini/sessions.py`. Subset of session state that survives a restart:

```python
@dataclass(frozen=True)
class PersistedSession:
    session_id: str | None = None   # Gemini session ID; None = new session on next message
    model: str | None = None         # Per-user model override
    custom_names: dict[str, str] = field(default_factory=dict)  # User-given session names
```

### 2.2 `UserSession` (in-memory, per-user)

Defined in `src/tg_gemini/bot.py`:

```python
@dataclass
class UserSession:
    session_id: str | None = None     # Gemini session ID; None = new session on next message
    model: str | None = None          # Per-user model override (None = use config default)
    active: bool = True               # Whether the bot responds to this user
    mutation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # Guards state mutations only
    last_sessions: list[SessionInfo] = field(default_factory=list)    # Cached /list output
    custom_names: dict[str, str] = field(default_factory=dict)        # User-given names for sessions
    pending_name: str | None = None   # Name queued for the next session to be created
    stop_event: asyncio.Event | None = None  # Stop signal for in-flight streams
```

### 2.3 `SessionStore` (persistence layer)

Defined in `src/tg_gemini/sessions.py`. Async-safe JSON store backed by a file:

```python
class SessionStore:
    def __init__(self, *, _path: Path | None = None, _lock: asyncio.Lock | None = None) -> None: ...
    async def load(self) -> dict[int, PersistedSession]: ...
    async def save(self, user_id: int, session: PersistedSession) -> None: ...
    async def save_all(self, sessions: dict[int, PersistedSession]) -> None: ...
```

- All I/O runs on a thread pool via `asyncio.to_thread` — never blocks the event loop
- Writes use **atomic rename** (temp file + `tmp.replace(path)`) — survives crashes
- File location: `~/.config/tg-gemini/sessions.json`
- Graceful degradation: corrupt or missing files return empty dict, never crash

### 2.4 `SessionManager`

```python
class SessionManager:
    def __init__(self, store: SessionStore | None = None) -> None: ...
    @classmethod
    async def create(cls, store: SessionStore) -> SessionManager: ...  # Loads persisted sessions
    async def save(self, user_id: int) -> None: ...                     # Saves one user's state
    async def shutdown(self) -> None: ...                                 # Saves all on exit
    def get(self, user_id: int) -> UserSession: ...                      # Lazy creation
```

### 2.5 `SessionInfo` (returned from Gemini CLI)

Defined in `src/tg_gemini/gemini.py`:

```python
@dataclass(frozen=True)
class SessionInfo:
    index: int       # Position in gemini --list-sessions output
    title: str       # Auto-generated session title from Gemini
    time: str        # Relative time string, e.g. "2 hours ago"
    session_id: str  # The UUID used by Gemini CLI
```

Fetched by `agent.list_sessions()`, parsed via regex from the plain-text output of `gemini --list-sessions`.

## 3. Session Lifecycle

### 3.1 New Session (First Message)

```
User sends message
    └─> handle_message (captures session_id=None, model=None BEFORE streaming)
    └─> _process_stream(bot.py:635)
            └─> agent.run_stream(prompt, session_id=None, ...)
                    └─> gemini -p "prompt" --output-format stream-json [no -r flag]
                            └─> Gemini CLI creates a NEW session internally
                            └─> stdout: first line is an "init" event
                                    {
                                      "type": "init",
                                      "session_id": "abc-123-...",
                                      "model": "gemini-2.5-flash"
                                    }
            └─> _handle_event InitEvent (bot.py:587)
                    └─> async with session.mutation_lock:  ← µs lock
                            session.session_id = event.session_id   ← captured here
    └─> await sessions.save(user_id)  ← persists to disk
```

### 3.2 Continuing a Session (after first message)

```
User sends next message
    └─> handle_message (captures session.session_id, session.model from memory)
    └─> _process_stream
            └─> agent.run_stream(prompt, session_id=session.session_id, ...)
                    └─> gemini -r <session_id> -p "prompt" --output-format stream-json
                            └─> Gemini CLI resumes the existing session
```

The `session_id` is captured **before** streaming begins. This is safe against concurrent command mutations — even if `/new` or `/resume` is called during streaming, the in-flight stream uses the captured value.

### 3.3 Restart Recovery

```
Bot starts
    └─> SessionManager.create(store)
            └─> SessionStore.load() reads ~/.config/tg-gemini/sessions.json
            └─> Restores session_id, model, custom_names for each user
    └─> User sends message
            └─> handle_message captures restored session_id from memory
            └─> _process_stream uses session_id → gemini -r <id>
                    └─> Conversation continues WITHOUT /resume
```

Sessions persist across bot restarts. Users do **not** need to manually `/resume` after the bot restarts — their `session_id` is restored from disk automatically.

### 3.4 Named Sessions

Users can name a session via `/name <name>`. The name is stored in `session.custom_names[session_id]` and displayed in `/list` instead of the auto-generated title.

If a user runs `/new [name]` before any message is sent, `pending_name` is set. When the `init` event arrives, the name is applied under `mutation_lock`:

```python
# bot.py:589-594
if session.pending_name and event.session_id:
    async with session.mutation_lock:
        session.custom_names[event.session_id] = session.pending_name
        session.pending_name = None
```

### 3.5 Deleting a Session

```
User runs /delete <index|id>
    └─> async with session.mutation_lock:  ← µs lock
            └─> agent.delete_session(target_id)
                    └─> gemini --delete-session <id>
            └─> If target_id == session.session_id: session.session_id = None
            └─> Remove from session.custom_names
    └─> await sessions.save(user_id)  ← persists changes
```

After deletion, the next message creates a brand new session.

## 4. Concurrency Control

### Lock Granularity

Each `UserSession` has its own `mutation_lock`. There are **two separate concerns**:

| Concern | Protection | Duration |
|---|---|---|
| Stream abortion (`stop_event`) | Per-session `stop_event: asyncio.Event` | Until stream ends |
| State mutations (`session_id`, `model`, `custom_names`) | Per-session `mutation_lock` | Microseconds |

### Streaming is Lock-Free

The key insight: **`_process_stream` does NOT acquire `mutation_lock`** during streaming. This means:

- Commands (`/new`, `/resume`, `/delete`, etc.) can run **unblocked** while a user is still streaming
- The lock only guards the **few microseconds** when writing `session_id` upon `InitEvent`
- State is **captured before streaming** and remains stable even if commands mutate session during the stream:

```python
# handle_message (bot.py:710-719)
session_id = session.session_id   # CAPTURED before streaming
model = session.model             # CAPTURED before streaming

# Stream WITHOUT holding any lock — commands remain unblocked
await _process_stream(message, session, agent, session_id, model, sessions)

# Persist session state after the stream completes
await sessions.save(message.from_user.id)
```

### Per-User Serialization

Within a single user's session, messages are serialized by the fact that each message goes through `handle_message` sequentially (via aiogram's Dispatcher). The `mutation_lock` is only needed when multiple concurrent handlers (e.g., a command and a streaming message) might both write to the same `UserSession` fields.

### Cross-User Parallelism

Different users have different `UserSession` objects with different `mutation_lock` instances — they can process messages fully in parallel.

## 5. Stream Abortion (`stop_event`)

When a user sends `/stop` or when the bot shuts down, an `asyncio.Event` (`stop_event`) is used to abort the in-flight stream:

```python
# Wire up stop signal so the /stop button can abort this stream
stop_evt = asyncio.Event()
session.stop_event = stop_evt

async for event in agent.run_stream(prompt, session_id, model, stop_event=stop_evt):
    await _handle_event(event, session, state, reply)
    if state.aborted:
        break
```

The `stop_event` is checked **inside** `agent.run_stream` — it sets `stop_evt` and the subprocess is killed via `proc.terminate()`.

## 6. Persistence Strategy

### What is Persisted

`PersistedSession` captures only the fields that need to survive a restart:

- `session_id` — so old conversations continue after restart
- `model` — per-user model preference
- `custom_names` — user-given session names

Fields **NOT persisted** (rebuilt on restart):
- `last_sessions` — refetched via `gemini --list-sessions`
- `pending_name` — cleared on restart (name queued for a session that didn't start)
- `active` — always `True` on restart

### When Persistence Happens

| Event | Action |
|---|---|
| Stream completes | `await sessions.save(user_id)` — persists captured `session_id` |
| Command mutates session | `await sessions.save(user_id)` — persists immediately |
| Bot shutdown | `await sessions.shutdown()` — saves all users atomically |

### File Format

`~/.config/tg-gemini/sessions.json`:

```json
{
  "1": {
    "session_id": "abc-123-...",
    "model": "flash",
    "custom_names": {"abc-123-...": "My Project"}
  },
  "42": {
    "session_id": "xyz-789",
    "model": "pro",
    "custom_names": {}
  }
}
```

## 7. Command Reference

| Command | Effect on `session_id` | Effect on other fields |
|---|---|---|
| `/new [name]` | Sets `session_id = None` under `mutation_lock` | Sets `pending_name` |
| `/resume <id\|index>` | Sets `session_id = target_id` under `mutation_lock` | Clears `pending_name` |
| `/resume` (no args) | Sets `session_id = "latest"` | Clears `pending_name` |
| `/delete <id\|index>` | Clears `session_id` if matches | Removes from `custom_names` |
| `/name <name>` | None | Sets `custom_names[session_id]` |
| `/model <name>` | None | Sets `session.model` |
| Any other message | Uses captured `session_id` | — |

All command handlers that mutate session state hold `mutation_lock` for only the few microseconds needed to update the fields, then release it.

## 8. Message Flow (Full Pipeline)

```
Telegram message
    │
    ├─ SessionManager.get(user_id) → UserSession
    │       └─ (creates UserSession if first time; session_id may be restored from disk)
    │
    ├─ Capture state BEFORE streaming
    │       session_id = session.session_id    ← stable snapshot
    │       model = session.model              ← stable snapshot
    │
    ├─ _process_stream (NO lock held during streaming)
    │       ├─ message.answer("Thinking...")
    │       ├─ agent.run_stream(prompt, session_id, model, stop_event)
    │       │       ├─ Builds CLI args: gemini -p <prompt> -r <session_id> ...
    │       │       ├─ asyncio.create_subprocess_exec → non-blocking
    │       │       └─ Yields events parsed from NDJSON stdout
    │       │
    │       ├─ for event in stream: _handle_event(event, session, state, reply)
    │       │       ├─ InitEvent  → async with mutation_lock: session.session_id = ...
    │       │       ├─ MessageEvent → accumulate text, throttle-edit Telegram message
    │       │       ├─ ToolUseEvent → send tool display message to Telegram
    │       │       ├─ ToolResultEvent → edit tool message with ✅/❌
    │       │       ├─ ErrorEvent → edit reply with error, set aborted=True
    │       │       └─ ResultEvent → extract stats (tokens, duration)
    │       │
    │       └─ Final UI update
    │               ├─ If tools used: delete "Thinking...", send final response as new message
    │               └─ If no tools: edit "Thinking..." in place
    │
    └─ await sessions.save(user_id)  ← persist after stream completes
```

## 9. Shutdown Flow

```
SIGTERM / SIGINT received
    └─> _shutdown()
            └─> await sessions.shutdown()
                    └─> SessionStore.save_all({uid: PersistedSession(...) for uid, s in _sessions.items()})
                            └─> Atomic write to ~/.config/tg-gemini/sessions.json
            └─> await bot.session.close()
```

All session state is persisted atomically before the process exits.

## 10. Relevant Files

| File | Responsibility |
|---|---|
| `src/tg_gemini/sessions.py` | `PersistedSession`, `SessionStore` — async JSON persistence, atomic writes |
| `src/tg_gemini/bot.py` | `UserSession`, `SessionManager`, all command handlers, `_process_stream`, event dispatch |
| `src/tg_gemini/gemini.py` | Subprocess execution, CLI argument building, `list_sessions`, `delete_session` |
| `src/tg_gemini/events.py` | Pydantic event models including `InitEvent` with `session_id` field |
| `src/tg_gemini/config.py` | `GeminiConfig` with `model`, `approval_mode`, `working_dir` |

## 11. Limitations

### 11.1 No Cross-Device Continuity

A session is tied to a Telegram user ID. If the same user connects from multiple devices, they share the session — but there is no mechanism to resume a session from a different user account.

### 11.2 `latest` String as Session ID

When `/resume` is called with no argument, `session.session_id` is set to the string `"latest"`. This is a special value that Gemini CLI interprets as "use the most recent session". The `SessionInfo` objects fetched by `/list` contain real UUIDs, so `session.last_sessions` is used to resolve index arguments.

### 11.3 Graceful Degradation on Persistence Failure

If the sessions file is corrupt or unreadable, `SessionStore.load()` returns `{}` and the bot continues with in-memory sessions only. Errors are logged but never crash the bot.
