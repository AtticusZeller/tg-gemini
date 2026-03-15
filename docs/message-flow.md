# cc-connect Telegram Message Processing Flow

This document details the complete technical lifecycle of a message within **cc-connect**, tracing its path from a Telegram user to the AI agent and back.

## 1. Phase 1: Inbound (Telegram → Platform)

**Component:** `platform/telegram/telegram.go`

1.  **Polling:** The platform starts a background goroutine that calls Telegram's `getUpdates` API (via `updates := bot.GetUpdatesChan(u)`).
2.  **Update Reception:** When a user sends a message, Telegram returns an `Update` object.
3.  **Sanitization:**
    *   Checks if the message is too old (to avoid "replay" after a restart).
    *   Filters by `allow_from` (User ID whitelist).
    *   In groups, it checks if the bot was mentioned or if the message was a reply to the bot.
4.  **Transformation:** The raw Telegram message is converted into a `core.Message` struct.
    *   **SessionKey:** Created as `telegram:{chatID}:{userID}`. This ensures user-level context isolation.
    *   **Attachments:** Photos, voice notes, and documents are downloaded from Telegram servers and attached to the message object.
5.  **Dispatch:** Calls `p.handler(p, coreMsg)`, which is a reference to `Engine.handleMessage`.

## 2. Phase 2: Orchestration (Platform → Engine)

**Component:** `core/engine.go`

1.  **Pre-processing:**
    *   **Alias Resolution:** Checks if the message matches a shortcut (e.g., "帮助" -> "/help").
    *   **Rate Limiting:** Ensures the user hasn't exceeded the message quota.
    *   **Banned Words:** Scans for restricted content.
2.  **Command Handling:** If the message starts with `/`, it is diverted to internal command logic (e.g., `/new`, `/switch`).
3.  **Session Locking:**
    *   Retrieves or creates a `Session` object.
    *   **TryLock:** Uses a mutex to ensure that if a user sends a second message while the first is still "thinking," the second is rejected with a "Previous message still processing" warning.
4.  **Interactive State:** Retrieves the `interactiveState` for the `SessionKey`. If no agent process is running for this user, it triggers `Agent.StartSession`.

## 3. Phase 3: Execution (Engine → Agent)

**Component:** `agent/gemini/session.go` (Example: Gemini)

1.  **Execution:** The engine calls `AgentSession.Send()`.
2.  **CLI Invocation:** The agent launches the `gemini` CLI as a subprocess:
    ```bash
    gemini --output-format stream-json --resume <id> -p "<user_text>"
    ```
3.  **Real-time Streaming:** 
    *   A background `readLoop` reads the CLI's `stdout`.
    *   The CLI outputs a stream of JSON events (e.g., `{"type": "message", "content": "..."}`).
    *   These are parsed and sent into the `Events()` channel as `core.Event` objects.

## 4. Phase 4: Feedback Loop (Agent → Engine → Platform)

**Component:** `core/engine.go` (`processInteractiveEvents`)

This is a loop that listens to the agent's event channel and reacts in real-time:

1.  **`EventThinking`:** Triggers a "Thinking..." status message or a typing indicator in Telegram.
2.  **`EventText` (Deltas):** 
    *   `cc-connect` accumulates these text fragments.
    *   **Streaming UI:** If configured, it periodically calls `Platform.UpdateMessage()` to edit the same Telegram message, creating a "live typing" effect.
3.  **`EventToolUse`:** Sends a specific message to Telegram indicating which tool (e.g., `bash`, `read_file`) the agent is invoking.
4.  **`EventPermissionRequest`:** 
    *   The loop **pauses**.
    *   Sends a Telegram message with **Inline Buttons** (Allow/Deny).
    *   Waits for the user to click a button before resuming the CLI interaction.
5.  **`EventResult`:** 
    *   The final response is complete.
    *   The engine saves the turn to the local `history.json`.
    *   The final text is sent to Telegram as a standard message.
    *   **Session Unlock:** The session mutex is released, allowing the next message.

---
**Key Files:**
- `platform/telegram/telegram.go`: Boundary with Telegram API.
- `core/engine.go`: The brain handling state, concurrency, and routing.
- `agent/gemini/session.go`: Boundary with the AI CLI process.
