"""CLI entry point for tg-gemini."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

__all__ = ["app"]

app = typer.Typer(
    name="tg-gemini",
    help="Telegram↔Gemini CLI middleware service.",
    no_args_is_help=True,
)


@app.command()
def start(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to config TOML file.")
    ] = None,
) -> None:
    """Start the tg-gemini bot service."""
    from tg_gemini.config import load_config, resolve_config_path
    from tg_gemini.dedup import MessageDedup
    from tg_gemini.engine import Engine
    from tg_gemini.gemini import GeminiAgent
    from tg_gemini.i18n import I18n, Language
    from tg_gemini.ratelimit import RateLimiter
    from tg_gemini.session import SessionManager
    from tg_gemini.telegram_platform import TelegramPlatform

    config_path = resolve_config_path(str(config) if config else None)
    if not config_path.exists():
        typer.echo(f"Config file not found: {config_path}", err=True)
        raise typer.Exit(1)

    cfg = load_config(config_path)

    # Configure loguru
    logger.remove()
    logger.add(
        sys.stderr,
        level=cfg.log.level,
        colorize=True,
        format="{time} {level} {message}",
    )

    logger.info("tg-gemini starting", config=str(config_path))

    # Determine language
    lang = Language(cfg.language) if cfg.language in ("en", "zh") else Language.EN

    # Build components
    data_path = Path(cfg.data_dir).expanduser()
    data_path.mkdir(parents=True, exist_ok=True)

    sessions = SessionManager(store_path=data_path / "sessions.json")

    agent = GeminiAgent(
        work_dir=cfg.gemini.work_dir,
        model=cfg.gemini.model,
        mode=cfg.gemini.mode,
        cmd=cfg.gemini.cmd,
        api_key=cfg.gemini.api_key,
        timeout_mins=cfg.gemini.timeout_mins,
    )

    platform = TelegramPlatform(
        token=cfg.telegram.token,
        allow_from=cfg.telegram.allow_from,
        group_reply_all=cfg.telegram.group_reply_all,
        share_session_in_channel=cfg.telegram.share_session_in_channel,
    )

    i18n = I18n(lang=lang)
    rate_limiter = RateLimiter(
        max_messages=cfg.rate_limit.max_messages, window_secs=cfg.rate_limit.window_secs
    )
    dedup = MessageDedup()
    engine = Engine(
        config=cfg,
        agent=agent,
        platform=platform,
        sessions=sessions,
        i18n=i18n,
        rate_limiter=rate_limiter,
        dedup=dedup,
    )

    async def _run() -> None:
        await rate_limiter.start()
        try:
            await engine.start()
        finally:
            await rate_limiter.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("tg-gemini stopped")
