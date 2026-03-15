# Plan: Fix Ruff Errors in Test Files

## Objective
Fix identified Ruff errors in test files while adhering to the specified requirements.

## Key Files & Context
- `tests/test_markdown.py`: Missing return type annotations.
- `tests/test_gemini.py`: Missing return type annotations, magic values, private member access, and insecure usage of `/tmp`.
- `tests/test_events.py`: Missing return type annotations and magic values.
- `tests/test_config.py`: Missing return type annotations, hardcoded secrets, and insecure usage of `/tmp`.
- `tests/test_cli.py`: Missing return type annotations, hardcoded secrets, and magic values.
- `tests/test_bot.py`: Missing return type annotations, hardcoded secrets, and nested `with` statements.
- `tests/conftest.py`: Hardcoded secrets.

## Implementation Steps

### 1. `tests/conftest.py`
- Add `# noqa: S106` to lines where dummy tokens like `"123:ABC"` are used in `sample_config` and `sample_toml`.

### 2. `tests/test_markdown.py`
- Add `-> None` to all function signatures.

### 3. `tests/test_gemini.py`
- Add `-> None` to all function signatures.
- Inject `tmp_path` fixture into `test_agent_run_stream_success`.
- Replace `working_dir="/tmp"` with `working_dir=str(tmp_path)` and `cwd="/tmp"` with `cwd=str(tmp_path)`.
- Replace magic value `2` in `assert len(events) == 2` with a named constant `EXPECTED_EVENTS = 2`.
- Add `# noqa: SLF001` to the `test_parse_line_invalid` function where `agent._parse_line` is accessed.

### 4. `tests/test_events.py`
- Add `-> None` to all function signatures.
- Replace magic value `10` in `assert event.stats.total_tokens == 10` with a named constant `TOTAL_TOKENS = 10`.

### 5. `tests/test_config.py`
- Add `-> None` to all function signatures.
- Add `# noqa: S105` to lines where `bot_token = 'token'` or `cfg.telegram.bot_token == "token"` is used.
- Replace `working_dir = '/tmp'` with `working_dir = '{tmp_path}'` using f-string or similar, and `cfg.gemini.working_dir == "/tmp"` with `cfg.gemini.working_dir == str(tmp_path)`.

### 6. `tests/test_cli.py`
- Add `-> None` to all function signatures.
- Add `# noqa: S105` to `VALID_TOKEN = ...`.
- Replace magic value `2` in `assert result.exit_code == 2` with `typer.ExitCode.USAGE_ERROR` (if available) or a local constant. Actually, `2` for `typer` usually means usage error. I'll use a local constant `EXIT_USAGE_ERROR = 2`.

### 7. `tests/test_bot.py`
- Add `-> None` to all function signatures.
- Add `# noqa: S105` to `VALID_TOKEN = ...`.
- In `test_handle_message_flow`, combine the nested `with` statements into a single `with` statement:
  ```python
  with patch("tg_gemini.bot.ChatActionSender.typing", return_value=AsyncMock()), \
       patch("time.monotonic", side_effect=mock_monotonic):
      await handle_message(message, sessions, agent, config)
  ```

### 8. General
- Double-check all files for `from __future__ import annotations` and remove if found (none found in initial search).

## Verification & Testing
- Run `ruff check tests/` with the specified rules to ensure all errors are fixed.
- Run `pytest tests/` to ensure all tests still pass.
