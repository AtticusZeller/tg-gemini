import asyncio
import contextlib
import html as html_mod
import time
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BotCommand, Message
from aiogram.utils.chat_action import ChatActionSender

from tg_gemini.config import MODEL_ALIASES, AppConfig
from tg_gemini.events import (
    ErrorEvent,
    InitEvent,
    MessageEvent,
    ResultEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from tg_gemini.gemini import GeminiAgent, SessionInfo
from tg_gemini.markdown import md_to_telegram_html, split_message_code_fence_aware

TELEGRAM_MAX_LENGTH = 4096
UPDATE_INTERVAL = 1.5
UPDATE_CHAR_THRESHOLD = 200
TOOL_CMD_TRUNCATE = 4096
TOOL_PARAM_TRUNCATE = 4096
TOOL_CONTENT_PREVIEW = 500


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
    session.pending_name = command.args or None

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


def _truncate(text: str, limit: int) -> str:
    return text[:limit] + "…" if len(text) > limit else text


def _esc(text: str) -> str:
    return html_mod.escape(text)


def _pre(text: str, lang: str = "") -> str:
    cls = f' class="language-{lang}"' if lang else ""
    return f"<pre><code{cls}>{_esc(text)}</code></pre>"


def _fmt_shell(params: dict[str, object]) -> str:
    cmd = _truncate(str(params["command"]), TOOL_CMD_TRUNCATE)
    desc = params.get("description", "")
    title = _esc(str(desc)) if desc else "run_shell_command"
    return f"🔧 <b>{title}</b>\n{_pre(cmd, 'bash')}"


def _fmt_file_op(name: str, params: dict[str, object]) -> str:
    fp = _esc(str(params["file_path"]))
    parts: list[str] = [f"🔧 <b>{name}</b>: <code>{fp}</code>"]
    if name == "replace":
        if "instruction" in params:
            instr = _esc(_truncate(str(params["instruction"]), TOOL_PARAM_TRUNCATE))
            parts.append(f"<i>{instr}</i>")
        old = str(params.get("old_string", ""))
        new = str(params.get("new_string", ""))
        if old or new:
            diff_lines = []
            if old:
                diff_lines.append(f"- {_truncate(old, TOOL_CONTENT_PREVIEW)}")
            if new:
                diff_lines.append(f"+ {_truncate(new, TOOL_CONTENT_PREVIEW)}")
            parts.append(_pre("\n".join(diff_lines)))
    elif name == "write_file" and "content" in params:
        preview = _truncate(str(params["content"]), TOOL_CONTENT_PREVIEW)
        parts.append(_pre(preview))
    elif name == "read_file":
        start = params.get("start_line")
        end = params.get("end_line")
        if start and end:
            parts[0] += f" (L{start}-L{end})"
        elif start:
            parts[0] += f" (from L{start})"
    return "\n".join(parts)


def _fmt_search(name: str, params: dict[str, object]) -> str | None:
    if name == "list_directory" and "dir_path" in params:
        return f"🔧 <b>list_directory</b>: <code>{_esc(str(params['dir_path']))}</code>"
    if name == "glob" and "pattern" in params:
        return f"🔧 <b>glob</b>: <code>{_esc(str(params['pattern']))}</code>"
    if name == "grep_search" and ("pattern" in params or "query" in params):
        query = str(params.get("pattern") or params.get("query", ""))
        return f"🔧 <b>grep_search</b>: <code>{_esc(query)}</code>"
    if name == "google_web_search" and "query" in params:
        return f"🔧 <b>google_web_search</b>: {_esc(str(params['query']))}"
    if name == "web_fetch" and ("prompt" in params or "url" in params):
        val = str(params.get("prompt") or params.get("url", ""))
        return f"🔧 <b>web_fetch</b>: {_esc(_truncate(val, TOOL_PARAM_TRUNCATE))}"
    return None


def _format_tool_html(event: ToolUseEvent) -> str:
    """Format a tool use event into HTML for Telegram display."""
    name = event.tool_name
    params = event.parameters

    if name == "run_shell_command" and "command" in params:
        return _fmt_shell(params)
    if name in ("read_file", "write_file", "replace") and "file_path" in params:
        return _fmt_file_op(name, params)

    result = _fmt_search(name, params)
    if result:
        return result

    if params:
        first_val = _truncate(str(next(iter(params.values()))), TOOL_PARAM_TRUNCATE)
        return f"🔧 <b>{name}</b>: {_esc(first_val)}"

    return f"🔧 {name}"


async def _throttle_edit(
    reply: Message, accumulated: str, last_update_time: float, last_update_len: int
) -> tuple[float, int]:
    now = time.monotonic()
    if (
        now - last_update_time >= UPDATE_INTERVAL
        and len(accumulated) - last_update_len >= UPDATE_CHAR_THRESHOLD
    ):
        await _edit_reply(reply, accumulated)
        return now, len(accumulated)
    return last_update_time, last_update_len


@dataclass
class _StreamState:
    accumulated: str = ""
    tool_messages: dict[str, Message] = field(default_factory=dict)
    tool_html: dict[str, str] = field(default_factory=dict)
    last_update_time: float = 0.0
    last_update_len: int = 0
    aborted: bool = False
    stats_footer: str = ""


async def _handle_event(
    event: object, session: UserSession, state: _StreamState, reply: Message
) -> None:
    """Process a single stream event, updating state and UI."""
    if isinstance(event, InitEvent):
        session.session_id = event.session_id
        if session.pending_name and event.session_id:
            session.custom_names[event.session_id] = session.pending_name
            session.pending_name = None
    elif isinstance(event, MessageEvent) and event.role == "assistant":
        state.accumulated = (state.accumulated + event.content) if event.delta else event.content
        state.last_update_time, state.last_update_len = await _throttle_edit(
            reply, state.accumulated, state.last_update_time, state.last_update_len
        )
    elif isinstance(event, ToolUseEvent):
        tool_html = _format_tool_html(event)
        tool_msg = await reply.answer(tool_html, parse_mode="HTML")
        state.tool_messages[event.tool_id] = tool_msg
        state.tool_html[event.tool_id] = tool_html
    elif isinstance(event, ToolResultEvent) and event.tool_id in state.tool_messages:
        tool_msg = state.tool_messages[event.tool_id]
        icon = "✅" if event.status == "success" else "❌"
        new_html = state.tool_html[event.tool_id].replace("🔧", icon, 1)
        with contextlib.suppress(Exception):
            await tool_msg.edit_text(new_html, parse_mode="HTML")
    elif isinstance(event, ErrorEvent):
        await reply.edit_text(f"Error: {event.message}")
        state.aborted = True
    elif isinstance(event, ResultEvent) and event.stats:
        s = event.stats
        state.stats_footer = f"({s.total_tokens} tokens, {s.duration_ms / 1000:.1f}s)"


async def _process_stream(
    message: Message, session: UserSession, agent: GeminiAgent
) -> tuple[str, list[str]]:
    if not message.bot:
        return "", []

    reply = await message.answer("Thinking...")
    state = _StreamState(last_update_time=time.monotonic())

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        async for event in agent.run_stream(message.text or "", session.session_id, session.model):
            await _handle_event(event, session, state, reply)
            if state.aborted:
                return "", []

    if state.accumulated:
        if state.tool_messages:
            # Tools were used: delete "Thinking..." and send response as new message
            # so it appears AFTER tool messages in correct order
            with contextlib.suppress(Exception):
                await reply.delete()
            await _send_new(reply, state.accumulated)
        else:
            # No tools: edit "Thinking..." in place (clean Q&A flow)
            await _send_final(reply, state.accumulated)
    elif not state.tool_messages:
        await reply.edit_text("No response.")

    if state.stats_footer:
        with contextlib.suppress(Exception):
            await reply.answer(f"<i>{state.stats_footer}</i>", parse_mode="HTML")

    return state.accumulated, list(state.tool_messages.keys())


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


async def _edit_reply(reply: Message, accumulated: str) -> None:
    """Edit the reply message with current accumulated text (streaming preview)."""
    html = md_to_telegram_html(accumulated)
    chunks = split_message_code_fence_aware(html, max_len=TELEGRAM_MAX_LENGTH)
    if chunks:
        with contextlib.suppress(Exception):
            await reply.edit_text(chunks[0], parse_mode="HTML")


async def _send_final(reply: Message, accumulated: str) -> None:
    """Edit the reply with final response, splitting into extra messages if needed."""
    html = md_to_telegram_html(accumulated)
    chunks = split_message_code_fence_aware(html, max_len=TELEGRAM_MAX_LENGTH)

    if not chunks:
        return

    with contextlib.suppress(Exception):
        await reply.edit_text(chunks[0], parse_mode="HTML")

    if reply.bot:
        for chunk in chunks[1:]:
            with contextlib.suppress(Exception):
                await reply.answer(chunk, parse_mode="HTML")


async def _send_new(reply: Message, accumulated: str) -> None:
    """Send the final response as new message(s) after tool messages."""
    html = md_to_telegram_html(accumulated)
    chunks = split_message_code_fence_aware(html, max_len=TELEGRAM_MAX_LENGTH)

    for chunk in chunks:
        with contextlib.suppress(Exception):
            await reply.answer(chunk, parse_mode="HTML")


async def start_bot(config: AppConfig) -> None:
    bot = Bot(token=config.telegram.bot_token)

    commands = [
        BotCommand(command="start", description="Welcome and help"),
        BotCommand(command="new", description="Start a new session"),
        BotCommand(command="list", description="List your sessions"),
        BotCommand(command="resume", description="Resume a session"),
        BotCommand(command="name", description="Name the current session"),
        BotCommand(command="current", description="Show current status"),
        BotCommand(command="model", description="Switch Gemini model"),
        BotCommand(command="delete", description="Delete a session"),
    ]
    await bot.set_my_commands(commands)

    dp = Dispatcher()
    dp.include_router(router)

    sessions = SessionManager()
    agent = GeminiAgent(config.gemini)

    await dp.start_polling(bot, sessions=sessions, agent=agent, config=config)
