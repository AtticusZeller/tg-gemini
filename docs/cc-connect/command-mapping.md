# cc-connect Telegram to Gemini Command Mapping

This document describes how Telegram interactions (slash commands and messages) map to the internal `cc-connect` engine and the underlying `gemini` CLI.

## 1. Built-in Slash Commands

When a user sends a `/` command in Telegram, `cc-connect` intercepts it before forwarding it to the agent.

| Telegram Command | Engine Method | Gemini CLI / Agent Action |
| :--- | :--- | :--- |
| `/new [name]` | `cmdNew` | Terminates the current process; next message starts a new one (without `--resume`). |
| `/list` | `cmdList` | Calls `Agent.ListSessions()`, which reads `~/.gemini/tmp/<slug>/chats/`. |
| `/switch <id>` | `cmdSwitch` | Terminates the current process; next message starts with `--resume <id>`. |
| `/name <name>` | `cmdName` | Updates the session metadata in `cc-connect`'s local session store. |
| `/current` | `cmdCurrent` | Returns the current active `SessionKey` and `AgentSessionID`. |
| `/model [name]` | `cmdModel` | Updates the `Agent.model` field. Next process launch will use `-m <name>`. |
| `/mode [mode]` | `cmdMode` | Maps to `--approval-mode`. (See Mode Mapping below). |
| `/memory` | `cmdMemory` | Reads/Writes `GEMINI.md` in the project root or home directory. |
| `/history` | `cmdHistory` | Retrieves the transcript from `cc-connect`'s local JSON history. |
| `/cron add ...` | `cmdCron` | Injects a task into the local `cron` scheduler. |
| `/quiet` | `cmdQuiet` | Toggles suppression of "Thinking..." and "Tool..." messages in Telegram. |

## 2. Message to CLI Mapping

Every non-command message in Telegram follows this transformation:

1.  **Telegram:** User sends "How many files are here?"
2.  **cc-connect (Engine):** 
    - Identifies `SessionKey`: `telegram:123456:789`
    - Retrieves stored `AgentSessionID` for this key (e.g., `abc-xyz`).
3.  **cc-connect (Agent):** Executes the following shell command:
    ```bash
    gemini --output-format stream-json --resume abc-xyz -p "How many files are here?"
    ```
4.  **CLI Output:** Gemini CLI performs tasks and streams JSON events back.

## 3. Permission Mode Mapping

The `/mode` command in `cc-connect` maps directly to the Gemini CLI's `--approval-mode` flag.

| cc-connect Mode | Gemini CLI Flag | Behavior |
| :--- | :--- | :--- |
| `default` | `--approval-mode default` | Telegram shows "Allow/Deny" buttons for every tool call. |
| `auto_edit` | `--approval-mode auto_edit` | Files are edited automatically; `shell` calls still ask for permission. |
| `yolo` | `--approval-mode yolo` | All tools (shell, read, write) execute without asking. |
| `plan` | `--approval-mode plan` | CLI runs in read-only mode, only proposing changes. |

## 4. Interactive Confirmations

When Gemini CLI needs permission (and is not in `yolo` mode), it emits an `EventPermissionRequest`.

- **cc-connect** translates this into a Telegram message with **Inline Buttons**.
- **User clicks "Allow":** `cc-connect` sends an internal "allow" signal back to the CLI process (if using a persistent process) or prepares the next CLI execution with pre-approved context.
- **Note:** For the `gemini` agent specifically, permissions are handled by the CLI's own approval loop. `cc-connect` facilitates the UI by intercepting these requests.

## 5. Tool-to-UI Mapping

When Gemini uses a tool, it is displayed in Telegram as follows:

| Tool Name | Display Format |
| :--- | :--- |
| `Bash` / `shell` | A code block with `bash` highlighting showing the command. |
| `WriteFile` | A summary: `🔧 Tool: WriteFile(path/to/file)`. |
| `ReadFile` | A summary: `🔧 Tool: ReadFile(path/to/file)`. |

## 6. Project-Specific Instructions (Memory)

The `/memory` command in Telegram allows viewing and editing the files that Gemini CLI uses for context.

- **Local:** `GEMINI.md` in the `work_dir`.
- **Global:** `~/.gemini/GEMINI.md`.

Editing these via `/memory` ensures that the next `gemini -p ...` call picks up the updated instructions.

---
**Source References:**
- `agent/gemini/gemini.go`: NormalizeMode and CommandDirs logic.
- `agent/gemini/session.go`: Send method and argument building.
- `core/engine.go`: Built-in command dispatch logic.
