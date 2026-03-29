# Configuration Reference

`tg-gemini` is configured using a TOML file (default path: `~/.config/tg-gemini/config.toml`).

## Example Configuration

```toml
[telegram]
bot_token = "your_bot_token_here"
allowed_user_ids = [123456789, 987654321]  # Optional whitelist

[gemini]
model = "pro"                              # Default model
approval_mode = "auto_edit"                # Default approval mode
working_dir = "/path/to/your/project"      # Gemini workspace
```

## `[telegram]` Section

- **`bot_token`** (Required): Your Telegram Bot API token from @BotFather.
- **`allowed_user_ids`** (Optional): A list of integer Telegram user IDs authorized to use the bot. If empty or omitted, anyone can use the bot (not recommended for production).

## `[gemini]` Section

- **`model`** (Optional): The default model to use for new sessions.
    - **Aliases:** `auto`, `pro`, `flash`, `flash-lite`.
    - **Full Names:** `gemini-3.1-pro-preview`, `gemini-2.5-pro`, etc.
- **`approval_mode`** (Optional): The default tool execution policy.
    - `default`: Always ask for permission for each tool.
    - `auto_edit`: Automatically approve file edits; ask for shell/MCP tools.
    - `yolo`: Automatically approve everything.
- **`working_dir`** (Optional): The root directory where the Gemini CLI will operate. Defaults to the current directory (`.`).

## Model Aliases

The following aliases are supported and resolve to the latest recommended models:

| Alias | Resolves To |
| :--- | :--- |
| `auto` | `gemini-2.5-pro` or `gemini-3.1-pro-preview` |
| `pro` | `gemini-2.5-pro` or `gemini-3.1-pro-preview` |
| `flash` | `gemini-2.5-flash` |
| `flash-lite` | `gemini-2.5-flash-lite` |
