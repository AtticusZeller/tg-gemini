# Session Management

This document describes how `tg-gemini` manages user sessions, the lifecycle of session state, and how the Telegram bot and Gemini CLI coordinate to provide continuous conversations.

## 1. Overview

Sessions are the mechanism that links a sequence of Telegram messages to a single Gemini CLI conversation. Each Telegram user gets an isolated in-memory session that tracks which Gemini session they are talking to.

**Key principle**: The `session_id` is determined by the Gemini CLI, not by `tg-gemini`. On the first message, no `session_id` is passed to the CLI, which creates a new session and announces its ID via the first `init` event. `tg-gemini` captures that ID and reuses it for all subsequent messages from that user.

## 2. Data Structures

### 2.1 `UserSession` (in-memory, per-user)

Defined in `src/tg_gemini/bot.py`:

```python
@dataclass
class UserSession:
    session_id: str | None = None     # Gemini session ID; None = new session on next message
    model: str | None = None          # Overrides config default for this user
    approval_mode: str | None = None  # Overrides config default for this user
    active: bool = True               # Whether the bot responds to this user
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # Serializes message processing
    last_sessions: list[SessionInfo] = field(default_factory=list)  # Cached /list output
    custom_names: dict[str, str] = field(default_factory=dict)  # User-given names for sessions
    pending_name: str | None = None   # Name queued for the next session to be created
```

### 2.2 `SessionManager`

```python
class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[int, UserSession] = {}
```

A simple `dict[int, UserSession]` keyed by Telegram user ID. Sessions are created lazily on first access via `sessions.get(user_id)`.

### 2.3 `SessionInfo` (returned from Gemini CLI)

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
    └─> _process_stream(bot.py:563)
            └─> agent.run_stream(prompt, session_id=None, ...)
                    └─> gemini -p "prompt" --output-format stream-json [no -r flag]
                            └─> Gemini CLI creates a NEW session internally
                            └─> stdout: first line is an "init" event
                                    {
                                      "type": "init",
                                      "session_id": "abc-123-...",
                                      "model": "gemini-2.5-flash"
                                    }
            └─> _handle_event InitEvent (bot.py:179)
                    └─> session.session_id = event.session_id   ← captured here
```

After the first message, `session.session_id` is populated and all subsequent messages will use it.

### 3.2 Continuing a Session

```
User sends next message
    └─> _process_stream
            └─> agent.run_stream(prompt, session_id=session.session_id, ...)
                    └─> gemini -r <session_id> -p "prompt" --output-format stream-json
                            └─> Gemini CLI resumes the existing session
                            └─> Full conversation context is available to the model
```

### 3.3 Named Sessions

Users can name a session via `/name <name>`. The name is stored in `session.custom_names[session_id]` and displayed in `/list` instead of the auto-generated title.

If a user runs `/new [name]` before any message is sent, `pending_name` is set. When the `init` event arrives, the name is applied:

```python
# bot.py:182-184
if session.pending_name and event.session_id:
    session.custom_names[event.session_id] = session.pending_name
    session.pending_name = None
```

### 3.4 Deleting a Session

```
User runs /delete <index|id>
    └─> agent.delete_session(target_id)
            └─> gemini --delete-session <id>
    └─> If target_id == session.session_id: session.session_id = None
    └─> Remove from session.custom_names
```

After deletion, the next message creates a brand new session.

## 4. Command Reference

| Command | Effect on `session_id` | Effect on other fields |
|---|---|---|
| `/new [name]` | Sets `session_id = None` | Sets `pending_name` |
| `/resume <id\|index>` | Sets `session_id = target_id` | Clears `pending_name` |
| `/resume` (no args) | Sets `session_id = "latest"` | Clears `pending_name` |
| `/delete <id\|index>` | Clears `session_id` if matches | Removes from `custom_names` |
| `/name <name>` | None (requires active session) | Sets `custom_names[session_id]` |
| `/model <name>` | None | Sets `session.model` |
| `/mode <mode>` | None | Sets `session.approval_mode` |
| `/compress` | Uses current `session_id` | Sends `/compress` as prompt |
| Any other `/` command | Uses current `session_id` | Forwards raw text to Gemini |

## 5. Concurrency Control

Each `UserSession` has an `asyncio.Lock`:

```python
async with session.lock:
    await _process_stream(message, session, agent)
```

This ensures that a user cannot send a second message while their first is still streaming. Without this lock, multiple concurrent `run_stream` calls would interleave `session_id` updates and corrupt the state.

The lock is **per-user**, not global. Different users can process messages concurrently.

## 6. Message Flow (Full Pipeline)

```
Telegram message
    │
    ├─ SessionManager.get(user_id) → UserSession
    │       └─ (creates UserSession if first time, with session_id=None)
    │
    ├─ async with session.lock:   ← blocks concurrent messages from same user
    │
    ├─ message.answer("Thinking...")
    │
    ├─ agent.run_stream(prompt, session_id, model, approval_mode)
    │       ├─ Builds CLI args: gemini -p <prompt> -r <session_id> ...
    │       ├─ asyncio.create_subprocess_exec → non-blocking
    │       └─ Yields GeminiEvent objects parsed from NDJSON stdout
    │
    ├─ for event in stream: _handle_event(event, session, state, reply)
    │       ├─ InitEvent  → capture session_id, model
    │       ├─ MessageEvent → accumulate text, throttle-edit Telegram message
    │       ├─ ToolUseEvent → send tool display message to Telegram
    │       ├─ ToolResultEvent → edit tool message with ✅/❌
    │       ├─ ErrorEvent → edit reply with error, set aborted=True
    │       └─ ResultEvent → extract stats (tokens, duration)
    │
    ├─ Final UI update
    │       ├─ If tools used: delete "Thinking...", send final response as new message
    │       └─ If no tools: edit "Thinking..." in place
    │
    └─ Release lock
```

## 7. Throttling

During streaming, Telegram edits are throttled to avoid rate limits:

- **Time-based**: minimum `UPDATE_INTERVAL = 1.5` seconds between edits
- **Content-based**: minimum `UPDATE_CHAR_THRESHOLD = 200` characters added

An edit only fires when **both** conditions are met. This prevents excessive API calls during fast token generation.

## 8. Configuration vs. Runtime State

| Field | Config (`config.toml`) | Runtime override |
|---|---|---|
| Model | `gemini.model` | `session.model` |
| Approval mode | `gemini.approval_mode` | `session.approval_mode` |
| Working directory | `gemini.working_dir` | None |
| Allowed users | `telegram.allowed_user_ids` | N/A |

Runtime overrides take precedence. If `session.model` is `None`, the config default is passed to the CLI.

## 9. Limitations and Future Work

### 9.1 In-Memory Only

Session state (`_sessions` dict) is lost on restart. A future improvement could persist sessions to disk or Redis.

### 9.2 No Cross-Device Continuity

A session is tied to a Telegram user ID. If the same user connects from multiple devices, they share the session — but there is no mechanism to resume a session from a different user account.

### 9.3 `latest` String as Session ID

When `/resume` is called with no argument, `session.session_id` is set to the string `"latest"`. This is a special value that Gemini CLI interprets as "use the most recent session". The `SessionInfo` objects fetched by `/list` contain real UUIDs, so `session.last_sessions` is used to resolve index arguments.

### 9.4 Potential Race on First Message

On the very first message from a user, `session.session_id` is `None`. Two concurrent messages from the same user would both invoke `gemini` without `-r`, potentially creating **two separate sessions**. The `session.lock` (acquired before `_process_stream`) prevents this by serializing messages from the same user.

## 10. Relevant Files

| File | Responsibility |
|---|---|
| `src/tg_gemini/gemini.py` | Subprocess execution, CLI argument building, `list_sessions`, `delete_session` |
| `src/tg_gemini/bot.py` | `UserSession`, `SessionManager`, all command handlers, `_process_stream`, event dispatch |
| `src/tg_gemini/events.py` | Pydantic event models including `InitEvent` with `session_id` field |
| `src/tg_gemini/config.py` | `GeminiConfig` with `model`, `approval_mode`, `working_dir` |
