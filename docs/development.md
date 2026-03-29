# Development Guide

This document covers the technology stack, development workflows, and quality standards for `tg-gemini`.

## 1. Technology Stack

- **Language:** Python 3.11+
- **Package Manager:** [uv](https://github.com/astral-sh/uv)
- **Frameworks:**
    - `aiogram 3.x`: Asynchronous Telegram Bot API.
    - `Typer`: Type-safe CLI command construction.
    - `Pydantic v2`: Data validation and settings management.
- **Tooling:**
    - `ruff`: Ultra-fast linting and formatting.
    - `ty`: Astral-native, high-performance type checking.
    - `pytest`: Testing framework with `pytest-asyncio`.
    - `coverage`: Test coverage reporting.

## 2. Development Workflow

### 2.1 Running the Bot
To start the bot during development:

```bash
# Using the default config path (~/.config/tg-gemini/config.toml)
uv run python -m tg_gemini.cli start

# Using a specific config file
uv run python -m tg_gemini.cli start --config my_config.toml
```

### 2.2 Helper Scripts
The project uses a unified `dev.sh` script to manage common tasks:

```bash
bash dev.sh format    # Run ruff formatter and fixer
bash dev.sh lint      # Run ty (type check) and ruff (lint check)
bash dev.sh test      # Run tests and generate coverage report
bash dev.sh check     # Run the full pre-commit pipeline (format, lint, test, hooks)
```

## 3. Quality Standards

### 3.1 Test Coverage
We enforce a minimum of 95% code coverage. Every new feature or bug fix must include corresponding tests.
- Verification: `fail_under = 95` in `pyproject.toml`.
- Execution: `bash dev.sh test`.

Tests are organized into two categories:
- **Unit tests** (`tests/test_*.py`): Test individual functions and classes in isolation using mocks.
- **Integration tests** (`tests/test_integration.py` or `tests/integration/`): Test cross-module interactions and end-to-end flows.

### 3.2 Strict Typing
All code must be fully typed and pass `ty check`. Legacy `Union` and `Optional` types should be replaced with the modern `|` operator.

### 3.3 Linting & Formatting
- **Line Length:** Standard is 100 characters.
- **Rules:** We use the `ALL` rule set in `ruff` with specific ignores for documentation and trailing commas.
- **Automatic Fixes:** `ruff check --fix` should be used to resolve common linting issues.

## 4. Development Pipeline

Every code change follows this mandatory pipeline:

1. **Plan** — Analyze the requirement, read relevant source and docs, outline the approach. Get approval before coding.
2. **Code** — Implement the feature or fix, including both production code and tests.
3. **Format** — `bash dev.sh format` — auto-fix formatting and lint issues.
4. **Lint** — `bash dev.sh lint` — verify type checking and lint rules pass.
5. **Test** — `bash dev.sh test` — ensure coverage meets the 95% threshold.
    - **Single-file change**: Only run the matching test, e.g. `bash dev.sh test -k foo` for `tests/test_foo.py`.
    - **Cross-module change**: Run the full test suite.
    - **Integration tests**: End-to-end flows in `tests/test_integration.py` or `tests/integration/`.
6. **Update docs** — If changes affect architecture, commands, formatting logic, or public APIs, update `docs/`.
7. **Git commit** — Use conventional commit format (`feat:`, `fix:`, `refactor:`, etc.).

## 5. Contributing

1.  **Surgical Changes:** Keep PRs focused. Avoid unrelated refactoring.
2.  **Conventional Commits:** Use standard prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`.
3.  **Documentation:** Update the relevant files in the `docs/` directory if your changes affect the architecture, commands, or formatting logic.
4.  **Modern Python:** Follow the latest Python standards (no `from __future__ import annotations`, use modern type hints).
