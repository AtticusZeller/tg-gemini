# Stream JSON Output Specification

The `stream-json` output format (enabled via `--output-format stream-json`) provides a real-time, machine-readable stream of events from the Gemini CLI. The output is formatted as **Newline Delimited JSON (NDJSON)**, where each line is a valid JSON object representing a single event.

## Reference Source Code

This specification is based on the following files in the `gemini-cli` repository:
- `packages/core/src/output/types.ts`: Event interfaces, enums, and `StreamStats` definitions.
- `packages/core/src/output/stream-json-formatter.ts`: Logic for formatting events and converting metrics.
- `packages/core/src/tools/definitions/base-declarations.ts`: Canonical string names for core tools and their parameter keys.
- `packages/core/src/tools/mcp-tool.ts`: MCP tool naming conventions (`mcp_` prefix).

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

**Example:**
```json
{"type":"init","timestamp":"2026-03-15T10:00:00.000Z","session_id":"abc-123","model":"gemini-2.5-pro"}
```

### 2. `message`
Emitted when the assistant or user sends a message.

| Field     | Type                      | Description                                                     |
| --------- | ------------------------- | --------------------------------------------------------------- |
| `role`    | `"user"` \| `"assistant"` | The role of the message sender.                                 |
| `content` | string                    | The text content of the message.                                |
| `delta`   | boolean                   | (Optional) If `true`, the content is a chunk of a larger stream. |

**Example:**
```json
{"type":"message","timestamp":"2026-03-15T10:00:01.000Z","role":"assistant","content":"Hello! How can I help you today?"}
```

### 3. `tool_use`
Emitted when the assistant decides to call a tool.

| Field        | Type   | Description                                                                                                                                                                                                                                                                                                  |
| ------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tool_name`  | string | The name of the tool being called. See [Tool Names](#tool-names) for possible values.                                                                                                                                                                                                                        |
| `tool_id`    | string | A unique identifier for this specific tool call (e.g., `call_asdf123`). Used to correlate with `tool_result`.                                                                                                                                                                                                |
| `parameters` | object | The arguments passed to the tool as a key-value map (`Record<string, unknown>`). The keys depend on the `tool_name`. For example, `read_file` uses `file_path` (string), `start_line` (number), and `end_line` (number). |

**Example:**
```json
{"type":"tool_use","timestamp":"2026-03-15T10:00:02.000Z","tool_name":"read_file","tool_id":"call_456","parameters":{"file_path":"README.md","start_line":1,"end_line":10}}
```

### 4. `tool_result`
Emitted after a tool has finished executing.

| Field     | Type                  | Description                                                |
| --------- | --------------------- | ---------------------------------------------------------- |
| `tool_id` | string                | Matches the `tool_id` from the corresponding `tool_use`.   |
| `status`  | `"success"` \| `"error"` | Whether the tool execution was successful.                  |
| `output`  | string                | (Optional) The output of the tool if successful.           |
| `error`   | object                | (Optional) Error details if the tool failed.                |

**`error` object structure:**
- `type`: string (e.g., `"RuntimeError"`, `"AbortError"`, `"MCP_TOOL_ERROR"`)
- `message`: string

**Example:**
```json
{"type":"tool_result","timestamp":"2026-03-15T10:00:03.000Z","tool_id":"call_456","status":"success","output":"# Project README..."}
```

### 5. `error`
Emitted when a system-level error or warning occurs.

| Field      | Type                   | Description                      |
| ---------- | ---------------------- | -------------------------------- |
| `severity` | `"warning"` \| `"error"` | The severity level of the error. |
| `message`  | string                 | The error message.               |

**Example:**
```json
{"type":"error","timestamp":"2026-03-15T10:00:04.000Z","severity":"error","message":"Failed to connect to MCP server."}
```

### 6. `result`
Emitted at the end of a prompt execution.

| Field    | Type                  | Description                                   |
| -------- | --------------------- | --------------------------------------------- |
| `status` | `"success"` \| `"error"` | The final status of the operation.            |
| `error`  | object                | (Optional) Final error details if applicable. |
| `stats`  | object                | (Optional) Token usage and timing statistics.  |

**`stats` object structure:**

| Field          | Type   | Description                                     |
| -------------- | ------ | ----------------------------------------------- |
| `total_tokens` | number | Total tokens used across all models.            |
| `input_tokens` | number | Total input (prompt) tokens used.               |
| `output_tokens`| number | Total output (candidate) tokens used.           |
| `cached`       | number | Tokens served from cache.                       |
| `input`        | number | Raw input tokens (excluding cache).             |
| `duration_ms`  | number | Execution duration in milliseconds.             |
| `tool_calls`   | number | Total number of tool calls made.                |
| `models`       | object | Per-model breakdown (`Record<string, ModelStats>`).|

**`ModelStats` object structure:**
- `total_tokens`: number
- `input_tokens`: number
- `output_tokens`: number
- `cached`: number
- `input`: number

**Example:**
```json
{"type":"result","timestamp":"2026-03-15T10:00:05.000Z","status":"success","stats":{"total_tokens":120,"input_tokens":100,"output_tokens":20,"cached":0,"input":100,"duration_ms":1500,"tool_calls":1,"models":{"gemini-2.5-pro":{"total_tokens":120,"input_tokens":100,"output_tokens":20,"cached":0,"input":100}}}}
```

---

## Tool Names

The `tool_name` field in `tool_use` events can contain several types of names:

### Core Tools
These are built-in tools provided by Gemini CLI.
- `glob`: Search for files matching a pattern.
- `grep_search`: Search for text patterns within files.
- `list_directory`: List contents of a directory.
- `read_file`: Read the content of a single file.
- `write_file`: Create or overwrite a file.
- `replace`: Surgical text replacement in a file.
- `run_shell_command`: Execute shell commands.
- `google_web_search`: Perform a Google search.
- `web_fetch`: Fetch content from a URL.
- `save_memory`: Persist facts across sessions.
- `ask_user`: Request input from the user.
- `enter_plan_mode` / `exit_plan_mode`: Manage complex task planning.
- `activate_skill`: Enable specialized agent skills.

### MCP Tools
Tools discovered via Model Context Protocol (MCP) servers follow a specific naming convention:
- **Format**: `mcp_{server_name}_{tool_name}`
- **Example**: `mcp_github_create_pull_request`

All MCP tool names start with the `mcp_` prefix.
