import asyncio
import contextlib
import time
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from tg_gemini.config import MODEL_ALIASES, AppConfig
from tg_gemini.events import ErrorEvent, InitEvent, MessageEvent, ToolUseEvent
from tg_gemini.gemini import GeminiAgent, SessionInfo
from tg_gemini.markdown import md_to_telegram_html

TELEGRAM_MAX_LENGTH = 4096
UPDATE_INTERVAL = 1.5
UPDATE_CHAR_THRESHOLD = 200


@dataclass
class UserSession:
    session_id: str | None = None
    model: str | None = None
    active: bool = True
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_sessions: list[SessionInfo] = field(default_factory=list)
    custom_names: dict[str, str] = field(default_factory=dict)
    pending_name: str | None = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[int, UserSession] = {}

    def get(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]


def _is_authorized(user_id: int, allowed_ids: list[int]) -> bool:
    return not allowed_ids or user_id in allowed_ids


router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, sessions: SessionManager) -> None:
    if not message.from_user:
        return
    session = sessions.get(message.from_user.id)
    session.active = True
    await message.answer(
        "Bot activated. Send me a message to chat with Gemini.\n\n"
        "Commands:\n"
        "/new [name] - Start a new session (with optional name)\n"
        "/list - List available sessions\n"
        "/resume [index|id] - Resume a specific or the latest session\n"
        "/name <name> - Name the current session\n"
        "/delete <index|id> - Delete a session\n"
        "/model <name> - Switch model\n"
        "/status - Show current status\n"
        "/current - Show current status (detailed)"
    )


@router.message(Command("new"))
async def cmd_new(message: Message, command: CommandObject, sessions: SessionManager) -> None:
    if not message.from_user:
        return
    session = sessions.get(message.from_user.id)
    session.session_id = None
    session.pending_name = command.args if command.args else None

    msg = "Session cleared. Next message starts a new conversation"
    if session.pending_name:
        msg += f" named: {session.pending_name}"
    await message.answer(msg + ".")


async def _format_session_list(
    sessions: list[SessionInfo], active_id: str | None, custom_names: dict[str, str]
) -> str:
    if not sessions:
        return "No sessions found."
    lines = ["Available sessions:"]
    for s in sessions:
        marker = "▶" if s.session_id == active_id else "◻"
        title = custom_names.get(s.session_id, s.title)
        lines.append(f"{s.index}. {marker} {title} ({s.time})")
    lines.append("\nUse `/resume <index>` to change session.")
    return "\n".join(lines)


@router.message(Command("list"))
async def cmd_list(message: Message, sessions: SessionManager, agent: GeminiAgent) -> None:
    if not message.from_user:
        return
    session = sessions.get(message.from_user.id)
    session.last_sessions = await agent.list_sessions()
    text = await _format_session_list(
        session.last_sessions, session.session_id, session.custom_names
    )
    await message.answer(md_to_telegram_html(text), parse_mode="HTML")


def _resolve_id(arg: str, last_sessions: list[SessionInfo]) -> str:
    if arg.isdigit():
        idx = int(arg)
        for s in last_sessions:
            if s.index == idx:
                return s.session_id
    return arg


@router.message(Command("name"))
async def cmd_name(message: Message, command: CommandObject, sessions: SessionManager) -> None:
    if not message.from_user:
        return
    session = sessions.get(message.from_user.id)
    if not session.session_id:
        await message.answer("No active session to name. Send a message first.")
        return
    if not command.args:
        await message.answer("Usage: /name <new_name>")
        return

    session.custom_names[session.session_id] = command.args
    await message.answer(f"Session renamed to: {command.args}")


@router.message(Command("resume"))
async def cmd_resume(message: Message, command: CommandObject, sessions: SessionManager) -> None:
    if not message.from_user:
        return
    session = sessions.get(message.from_user.id)
    if command.args:
        target_id = _resolve_id(command.args, session.last_sessions)
        session.session_id = target_id
        await message.answer(f"Resuming session: <code>{target_id}</code>", parse_mode="HTML")
    else:
        # If no args, list or just resume latest
        session.session_id = "latest"
        await message.answer("Resuming latest session.")


@router.message(Command("delete"))
async def cmd_delete(
    message: Message, command: CommandObject, sessions: SessionManager, agent: GeminiAgent
) -> None:
    if not message.from_user:
        return
    if not command.args:
        await message.answer("Usage: /delete <index|id>")
        return

    session = sessions.get(message.from_user.id)
    target_id = _resolve_id(command.args, session.last_sessions)

    success = await agent.delete_session(target_id)
    if success:
        if session.session_id == target_id:
            session.session_id = None
        # Clean up custom name if any
        session.custom_names.pop(target_id, None)
        await message.answer(f"Deleted session: <code>{target_id}</code>", parse_mode="HTML")
    else:
        await message.answer("Failed to delete session.")


@router.message(Command("model"))
async def cmd_model(message: Message, command: CommandObject, sessions: SessionManager) -> None:
    if not message.from_user:
        return
    if not command.args:
        aliases = ", ".join(sorted(MODEL_ALIASES.keys()))
        await message.answer(f"Usage: /model <name>\nAliases: {aliases}")
        return
    session = sessions.get(message.from_user.id)
    session.model = command.args
    await message.answer(f"Model set to: {command.args}")


@router.message(Command("status"))
async def cmd_status(message: Message, sessions: SessionManager, config: AppConfig) -> None:
    if not message.from_user:
        return
    session = sessions.get(message.from_user.id)
    status = (
        f"Active: {session.active}\n"
        f"Model: {session.model or config.gemini.model}\n"
        f"Session: {session.session_id or 'new'}"
    )
    await message.answer(status)


@router.message(Command("current"))
async def cmd_current(message: Message, sessions: SessionManager, config: AppConfig) -> None:
    if not message.from_user:
        return
    session = sessions.get(message.from_user.id)
    current = (
        f"Current Model: <code>{session.model or config.gemini.model}</code>\n"
        f"Current Session: <code>{session.session_id or 'new'}</code>"
    )
    await message.answer(current, parse_mode="HTML")


async def _throttle_update(
    reply: Message,
    accumulated: str,
    status_lines: list[str],
    last_update_time: float,
    last_update_len: int,
) -> tuple[float, int]:
    now = time.monotonic()
    if (
        now - last_update_time >= UPDATE_INTERVAL
        and len(accumulated) - last_update_len >= UPDATE_CHAR_THRESHOLD
    ):
        await _update_ui(reply, accumulated, status_lines)
        return now, len(accumulated)
    return last_update_time, last_update_len


async def _process_stream(
    message: Message, session: UserSession, agent: GeminiAgent
) -> tuple[str, list[str]]:
    if not message.bot:
        return "", []

    accumulated = ""
    status_lines: list[str] = []
    last_update_time = time.monotonic()
    last_update_len = 0

    reply = await message.answer("Thinking...")

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        async for event in agent.run_stream(message.text or "", session.session_id, session.model):
            if isinstance(event, InitEvent):
                session.session_id = event.session_id
                if session.pending_name and event.session_id:
                    session.custom_names[event.session_id] = session.pending_name
                    session.pending_name = None
            elif isinstance(event, MessageEvent):
                if event.role == "assistant":
                    accumulated += event.content
                    last_update_time, last_update_len = await _throttle_update(
                        reply, accumulated, status_lines, last_update_time, last_update_len
                    )
            elif isinstance(event, ToolUseEvent):
                status_lines.append(f"🔧 {event.tool_name}")
                await _update_ui(reply, accumulated, status_lines)
            elif isinstance(event, ErrorEvent):
                await reply.edit_text(f"Error: {event.message}")
                return "", []

    if accumulated or status_lines:
        await _update_ui(reply, accumulated, status_lines)
    else:
        await reply.edit_text("No response.")

    return accumulated, status_lines


@router.message(F.text & ~F.text.startswith("/"))
async def handle_message(
    message: Message, sessions: SessionManager, agent: GeminiAgent, config: AppConfig
) -> None:
    if not message.from_user or not message.text:
        return
    if not _is_authorized(message.from_user.id, config.telegram.allowed_user_ids):
        return

    session = sessions.get(message.from_user.id)
    if not session.active:
        return

    async with session.lock:
        await _process_stream(message, session, agent)


async def _update_ui(reply: Message, accumulated: str, status_lines: list[str]) -> None:
    text = accumulated if accumulated else ""
    if status_lines:
        if text:
            text += "\n\n"
        text += "\n".join(status_lines[-5:])

    if not text:
        text = "Thinking..."

    with contextlib.suppress(Exception):
        await reply.edit_text(md_to_telegram_html(text), parse_mode="HTML")


async def start_bot(config: AppConfig) -> None:
    bot = Bot(token=config.telegram.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    sessions = SessionManager()
    agent = GeminiAgent(config.gemini)

    await dp.start_polling(bot, sessions=sessions, agent=agent, config=config)
