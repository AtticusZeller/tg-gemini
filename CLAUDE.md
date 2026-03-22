# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`tg-gemini` is a Python middleware service bridging Telegram bot interface with Google Gemini CLI headless mode. It receives Telegram messages/commands, forwards them to `gemini -p --output-format stream-json`, streams JSONL events back to Telegram as they arrive, and converts Markdown to Telegram HTML. Single platform (Telegram), single agent (Gemini CLI).

## Development Commands

All via `bash dev.sh <command>` (requires `uv` in PATH):

```bash
bash dev.sh format          # ruff check --fix + ruff format
bash dev.sh lint            # ty check + ruff check + ruff format --check
bash dev.sh test            # coverage run pytest + coverage report + coverage html
bash dev.sh test -k foo     # run single test matching "foo"
bash dev.sh check           # full pipeline: format → lint → test → pre-commit
bash dev.sh bump            # git-cliff changelog + bump-my-version patch + push tags
```

Install dependencies: `uv sync --all-groups`

## Modern Python Tooling

This project follows the [Trail of Bits modern Python](https://github.com/trailofbits/cookiecutter-python) conventions. All tooling runs via `uv run`.

### Tool Stack

| Tool | Purpose | Replaces |
|------|---------|----------|
| **uv** | Package & env management | pip, virtualenv, pip-tools |
| **uv_build** | Build backend | hatchling, setuptools |
| **ruff** | Linting + formatting | flake8, black, isort, pyupgrade |
| **ty** | Type checking | mypy, pyright |
| **pytest + coverage** | Testing | unittest |

### Anti-Patterns (never do these)

| Avoid | Use Instead |
|-------|-------------|
| `pip install` / `pip uninstall` | `uv add` / `uv remove` |
| `source .venv/bin/activate` | `uv run <cmd>` |
| `hatchling` build backend | `uv_build` |
| `mypy` / `pyright` | `ty check src/` |
| `[project.optional-dependencies]` for dev | `[dependency-groups]` (PEP 735) |
| `from __future__ import annotations` | Native Python 3.12+ syntax |
| `from typing import List, Dict, Tuple` | `list`, `dict`, `tuple` builtins |
| `Optional[X]` | `X \| None` |
| `Union[X, Y]` | `X \| Y` |
| `TYPE_CHECKING` imports used in runtime annotations | Regular imports |

### Dependency Management

```bash
uv add <pkg>                  # add runtime dependency
uv add --group dev <pkg>      # add to dev group
uv add --group test <pkg>     # add to test group
uv remove <pkg>               # remove dependency
uv sync --all-groups          # install everything
```

Dependency groups in `pyproject.toml`:
- `lint` — `ty`, `ruff`
- `test` — `pytest`, `pytest-asyncio`, `coverage`
- `dev` — includes `lint` + `test` + release tools (via `include-group`)
- `docs` — mkdocs stack

### Type Annotations (Python 3.12+)

- No `from __future__ import annotations` — use native syntax
- Use `X | None` not `Optional[X]`; `X | Y` not `Union[X, Y]`
- Use `list[X]`, `dict[K, V]`, `tuple[X, ...]` builtins directly
- Use `Self` from `typing` for self-referential return types
- Keep `TYPE_CHECKING` only for types that are **never used at runtime** (e.g., abstract protocol stubs)

### Ruff Configuration

`select = ["ALL"]` with explicit per-rule ignores in `pyproject.toml`. Key ignores:

```
D, ANN          — docstrings/annotations not enforced
COM812, ISC001  — formatter conflicts
S101, S603, S607 — assert + subprocess use is intentional
INP001          — tests/ is a namespace package (expected)
RUF006          — fire-and-forget asyncio.create_task is intentional
ASYNC110        — sleep-in-while-loop for bot lifecycle polling
```

Run `uv run ruff check src/ tests/ --fix` then `uv run ruff format src/ tests/`.

### Version Management

Version is static in `pyproject.toml` (`version = "0.0.0"`). `__version__` in `__init__.py` reads it via `importlib.metadata.version("tg-gemini")`. Bumped via `bump-my-version` which updates both `pyproject.toml` and `CHANGELOG.md`.

## Code Quality Requirements

- **≥95% test coverage** (`fail_under = 95` in pyproject.toml)
- **ty** — all code must be fully typed (`uv run ty check src/`)
- **Ruff** `select = ["ALL"]` with explicit ignores; line length not enforced (E501 ignored)
- All warnings treated as errors in pytest (`filterwarnings = ["error"]`)
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`, etc.

## Architecture

### Component Overview

```
CLI (cli.py / typer)
  └── Engine (engine.py)               # orchestrates all components
        ├── TelegramPlatform            # polling, routing, sending
        │     └── markdown_to_html()   # Obsidian MD → Telegram HTML
        ├── GeminiAgent                 # factory for GeminiSession
        │     └── GeminiSession        # subprocess + JSONL stream parser
        ├── SessionManager              # per-user session state (JSON-persisted)
        ├── StreamPreview               # throttled streaming message edits
        ├── SkillRegistry               # loads SKILL.md from skill_dirs
        ├── CommandLoader               # loads .gemini/commands/*.toml
        └── I18n                        # EN/ZH translations
```

### Data Flow

1. `TelegramPlatform` receives a Telegram update → builds `Message` (with `ReplyContext`) → calls `Engine.handle_message()`
2. `Engine` checks for slash commands or routes to `_process()`, which locks the `Session`
3. `GeminiAgent.start_session()` returns a `GeminiSession`; `session.send()` spawns the subprocess and starts `_read_loop()` in a background task
4. `_read_loop()` reads JSONL lines from stdout → emits `Event` objects into `asyncio.Queue`
5. `Engine._run_gemini()` consumes events: `TEXT` → `StreamPreview.append_text()`, `TOOL_USE`/`TOOL_RESULT` → `platform.send()`, `RESULT` → `StreamPreview.finish()`
6. `StreamPreview` batches Telegram message edits (throttled by `interval_ms` / `min_delta_chars`)

### Key Design Decisions

- **Session key**: `"telegram:{chat_id}:{user_id}"` — one session per user per chat
- **Concurrency**: per-session `asyncio.Lock`; overflow queued up to `_MAX_QUEUE=5`
- **Parse mode**: Telegram `HTML` (more forgiving than MarkdownV2); fallback to plain text on `BadRequest`
- **Config**: `~/.tg-gemini/config.toml` (default), `config.toml` (local), or `--config` flag
- **`allow_from`**: `"*"` (open) or comma-separated Telegram user IDs
- **Gemini modes**: `default`, `auto_edit`, `yolo` (`-y`), `plan` — mapped to CLI flags in `GeminiSession`
- **Attachments**: images/files saved to `tempfile.gettempdir()` as `@file` references in prompt; cleaned up after subprocess exits
- **Skills**: Loaded from `<skill_dir>/<name>/SKILL.md` with YAML frontmatter; wrapped in a prompt that instructs the agent to execute the skill
- **Commands**: Loaded from `<work_dir>/.gemini/commands/*.toml`; support `{{args}}`, `@{filepath}`, `!{cmd}` syntax

### Config Schema (`config.toml`)

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

# Skill directories (optional)
[skills]
dirs = ["~/.tg-gemini/skills"]
```

### Slash Commands

| Command | Action |
|---|---|
| `/new` | Reset to a new Gemini session |
| `/model [name]` | List or switch model |
| `/mode [mode]` | List or switch approval mode |
| `/stop` | Notify stop (best-effort; no subprocess kill in v1) |
| `/help` | Show command list |
| `/commands reload` | Reload Commands and Skills, refresh Telegram menu |

**Command priority**: Built-in commands → Commands (`.gemini/commands/*.toml`) → Skills (`skill_dirs/*/SKILL.md`)

### JSONL Event Mapping

Gemini CLI emits these event types on stdout; `GeminiSession._handle_event()` maps them:

| Gemini type | `EventType` | Engine action |
|---|---|---|
| `init` | `TEXT` (with `session_id`) | Store `agent_session_id` for session resume |
| `message` role=user | ignored | User echo — skipped |
| `message` role=assistant, `delta:true` | `TEXT` | Accumulate + stream preview |
| `tool_use` | `TOOL_USE` | Freeze preview, send tool notification |
| `tool_result` | `TOOL_RESULT` | Send result notification |
| `error` | `ERROR` | Send error message |
| `result` | `RESULT` | Finalize preview or send full response |

Note: In stream-json mode, **all** assistant text arrives as `delta:true` messages — there are no non-delta assistant messages. The `_pending_msgs` buffer in `GeminiSession` handles the edge case of assistant messages without a `delta` field (flushed as `THINKING` before `tool_use`, as `TEXT` before `result`), but this path is not exercised in normal operation.

For complete stream-json event schemas, all built-in tool parameters, `ToolErrorType` enum, exit codes, and session/resume details, see [`docs/gemini-cli/stream-json.md`](docs/gemini-cli/stream-json.md).
