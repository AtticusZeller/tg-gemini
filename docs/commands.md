# Command Mapping

This document describes how Telegram interactions (slash commands and messages) map to the internal engine and the underlying `gemini` CLI.

## 1. Slash Commands

When a user sends a `/` command in Telegram, `tg-gemini` intercepts it to manage the middleware state or adjust the flags passed to the next Gemini execution.

| Telegram Command | Action | Gemini CLI Equivalent |
| :--- | :--- | :--- |
| `/start` | Welcome message and command list. | - |
| `/new [name]` | Clears the current `session_id`. Optionally sets a pending name. | Next run skips the `-r` flag. |
| `/list` | Lists available sessions for the project. | `gemini --list-sessions` |
| `/switch <index\|id>` | Switches to a specific session. | Updates internal state; next run uses `-r <id>`. |
| `/name <name>` | Sets a custom name for the current session. | Stored in middleware memory; shown in `/list`. |
| `/resume [index\|id]` | Resumes a session. | If no arg, uses `-r latest`. If arg, same as `/switch`. |
| `/delete <index\|id>` | Deletes a session from disk. | `gemini --delete-session <id>` |
| `/model <name>` | Updates the model for the current user. | Next run uses `-m <name>`. |
| `/status` | Displays active model and session ID. | - |
| `/current` | Displays active model and session ID (HTML formatted). | - |

### 1.1 Index Resolution
For commands taking an `<index>`, the middleware resolves the index based on the most recent `/list` output for that user. If the argument is not a digit, it is treated as a literal `session_id`.

## 2. Message to CLI Mapping

Every non-command text message follows this transformation:

1.  **Authorization:** The `user_id` is checked against the whitelist.
2.  **Concurrency:** A lock is acquired for the user's session.
3.  **Command Construction:** The agent builds the shell command based on the user's state:
    ```bash
    gemini -p "<user_text>" --output-format stream-json -m <model> --approval-mode <mode> [-r <session_id>]
    ```
4.  **Execution:** The command is executed via `asyncio.create_subprocess_exec`.
5.  **Event Processing:**
    - `init`: Captures and stores the `session_id`.
    - `message`: Accumulates content and triggers throttled UI updates.
    - `tool_use`: Adds a status line (e.g., `🔧 bash`) to the UI.
    - `error`: Displays the error message and terminates the stream.
    - `result`: Finalizes the message formatting and completes the handler.

## 3. Tool Status Mapping

When Gemini uses a tool, it is displayed in Telegram as an incremental status line below the main response text:

| Tool Category | UI Display |
| :--- | :--- |
| Core Tools | `🔧 <tool_name>` (e.g., `🔧 read_file`) |
| MCP Tools | `🔧 mcp_<server>_<tool>` |

These status lines are automatically removed or replaced by the final formatted response once the execution is complete.
