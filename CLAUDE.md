# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`tg-gemini` is a Python middleware service that bridges Telegram bot interface with Google Gemini CLI headless mode. It runs on a VPS, receives Telegram messages/commands, forwards them to `gemini -p` (headless), processes the stream-JSON output, converts Obsidian Markdown to Telegram-compatible format, and returns responses. It is intentionally minimal: single platform (Telegram), single agent (Gemini CLI).

## Development Commands

All via `bash dev.sh <command>` (requires `uv` and tools in PATH):

```bash
bash dev.sh format          # ruff check --fix + ruff format
bash dev.sh lint            # mypy src + ruff check + ruff format --check
bash dev.sh test            # coverage run pytest + coverage report + coverage html
bash dev.sh test -k foo     # run single test matching "foo"
bash dev.sh check           # full pipeline: format → lint → test → pre-commit
bash dev.sh bump            # git-cliff changelog + bump-my-version patch + push tags
bash dev.sh docs dev        # mkdocs serve (local preview)
```

Install dependencies: `uv sync --all-groups`

## Code Quality Requirements

- **100% test coverage** required (`fail_under = 100` in pyproject.toml)
- **MyPy strict mode** — all code must be fully typed
- **Ruff** enforces E, W, F, I, B, C4, UP, ARG001; line length is not enforced (E501 ignored)
- All warnings treated as errors in pytest (`filterwarnings = ["error"]`)
- Conventional commits required for changelog: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`, etc.

## Architecture & Implementation Plan

The actual Telegram↔Gemini middleware is **not yet implemented**. The `src/tg_gemini/` currently contains boilerplate. Implementation should follow this architecture:

### Core Components

1. **CLI entrypoint** (`src/tg_gemini/__main__.py` or `main.py`)
   - Use `typer` or `click` for CLI; entry point `tg-gemini` is defined in pyproject.toml
   - Commands: `start`, `stop`, `status`, `upgrade`

2. **Config** (`src/tg_gemini/config.py`)
   - TOML-based config (use `tomllib` stdlib or `tomli` backport)
   - Fields: `telegram.bot_token`, `telegram.allowed_user_ids`, `gemini.model`, `gemini.approval_mode`, `gemini.working_dir`

3. **Gemini wrapper** (`src/tg_gemini/gemini.py`)
   - Invoke: `gemini -p "<prompt>" --output-format stream-json`
   - Parse newline-delimited JSONL events: `init`, `message`, `tool_use`, `tool_result`, `error`, `result`
   - Stream assistant message chunks to Telegram as they arrive
   - Handle exit codes: 0 (success), 1 (error), 42 (invalid input), 53 (turn limit)
   - Session resume: `gemini -r latest -p "<prompt>" --output-format stream-json`

4. **Markdown converter** (`src/tg_gemini/markdown.py`)
   - Convert Obsidian/standard Markdown → Telegram MarkdownV2 or HTML parse mode
   - Key transforms: `**bold**`, `*italic*`, `` `code` ``, fenced code blocks, `[[wikilinks]]` → plain text, `> blockquotes`
   - Escape Telegram special chars: `_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`

5. **Telegram bot** (`src/tg_gemini/bot.py`)
   - Use `python-telegram-bot` (async)
   - Slash commands: `/start`, `/stop`, `/status`, `/new` (new session), `/resume` (resume latest session), `/model <name>` (switch model)
   - Filter by `allowed_user_ids` for security
   - Stream responses using `message.edit_text()` with incremental updates

### Key Technical Decisions

- **Async**: Use `asyncio` + `asyncio.create_subprocess_exec` for non-blocking Gemini subprocess calls
- **Stream processing**: Read JSONL line-by-line from subprocess stdout, accumulate `message` chunks, send partial updates to Telegram every N chars or on sentence boundaries
- **Telegram parse mode**: Use `HTML` parse mode (more forgiving than MarkdownV2 for escaping)
- **Config location**: `~/.config/tg-gemini/config.toml` (XDG), or path passed via `--config` flag

## Package Structure

```
src/tg_gemini/
├── __init__.py      # version + main() entry point
├── config.py        # TOML config loading/validation (dataclasses or pydantic)
├── gemini.py        # subprocess wrapper, stream-JSON parsing
├── markdown.py      # Obsidian MD → Telegram HTML conversion
├── bot.py           # python-telegram-bot handlers
└── cli.py           # typer/click CLI (start/stop/status/upgrade)
tests/
├── test_config.py
├── test_gemini.py   # mock subprocess output with sample JSONL fixtures
├── test_markdown.py # conversion edge cases
└── test_bot.py      # handler logic (mock telegram objects)
```
