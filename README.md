# tg-gemini

Lightweight Telegram-Gemini CLI middleware. Receive Telegram messages, forward them to `gemini` CLI in headless `stream-json` mode, and stream responses back with rich HTML formatting.

## 🚀 Features

- **Pure Async Architecture:** Built with `aiogram 3.x` and `asyncio` for high performance.
- **Direct CLI Integration:** No complex abstractions; it wraps the [Gemini CLI](https://github.com/google-gemini/gemini-cli) directly using its headless mode.
- **Streaming Responses:** Real-time updates in Telegram as Gemini thinks and acts.
- **Smart Markdown-to-HTML:** Surgical conversion of Markdown/Obsidian syntax to Telegram-compatible HTML.
- **Session Persistence:** Native Gemini CLI session resumption support.
- **Modern Tooling:** Managed by `uv`, strictly typed with `ty`, and linted with `ruff`.

## 🛠️ Prerequisites

- **Python:** >= 3.11
- **uv:** [Package manager](https://github.com/astral-sh/uv)
- **Gemini CLI:** Installed and available in your `PATH`
- **Telegram Bot Token:** From [@BotFather](https://t.me/BotFather)

## 📦 Installation

```bash
git clone https://github.com/atticuszeller/tg-gemini.git
cd tg-gemini
uv sync --all-groups
```

## ⚙️ Configuration

Create a config file at `config.toml`:

```toml
[telegram]
bot_token = "123456:ABC-DEF..."
allowed_user_ids = [123456789]  # Optional: whitelist of user IDs

[gemini]
model = "auto"             # auto | pro | flash | flash-lite | concrete-name
approval_mode = "default"  # default | auto_edit | yolo
working_dir = "."          # Directory where Gemini CLI executes
```

## 📖 Documentation

- [**Architecture**](docs/architecture.md): System design and component layers.
- [**Command Mapping**](docs/commands.md): Telegram commands and Gemini CLI flags.
- [**Format Conversion**](docs/formatting.md): Markdown-to-HTML strategy.
- [**Development Guide**](docs/development.md): Tech stack, testing, and quality standards.

## 🧪 Development

All development workflows are managed via `dev.sh`:

```bash
bash dev.sh format    # Format code with Ruff
bash dev.sh lint      # Type check (ty) and Lint (Ruff)
bash dev.sh test      # Run tests with 100% coverage enforcement
bash dev.sh check     # Full pre-commit pipeline
```

## 📄 License

MIT © [A.J.Zeller](https://github.com/atticuszeller)
