# Configuration Reference

`tg-gemini` is configured using a TOML file (default path: `~/.tg-gemini/config.toml`).

## Example Configuration

```toml
[telegram]
token = "BOT_TOKEN"
allow_from = "*"          # or "123456789,987654321"

[gemini]
work_dir = "."
model = ""                # e.g. "gemini-2.5-pro"
mode = "default"          # default | auto_edit | yolo | plan
cmd = "gemini"
api_key = ""
timeout_mins = 0

[log]
level = "INFO"

[display]
thinking_max_len = 300
tool_max_len = 500

[stream_preview]
enabled = true
interval_ms = 1500
min_delta_chars = 30
max_chars = 2000

[rate_limit]
max_messages = 0
window_secs = 60.0

[skills]
dirs = ["~/.tg-gemini/skills"]
```

## `[telegram]` Section

- **`token`** (Required): Your Telegram Bot API token from @BotFather.
- **`allow_from`** (Optional): `"*"` (open) or comma-separated Telegram user IDs. Defaults to `"*"`.
- **`group_reply_all`** (Optional): If `true`, the group chats the bot responds to all messages, not just @mentions/replies. Default: `false`.
- **`share_session_in_channel`** (Optional): If `true`, all users in a channel share one session. Default: `false`.

## `[gemini]` Section

- **`work_dir`** (Optional): Root directory for Gemini CLI workspace. Defaults to `"."`.
- **`model`** (Optional): Default model name (empty = use Gemini default).
- **`mode`** (Optional): Tool approval policy. One of `default`, `auto_edit`, `yolo`, `plan`. Defaults to `"default"`.
- **`cmd`** (Optional): Path to `gemini` binary. Defaults to `"gemini"`.
- **`api_key`** (Optional): Gemini API key. Defaults to `""`.
- **`timeout_mins`** (Optional): Subprocess timeout in minutes. `0` = no timeout. Default: `0`.

## `[log]` Section

- **`level`** (Optional): Log level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Defaults to `"INFO"`.

## `[display]` Section

- **`thinking_max_len`** (Optional): Max characters for thinking/tool display. Defaults to `300`.
- **`tool_max_len`** (Optional): Max characters for tool result display. Defaults to `500`.

## `[stream_preview]` Section

- **`enabled`** (Optional): Enable streaming preview. Defaults to `true`.
- **`interval_ms`** (Optional): Min interval between preview updates in ms. Defaults to `1500`.
- **`min_delta_chars`** (Optional): Min new characters to trigger an update. Defaults to `30`.
- **`max_chars`** (Optional): Max preview text length. `0` = no truncation. Defaults to `2000`.

## `[rate_limit]` Section

- **`max_messages`** (Optional): Max messages per window. `0` = disabled. Default: `0`.
- **`window_secs`** (Optional): Rate limit window in seconds. Defaults to `60.0`.

## `[skills]` Section

- **`dirs`** (Optional): Extra skill directories. Default auto-loads from `<work_dir>/.gemini/skills/`. Defaults to `[]`.
