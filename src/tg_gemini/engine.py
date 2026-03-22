"""Engine: orchestrates Telegram messages → Gemini sessions → streaming replies."""

import asyncio

from loguru import logger

from tg_gemini.config import AppConfig
from tg_gemini.gemini import GeminiAgent, GeminiSession
from tg_gemini.i18n import I18n, MsgKey
from tg_gemini.models import EventType, Message, ReplyContext
from tg_gemini.session import Session, SessionManager
from tg_gemini.streaming import StreamPreview
from tg_gemini.telegram_platform import TelegramPlatform

__all__ = ["Engine"]

_MAX_QUEUE = 5


class Engine:
    """Routes incoming messages to Gemini and streams responses back to Telegram."""

    def __init__(
        self,
        config: AppConfig,
        agent: GeminiAgent,
        platform: TelegramPlatform,
        sessions: SessionManager,
        i18n: I18n,
    ) -> None:
        self._config = config
        self._agent = agent
        self._platform = platform
        self._sessions = sessions
        self._i18n = i18n
        self._queues: dict[str, asyncio.Queue[Message]] = {}
        self._active_gemini: dict[str, GeminiSession] = {}

    async def start(self) -> None:
        """Start the Telegram polling loop."""
        await self._platform.start(self.handle_message)

    async def stop(self) -> None:
        """Stop the platform."""
        await self._platform.stop()

    async def handle_message(self, msg: Message) -> None:
        """Entry point for all incoming messages."""
        logger.info(
            "message received",
            platform=msg.platform,
            user=msg.user_name,
            content_len=len(msg.content),
        )

        content = msg.content.strip()
        if not content and not msg.images and not msg.files:
            return

        # Slash command handling
        if content.startswith("/"):
            await self.handle_command(msg, content)
            return

        session = self._sessions.get_or_create(msg.session_key)

        # If agent is busy, queue the message
        if session.busy:
            q = self._queues.setdefault(
                msg.session_key, asyncio.Queue(maxsize=_MAX_QUEUE)
            )
            if q.full():
                await self._reply(msg, self._i18n.t(MsgKey.SESSION_BUSY))
                return
            await q.put(msg)
            await self._reply(msg, self._i18n.t(MsgKey.SESSION_BUSY))
            return

        await self._process(msg, session)

    async def handle_command(self, msg: Message, raw: str) -> bool:
        """Handle slash commands. Returns True if consumed."""
        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]  # strip @botname suffix
        args = parts[1].strip() if len(parts) > 1 else ""

        match cmd:
            case "/new":
                await self._cmd_new(msg)
            case "/help":
                await self._cmd_help(msg)
            case "/stop":
                await self._cmd_stop(msg)
            case "/model":
                await self._cmd_model(msg, args)
            case "/mode":
                await self._cmd_mode(msg, args)
            case _:
                await self._reply(msg, self._i18n.t(MsgKey.UNKNOWN_CMD))
                return True
        return True

    async def _process(self, msg: Message, session: Session) -> None:
        """Run Gemini and stream response back. Drains queued messages after completion."""
        acquired = await session.try_lock()
        if not acquired:
            await self._reply(msg, self._i18n.t(MsgKey.SESSION_BUSY))
            return

        try:
            await self._run_gemini(msg, session)
        finally:
            await session.unlock()
            # Drain queued messages
            q = self._queues.get(msg.session_key)
            if q and not q.empty():
                try:
                    next_msg = q.get_nowait()
                    task = asyncio.create_task(self._process(next_msg, session))
                    task.add_done_callback(
                        lambda t: (
                            logger.error(
                                "Engine: queue drain task failed",
                                exc_info=t.exception(),
                            )
                            if t.exception()
                            and not isinstance(t.exception(), asyncio.CancelledError)
                            else None
                        )
                    )
                except asyncio.QueueEmpty:
                    pass

    async def _run_gemini(self, msg: Message, session: Session) -> None:
        """Send prompt to Gemini and stream events to Telegram."""
        assert msg.reply_ctx is not None
        ctx: ReplyContext = msg.reply_ctx

        typing_task = await self._platform.start_typing(ctx)

        gemini_session: GeminiSession | None = None
        try:
            gemini_session = self._agent.start_session(
                resume_id=session.agent_session_id
            )
            self._active_gemini[msg.session_key] = gemini_session

            preview = StreamPreview(
                config=self._config.stream_preview,
                send_preview=lambda text: self._platform.send_preview_start(ctx, text),
                update_preview=self._platform.update_message,
                delete_preview=self._platform.delete_preview,
            )

            await gemini_session.send(
                prompt=msg.content, images=msg.images or [], files=msg.files or []
            )

            full_text = ""
            tool_used = False

            while True:
                try:
                    event = await asyncio.wait_for(
                        gemini_session.events.get(), timeout=120
                    )
                except TimeoutError:
                    logger.error("Engine: gemini session timed out")
                    break

                match event.type:
                    case EventType.TEXT:
                        if event.session_id:
                            # init event: store session_id
                            session.agent_session_id = event.session_id
                        elif event.content:
                            full_text += event.content
                            await preview.append_text(event.content)

                    case EventType.THINKING:
                        # Flush thinking text as a short notification
                        if event.content:
                            max_len = self._config.display.thinking_max_len
                            truncated = (
                                event.content[:max_len] + "…"
                                if len(event.content) > max_len
                                else event.content
                            )
                            thinking_msg = f"<i>{truncated}</i>"
                            await self._platform.send(ctx, thinking_msg)

                    case EventType.TOOL_USE:
                        await preview.freeze()
                        preview.detach()
                        tool_used = True
                        tool_display = event.tool_input
                        max_len = self._config.display.tool_max_len
                        if len(tool_display) > max_len:
                            tool_display = tool_display[:max_len] + "…"
                        tool_msg = self._i18n.tf(
                            MsgKey.TOOL_USE, event.tool_name, tool_display
                        )
                        await self._platform.send(ctx, tool_msg)

                    case EventType.TOOL_RESULT:
                        if event.content:
                            result_msg = self._i18n.tf(
                                MsgKey.TOOL_RESULT, event.content
                            )
                            await self._platform.send(ctx, result_msg)

                    case EventType.ERROR:
                        err_str = str(event.error) if event.error else "unknown error"
                        await self._platform.send(
                            ctx, self._i18n.tf(MsgKey.ERROR_PREFIX, err_str)
                        )

                    case EventType.RESULT:
                        sent = await preview.finish(full_text)
                        if not sent:
                            if full_text:
                                await self._platform.reply(ctx, full_text)
                            elif not tool_used:
                                await self._platform.send(
                                    ctx, self._i18n.t(MsgKey.EMPTY_RESPONSE)
                                )
                        break

        except Exception as exc:
            logger.exception("Engine: error processing message", error=exc)
            await self._platform.send(ctx, self._i18n.tf(MsgKey.ERROR_PREFIX, str(exc)))
        finally:
            typing_task.cancel()
            self._active_gemini.pop(msg.session_key, None)
            if gemini_session:
                await gemini_session.close()

    async def _reply(self, msg: Message, content: str) -> None:
        if msg.reply_ctx is not None:
            ctx: ReplyContext = msg.reply_ctx
            await self._platform.send(ctx, content)

    # --- slash command handlers ---

    async def _cmd_new(self, msg: Message) -> None:
        session = self._sessions.new_session(msg.session_key)
        logger.info(
            "Engine: new session", session_key=msg.session_key, session_id=session.id
        )
        await self._reply(msg, self._i18n.t(MsgKey.SESSION_NEW))

    async def _cmd_help(self, msg: Message) -> None:
        await self._reply(msg, self._i18n.t(MsgKey.HELP))

    async def _cmd_stop(self, msg: Message) -> None:
        gemini = self._active_gemini.get(msg.session_key)
        if gemini:
            await gemini.kill()
            logger.info(
                "Engine: /stop killed active session", session_key=msg.session_key
            )
        await self._reply(msg, self._i18n.t(MsgKey.STOP_OK))

    async def _cmd_model(self, msg: Message, args: str) -> None:
        if args:
            self._agent.model = args
            await self._reply(msg, self._i18n.tf(MsgKey.MODEL_SWITCHED, args))
        else:
            current = self._agent.model or "(default)"
            models = self._agent.available_models()
            model_list = "\n".join(f"  • {m.name}" for m in models)
            text = self._i18n.tf(MsgKey.MODEL_CURRENT, current) + "\n\n" + model_list
            await self._reply(msg, text)

    async def _cmd_mode(self, msg: Message, args: str) -> None:
        valid_modes = ("default", "auto_edit", "yolo", "plan")
        if args and args in valid_modes:
            self._agent.mode = args
            await self._reply(msg, self._i18n.tf(MsgKey.MODE_SWITCHED, args))
        elif args:
            modes_str = " | ".join(valid_modes)
            await self._reply(
                msg, self._i18n.tf(MsgKey.MODE_SWITCHED, f"invalid. Use: {modes_str}")
            )
        else:
            current = self._agent.mode
            await self._reply(msg, self._i18n.tf(MsgKey.MODE_CURRENT, current))
