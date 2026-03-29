import asyncio
import logging
from pathlib import Path
from typing import Annotated

import structlog
import typer

from tg_gemini.bot import start_bot
from tg_gemini.config import load_config

app = typer.Typer(help="Telegram-Gemini CLI middleware.")
logger = structlog.get_logger()


def setup_logging(*, verbose: bool = False) -> None:
    """Configure logging for the application."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if verbose else logging.INFO
        ),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    )
    # Reduce noise from underlying libraries
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


@app.command()
def start(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to config.toml", exists=True)
    ] = None,
    verbose: Annotated[  # noqa: FBT002
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """Start the Telegram bot."""
    setup_logging(verbose=verbose)
    try:
        cfg = load_config(config)
        logger.info("starting_bot", model=cfg.gemini.model)
        asyncio.run(start_bot(cfg))
    except Exception as e:
        logger.exception("bot_crashed", error=str(e))
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
