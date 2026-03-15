# GEMINI.md

This file provides the foundational context and instructional mandates for working within the `tg-gemini` repository.

## Project Overview

`tg-gemini` is a lightweight Python middleware that bridges a Telegram bot interface with the Google Gemini CLI's headless mode. It allows users to interact with Gemini directly through Telegram, supporting streaming responses, tool-use status updates, and robust session management.

### Key Technologies
- **Language:** Python 3.11+ (Modern syntax enforced)
- **Package Management:** [uv](https://github.com/astral-sh/uv)
- **Telegram Framework:** [aiogram 3.x](https://github.com/aiogram/aiogram) (Pure Async)
- **CLI Framework:** [Typer](https://github.com/tiangolo/typer)
- **Data Validation:** [Pydantic v2](https://docs.pydantic.dev/) (For stream-json events)
- **Agent Integration:** Gemini CLI (Headless `stream-json` mode)
- **Quality Tools:** `ruff`, `ty (strict)`, `pytest` (100% coverage target)

## Architecture

The project follows a decoupled **Bridge Pattern**:

- `src/tg_gemini/platform/telegram`: `aiogram` routers and handlers for Telegram interactions.
- `src/tg_gemini/core/engine`: Core orchestration logic, including the throttled streaming loop.
- `src/tg_gemini/core/agent`: `GeminiAgent` class managing the `gemini` CLI subprocess.
- `src/tg_gemini/events`: Pydantic models for Gemini CLI `stream-json` events.
- `src/tg_gemini/core/markdown`: Surgical Markdown-to-HTML conversion.
- `src/tg_gemini/cli.py`: Typer-based CLI for service management.
- `src/tg_gemini/config.py`: TOML-based configuration loading.

## Documentation Reference

Detailed documentation is available in the `docs/` directory:
- [**Architecture**](docs/architecture.md): Detailed system design.
- [**Command Mapping**](docs/commands.md): How commands map to Gemini CLI.
- [**Format Conversion**](docs/formatting.md): Markdown-to-HTML logic.
- [**Development Guide**](docs/development.md): Development setup and standards.

## Development Workflow

Follow this iterative cycle for all changes:

1.  **Plan:** Define the implementation approach and testing strategy.
2.  **Act:** Apply targeted changes. Use `uv add` for dependencies. Use modern Python syntax (e.g., `|` for Union types).
3.  **Validate:** 
    - Run `bash dev.sh format` to ensure style consistency.
    - Run `bash dev.sh lint` to verify type safety via `ty`.
    - Run `bash dev.sh test` to ensure **100% code coverage** and no regressions.
    - Run `bash dev.sh check` for the final pre-commit verification.

## Code Quality Mandates

### Modern Python Standards
- **No `from __future__ import annotations`:** Use Python 3.11+ native type hinting.
- **Modern Type Hints:** Use `|` instead of `Union` or `Optional`. Use `list` and `dict` instead of `List` and `Dict`.
- **Annotated Options:** Use `Annotated` for all Typer command options.

### Technical Integrity
- **100% Test Coverage:** All changes MUST maintain 100% code coverage. This is strictly enforced.
- **Strict Typing:** All code MUST be fully typed and pass `ty check`.
- **Fail Fast:** Configuration and input validation should happen as early as possible.

### Contribution Guidelines
- **Conventional Commits:** Use standard prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`.
- **Surgical Updates:** When modifying `markdown.py`, protect code blocks via placeholders and preserve HTML escaping.
- **Session Continuity:** Always leverage Gemini's native `-r` flag. Support index-based session resolution.
