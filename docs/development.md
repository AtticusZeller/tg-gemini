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

The project uses a unified `dev.sh` script to manage common tasks:

```bash
bash dev.sh format    # Run ruff formatter and fixer
bash dev.sh lint      # Run ty (type check) and ruff (lint check)
bash dev.sh test      # Run tests and generate coverage report
bash dev.sh check     # Run the full pre-commit pipeline (format, lint, test, hooks)
```

## 3. Quality Standards

### 3.1 100% Test Coverage
We enforce 100% code coverage. Every new feature or bug fix must include corresponding tests.
- Verification: `fail_under = 100` in `pyproject.toml`.
- Execution: `bash dev.sh test`.

### 3.2 Strict Typing
All code must be fully typed and pass `ty check`. Legacy `Union` and `Optional` types should be replaced with the modern `|` operator.

### 3.3 Linting & Formatting
- **Line Length:** Standard is 100 characters.
- **Rules:** We use the `ALL` rule set in `ruff` with specific ignores for documentation and trailing commas.
- **Automatic Fixes:** `ruff check --fix` should be used to resolve common linting issues.

## 4. Contributing

1.  **Surgical Changes:** Keep PRs focused. Avoid unrelated refactoring.
2.  **Conventional Commits:** Use standard prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`.
3.  **Documentation:** Update the relevant files in the `docs/` directory if your changes affect the architecture, commands, or formatting logic.
4.  **Modern Python:** Follow the latest Python standards (no `from __future__ import annotations`, use modern type hints).
