# Stream JSON Output Specification

The `stream-json` output format (enabled via `--output-format stream-json`) provides a real-time, machine-readable stream of events from the Gemini CLI. The output is formatted as **Newline Delimited JSON (NDJSON)**, where each line is a valid JSON object representing a single event.

## Reference Source Code

This specification is based on the following files in the `gemini-cli` repository:
- `packages/core/src/output/types.ts`: Event interfaces, enums, and `StreamStats` definitions.
- `packages/core/src/output/stream-json-formatter.ts`: Logic for formatting events and converting metrics.
- `packages/core/src/tools/definitions/base-declarations.ts`: Canonical string names for core tools and their parameter keys.
- `packages/core/src/tools/mcp-tool.ts`: MCP tool naming conventions (`mcp_` prefix).

---

## Typical Stream Sequence

When running a command like `gemini -p "Your prompt" --output-format stream-json`, the typical sequence of events is as follows:

1.  **`init`**: Emitted once at the very beginning to provide session and model metadata.
2.  **`message` (role: "user")**: Emitted once representing the initial prompt.
3.  **Iteration (one or more turns)**:
    -   **`message` (role: "assistant", delta: true)**: Multiple events as the model streams its text response.
    -   **`tool_use`**: If the model decides to use a tool, this event describes the tool and parameters.
    -   **`tool_result`**: Emitted after the tool execution completes, correlating via `tool_id`.
    -   *If tools were used, the loop repeats for the next model turn.*
4.  **`result`**: Emitted once at the very end, containing final status and aggregated usage statistics.

---

## Base Event Structure

Every event in the stream follows this base structure:

| Field       | Type   | Description                                   |
| ----------- | ------ | --------------------------------------------- |
| `type`      | string | The type of the event (see [Event Types](#event-types)). |
| `timestamp` | string | ISO 8601 timestamp of when the event occurred. |

---

## Event Types

### 1. `init`
Emitted at the start of a session.

| Field        | Type   | Description                               |
| ------------ | ------ | ----------------------------------------- |
| `session_id` | string | Unique identifier for the current session. |
| `model`      | string | The name of the model being used.         |

### 2. `message`
Emitted when the assistant or user sends a message.

| Field     | Type                      | Description                                                     |
| --------- | ------------------------- | --------------------------------------------------------------- |
| `role`    | `"user"` \| `"assistant"` | The role of the message sender.                                 |
| `content` | string                    | The text content of the message.                                |
| `delta`   | boolean                   | (Optional) If `true`, the content is a chunk of a larger stream. |

### 3. `tool_use`
Emitted when the assistant decides to call a tool.

| Field        | Type   | Description                                                                                             |
| ------------ | ------ | ------------------------------------------------------------------------------------------------------- |
| `tool_name`  | string | The name of the tool being called. See [Tool Names](#tool-names) for possible values.                    |
| `tool_id`    | string | A unique identifier for this specific tool call. Used to correlate with `tool_result`.                  |
| `parameters` | object | The arguments passed to the tool. See [Core Tool Parameter Reference](#core-tool-parameter-reference). |

### 4. `tool_result`
Emitted after a tool has finished executing.

| Field     | Type                  | Description                                              |
| --------- | --------------------- | -------------------------------------------------------- |
| `tool_id` | string                | Matches the `tool_id` from the corresponding `tool_use`. |
| `status`  | `"success"` \| `"error"` | Whether the tool execution was successful.              |
| `output`  | string                | (Optional) The output of the tool if successful.         |
| `error`   | object                | (Optional) Error details if the tool failed.              |

### 5. `error`
Emitted when a system-level error or warning occurs.

| Field      | Type                   | Description                      |
| ---------- | ---------------------- | -------------------------------- |
| `severity` | `"warning"` \| `"error"` | The severity level of the error. |
| `message`  | string                 | The error message.               |

### 6. `result`
Emitted at the end of a prompt execution.

| Field    | Type                  | Description                                   |
| -------- | --------------------- | --------------------------------------------- |
| `status` | `"success"` \| `"error"` | The final status of the operation.            |
| `error`  | object                | (Optional) Final error details if applicable. |
| `stats`  | object                | (Optional) Token usage and timing statistics.  |

---

## Tool Names

### Core Tools
- `glob`
- `grep_search`
- `list_directory`
- `read_file`
- `write_file`
- `replace`
- `run_shell_command`
- `google_web_search`
- `web_fetch`
- `save_memory`
- `ask_user`
- `enter_plan_mode`
- `exit_plan_mode`
- `activate_skill`

### MCP Tools
Format: `mcp_{server_name}_{tool_name}` (e.g., `mcp_github_create_pull_request`).

---

## Core Tool Parameter Reference

This section defines the parameter schema for each core tool emitted in `tool_use` events.

### `read_file`
Reads the content of a single file.
- `file_path` (string, required): Path to the file.
- `start_line` (number): 1-based start line.
- `end_line` (number): 1-based end line (inclusive).

### `write_file`
Creates or overwrites a file.
- `file_path` (string, required): Path to the file.
- `content` (string, required): Complete literal content to write.

### `grep_search`
Search for patterns within file contents.
- `pattern` (string, required): Regex or literal pattern.
- `dir_path` (string): Directory or file to search.
- `include_pattern` (string): Glob to filter files (e.g., `*.ts`).
- `exclude_pattern` (string): Regex to exclude matches.
- `names_only` (boolean): If true, only return file paths.
- `case_sensitive` (boolean): Case-sensitive search.
- `fixed_strings` (boolean): Treat pattern as literal string.
- `context` (number): Number of context lines.
- `after` (number): Lines after match.
- `before` (number): Lines before match.
- `no_ignore` (boolean): Ignore `.gitignore`.
- `max_matches_per_file` (number): Limit matches per file.
- `total_max_matches` (number): Overall limit (default 100).

### `glob`
Find files matching glob patterns.
- `pattern` (string, required): Glob pattern (e.g., `src/**/*.ts`).
- `dir_path` (string): Directory to search within.
- `case_sensitive` (boolean): Case-sensitive matching.
- `respect_git_ignore` (boolean): Follow `.gitignore`.
- `respect_gemini_ignore` (boolean): Follow `.geminiignore`.

### `list_directory`
List contents of a directory.
- `dir_path` (string, required): Path to list.
- `ignore` (array of strings): Glob patterns to ignore.
- `file_filtering_options` (object):
    - `respect_git_ignore` (boolean)
    - `respect_gemini_ignore` (boolean)

### `replace`
Surgical text replacement.
- `file_path` (string, required): Path to the file.
- `instruction` (string, required): Semantic explanation of the change.
- `old_string` (string, required): Exact literal text to find.
- `new_string` (string, required): Exact literal replacement.
- `allow_multiple` (boolean): Replace all occurrences.

### `run_shell_command`
Execute shell commands.
- `command` (string, required): Exact bash or powershell command.
- `description` (string): Concise summary for the user.
- `dir_path` (string): Execution directory.
- `is_background` (boolean): Run in background.

### `google_web_search`
- `query` (string, required): Search query.

### `web_fetch`
- `prompt` (string, required): Prompt containing up to 20 URLs and processing instructions.

### `save_memory`
- `fact` (string, required): Global preference or fact to persist.

### `ask_user`
- `questions` (array, required): 1-4 question objects.
    - `question` (string, required): Full question text.
    - `header` (string, required): Short tag (e.g., "Auth").
    - `type` (string, required): `"choice"`, `"text"`, or `"yesno"`.
    - `options` (array): For `"choice"` type.
        - `label` (string, required): Option display text.
        - `description` (string, required): Option explanation.
    - `multiSelect` (boolean): For `"choice"` type.
    - `placeholder` (string): Input hint.

### `enter_plan_mode`
- `reason` (string): Explanation for entering plan mode.

### `exit_plan_mode`
- `plan_path` (string, required): Path to the finalized plan file.

### `activate_skill`
- `name` (string, required): Name of the specialized skill to activate.
