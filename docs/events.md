# Internal Event Protocol

`tg-gemini` parses the NDJSON output from the Gemini CLI's `stream-json` mode into typed Pydantic models. This ensures high reliability and type safety when processing agent responses and tool usage.

## Event Types

All events are defined in `src/tg_gemini/events.py`.

### 1. `init` (`InitEvent`)
Emitted at the start of a session. Contains the resolved session ID and model.
- `session_id`: (string) The unique ID for the conversation.
- `model`: (string) The actual model name being used.

### 2. `message` (`MessageEvent`)
Emitted when the user or assistant sends a text chunk.
- `role`: (`user` | `assistant`) The sender's role.
- `content`: (string) The text content.
- `delta`: (boolean) If true, this is a stream chunk.

### 3. `tool_use` (`ToolUseEvent`)
Emitted when the agent decides to invoke a tool.
- `tool_name`: (string) Name of the tool (e.g., `bash`, `read_file`, `mcp_...`).
- `tool_id`: (string) Unique ID for the tool call.
- `parameters`: (dict) Arguments passed to the tool.

### 4. `tool_result` (`ToolResultEvent`)
Emitted after a tool execution completes.
- `tool_id`: (string) Corresponds to the `tool_id` from `tool_use`.
- `status`: (`success` | `error`) Execution status.
- `output`: (string, optional) Result of the tool.
- `error`: (dict, optional) Error details if failed.

### 5. `error` (`ErrorEvent`)
Emitted for system errors or warnings.
- `severity`: (`error` | `warning`)
- `message`: (string) The error description.

### 6. `result` (`ResultEvent`)
The final event in a stream, summarizing the outcome and usage.
- `status`: (`success` | `error`)
- `stats`: (dict) Token usage and timing statistics.

## Parsing Logic

`GeminiSession._read_loop()` in `src/tg_gemini/gemini.py` reads the subprocess `stdout` line-by-line. Each line is parsed via `_parse_line()` which extracts JSON objects and feeds them into `_handle_event()` for type dispatch. `_handle_event()` maps the raw JSON event type to the corresponding typed `Event` model via `parse_event()` from `events.py`. Lines that are not valid JSON or do not match a known event type are logged but ignored.

The `GeminiAgent.run_stream()` method wraps a `GeminiSession` and yields events with stop/interrupt support via an `asyncio.Event`.
