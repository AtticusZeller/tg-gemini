# CLI Reference

The `tg-gemini` middleware provides a command-line interface for managing the bot service.

## Usage

```bash
uv run python -m tg_gemini.cli [COMMAND] [OPTIONS]
```

## Commands

### `start`
Starts the Telegram bot.

- **Options:**
    - `--config`, `-c`: (Path) Path to the `config.toml` file. If not provided, it searches in the default location (`~/.config/tg-gemini/config.toml`).

### `check-config`
Validates the configuration file without starting the bot.

- **Options:**
    - `--config`, `-c`: (Path) Path to the `config.toml` file.

### `version`
Displays the current version of `tg-gemini`.

## Development Helper (`dev.sh`)

For development tasks, use the `dev.sh` script:

```bash
bash dev.sh format    # Auto-format code with ruff
bash dev.sh lint      # Run type checks and linting
bash dev.sh test      # Run the test suite with coverage
bash dev.sh check     # Run the full quality pipeline
```
