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

### 2.2 `Session` (in-memory, per-user)

Defined in `src/tg_gemini/session.py`:

```python
@dataclass
class Session:
    id: str                                # UUID v4
    user_key: str = ""                      # "telegram:{chat_id}:{user_id}"
    agent_session_id: str = ""              # Gemini CLI session ID for --resume
    name: str = ""                          # User-given name
    history: list[HistoryEntry] = field(default_factory=list)
    created_at: datetime = ...              # UTC timestamp
    updated_at: datetime = ...              # Updated on unlock()
    _busy: bool = False                     # Whether session is processing
    _lock: asyncio.Lock = ...               # Per-session concurrency lock
```

### 2.3 `SessionManager`

Defined in `src/tg_gemini/session.py`. Manages multiple sessions per user:

```python
class SessionManager:
    def __init__(self, store_path: Path | None = None) -> None: ...
    def new_session(self, user_key: str, name: str = "") -> Session: ...
    def get(self, user_key: str) -> Session | None: ...
    def list_sessions(self, user_key: str) -> list[Session]: ...    # Sorted by updated_at desc
    def switch_session(self, user_key: str, target: str) -> Session | None: ...
    def delete_sessions(self, ids: list[str]) -> int: ...
    def active_session_id(self, user_key: str) -> str: ...
```

- Sessions are persisted to a JSON file via `_save()` / `_load()`
- Atomic write (temp file + rename) — survives crashes
- File location: `~/.tg-gemini/sessions.json` (configurable via `data_dir`)
- Graceful degradation: corrupt or missing files return empty, never crash

### 2.4 `SessionInfo` (returned from Gemini CLI)

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
    └─> Engine.handle_message()
    └─> Engine._process()
            └─> SessionManager.get_or_create(session_key) → Session (agent_session_id="")
            └─> Engine._run_gemini(session, ...)
                    └─> GeminiSession.send(prompt) → gemini subprocess
                    └─> _read_loop() → reads JSONL events
                            └─> init event → Event(type=INIT, session_id="abc-123-...")
                    └─> Engine processes INIT event:
                            └─> session.agent_session_id = "abc-123-..."  ← captured for resume
            └─> SessionManager._save()  ← persists to disk
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

`SessionManager` persists all sessions to `~/.tg-gemini/sessions.json`:

```json
{
  "version": 2,
  "sessions": {
    "uuid-v4": {
      "id": "uuid-v4",
      "user_key": "telegram:123:456",
      "agent_session_id": "gemini-session-id",
      "name": "My Session",
      "history": [],
      "created_at": "2026-03-29T10:00:00+00:00",
      "updated_at": "2026-03-29T10:00:05+00:00"
    }
  },
  "active_sessions": {"telegram:123:456": "uuid-v4"},
  "session_counter": 1
}
```

Fields **NOT persisted** (rebuilt on restart):
- `_busy` / `_lock` — runtime state only

### When Persistence Happens

| Event | Action |
|---|---|
| `new_session()` / `switch_session()` / `delete_session()` / `set_session_name()` | `SessionManager._save()` — persists immediately |
| Stream completes | `SessionManager._save()` — persists captured `agent_session_id` |

### File Format

`~/.tg-gemini/sessions.json` (configurable via `data_dir` in config):

```json
{
  "version": 2,
  "sessions": {
    "uuid-v4": {
      "id": "uuid-v4",
      "user_key": "telegram:123:456",
      "agent_session_id": "gemini-session-id",
      "name": "My Session",
      "history": [
        {"role": "user", "content": "hello", "timestamp": "2026-03-29T10:00:00+00:00"},
        {"role": "assistant", "content": "Hi!", "timestamp": "2026-03-29T10:00:05+00:00"}
      ],
      "created_at": "2026-03-29T10:00:00+00:00",
      "updated_at": "2026-03-29T10:00:05+00:00"
    }
  },
  "active_sessions": {"telegram:123:456": "uuid-v4"},
  "session_counter": 1
}
```

## 7. Command Reference

| Command | Effect on Session | Effect on other fields |
|---|---|---|
| `/new [name]` | `SessionManager.new_session()` — creates fresh session, makes active | Sets `name` |
| `/switch <id\|index\|name>` | `SessionManager.switch_session()` — changes active session | — |
| `/list [query]` | Displays sessions with inline keyboard (Switch + Delete buttons) | — |
| `/delete` | Enter interactive delete mode with toggle selections | — |
| `/delete_one <id>` | `SessionManager.delete_session()` — removes single session | — |
| `/name <name>` | `SessionManager.set_session_name()` — renames current session | — |
| `/model [name]` | Shows/switches model via inline keyboard | `agent.model` |
| `/mode [mode]` | Shows/switches approval mode via inline keyboard | `agent.mode` |
| `/current` | Shows active session info | — |
| `/history` | Shows recent conversation history | — |
| `/status` | Shows bot/session status | — |
| `/stop` | Signals stop via `asyncio.Event` | Best-effort, no subprocess kill |
| `/quiet` | Toggle quiet mode (suppress tool output) | Per-session `_InteractiveState` |
| `/commands reload` | Reloads commands and skills, refreshes Telegram menu | — |
| Any other message | Routes to `_process()` → `_run_gemini()` | — |

## 8. Message Flow (Full Pipeline)

```
Telegram message
    │
    ├─ TelegramPlatform._handle_update()
    │       ├─ Filter old messages (>30s), check allow_from
    │       ├─ Build Message with ReplyContext → Engine.handle_message()
    │
    ├─ Engine.handle_message()
    │       ├─ Dedup check (MessageDedup)
    │       ├─ Rate limit check (RateLimiter)
    │       ├─ Slash command? → handle_command()
    │       └─ Session busy? → enqueue (max 5)
    │
    └─ Engine._process() → Engine._run_gemini()
            ├─ SessionManager.get_or_create(session_key) → Session
            ├─ Session.try_lock() → acquires asyncio.Lock
            ├─ GeminiAgent.start_session(resume_id=session.agent_session_id)
            │       └─ Returns GeminiSession
            ├─ GeminiSession.send(prompt)
            │       └─ asyncio.create_subprocess_exec("gemini", ...)
            ├─ _read_loop() → reads JSONL → emits Events into asyncio.Queue
            │
            ├─ Engine consumes events:
            │       ├─ INIT → store session.agent_session_id for resume
            │       ├─ TEXT → StreamPreview.append_text()
            │       ├─ TOOL_USE → StreamPreview.freeze() + platform.send(tool_msg)
            │       ├─ TOOL_RESULT → platform.send(result_msg) (quiet mode skips)
            │       ├─ ERROR → platform.send(error_msg)
            │       └─ RESULT → StreamPreview.finish() → platform.reply()
            │
            ├─ Session.unlock() → updates timestamp
            └─ SessionManager._save()  ← persists to disk
```

## 9. Shutdown Flow

```
SIGTERM / SIGINT received
    └─> asyncio.Event (shutdown signal)
            └─> Engine stops processing
            └─> SessionManager._save() persists all sessions to disk
                    └─> Atomic write to ~/.tg-gemini/sessions.json
```

All session state is persisted atomically before the process exits.

## 10. Relevant Files

| File | Responsibility |
|---|---|
| `src/tg_gemini/session.py` | `Session`, `SessionManager` — multi-session management, JSON persistence |
| `src/tg_gemini/engine.py` | Message routing, command dispatch, `_run_gemini`, event processing, card UI |
| `src/tg_gemini/gemini.py` | `GeminiSession` subprocess + JSONL parsing, `GeminiAgent` factory, `list_sessions`, `delete_session`, `run_stream` |
| `src/tg_gemini/events.py` | Pydantic event models including `InitEvent` with `session_id` field |
| `src/tg_gemini/config.py` | `AppConfig` with `GeminiConfig` (`model`, `mode`, `work_dir`, `cmd`, `api_key`, `timeout_mins`) |

## 11. Limitations

### 11.1 No Cross-Device Continuity

A session is tied to a Telegram user ID. If the same user connects from multiple devices, they share the session — but there is no mechanism to resume a session from a different user account.

### 11.2 Multi-Session Model

The current architecture uses `SessionManager` from `session.py` which supports multiple named sessions per user. Sessions are identified by UUIDs and sorted by `updated_at`. The `/switch` command replaces the old `/resume` and accepts a 1-based index, ID prefix, or name substring to change the active session.

### 11.3 Graceful Degradation on Persistence Failure

If the sessions file is corrupt or unreadable, `SessionStore.load()` returns `{}` and the bot continues with in-memory sessions only. Errors are logged but never crash the bot.
