import asyncio
from pathlib import Path
from typing import Annotated

import typer

from tg_gemini.bot import start_bot
from tg_gemini.config import load_config

app = typer.Typer(help="Telegram-Gemini CLI middleware.")


@app.command()
def start(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to config.toml", exists=True)
    ] = None,
) -> None:
    """Start the Telegram bot."""
    try:
        cfg = load_config(config)
        typer.echo(f"Starting bot (model={cfg.gemini.model})")
        asyncio.run(start_bot(cfg))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def check_config(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to config.toml", exists=True)
    ] = None,
) -> None:
    """Validate the configuration file."""
    try:
        cfg = load_config(config)
        typer.echo(f"Config OK: model={cfg.gemini.model}")
    except Exception as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def version() -> None:
    """Show version."""
    from tg_gemini import __version__

    typer.echo(f"tg-gemini {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
