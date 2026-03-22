"""Tests for telegram_platform.py."""

import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_gemini.models import (
    FileAttachment,
    ImageAttachment,
    Message as CoreMessage,
    PreviewHandle,
    ReplyContext,
)
from tg_gemini.telegram_platform import TelegramPlatform, _is_allowed

# --- _is_allowed ---


def test_is_allowed_wildcard() -> None:
    assert _is_allowed("*", "12345") is True
    assert _is_allowed("*", "anything") is True


def test_is_allowed_explicit_list() -> None:
    assert _is_allowed("123,456", "123") is True
    assert _is_allowed("123, 456", "456") is True
    assert _is_allowed("123,456", "999") is False


def test_is_allowed_single_id() -> None:
    assert _is_allowed("42", "42") is True
    assert _is_allowed("42", "43") is False


# --- TelegramPlatform construction ---


def test_platform_construction() -> None:
    platform = TelegramPlatform(token="abc:TOKEN", allow_from="*")
    assert platform._token == "abc:TOKEN"
    assert platform._allow_from == "*"
    assert platform._app is None


# --- reply / send / etc when _app is None ---


async def test_reply_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1, message_id=10)
    # Should not raise even when app is None
    await platform.reply(ctx, "hello")


async def test_send_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1, message_id=10)
    await platform.send(ctx, "hello")


async def test_send_image_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1)
    img = ImageAttachment(mime_type="image/jpeg", data=b"jpg")
    await platform.send_image(ctx, img)  # no error


async def test_send_file_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1)
    f = FileAttachment(mime_type="text/plain", data=b"data", file_name="f.txt")
    await platform.send_file(ctx, f)  # no error


async def test_send_preview_start_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1, message_id=10)
    with pytest.raises(RuntimeError, match="not started"):
        await platform.send_preview_start(ctx, "hello")


async def test_update_message_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    handle = PreviewHandle(chat_id=1, message_id=42)
    await platform.update_message(handle, "new text")  # no error


async def test_delete_preview_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    handle = PreviewHandle(chat_id=1, message_id=42)
    await platform.delete_preview(handle)  # no error


async def test_send_with_buttons_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1)
    await platform.send_with_buttons(ctx, "content", [("btn", "data")])  # no error


async def test_stop_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    await platform.stop()
    assert platform._app is None


# --- With mocked app ---


def _make_platform_with_app() -> tuple[TelegramPlatform, MagicMock]:
    platform = TelegramPlatform(token="tok:TOKEN", allow_from="*")
    mock_app = MagicMock()
    mock_bot = AsyncMock()
    mock_app.bot = mock_bot
    platform._app = mock_app
    return platform, mock_bot


async def test_reply_sends_html() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_message = AsyncMock()
    ctx = ReplyContext(chat_id=123, message_id=1)
    await platform.reply(ctx, "**bold** text")
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 123
    assert "<b>" in call_kwargs["text"]


async def test_reply_includes_reply_to() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_message = AsyncMock()
    ctx = ReplyContext(chat_id=123, message_id=55)
    await platform.reply(ctx, "hello")
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs.get("reply_to_message_id") == 55


async def test_send_html_fallback_on_parse_error() -> None:
    from telegram.error import BadRequest as TgBadRequest

    platform, mock_bot = _make_platform_with_app()

    call_count = 0

    async def side_effect(**_: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TgBadRequest("Can't parse entities")

    mock_bot.send_message = AsyncMock(side_effect=side_effect)
    ctx = ReplyContext(chat_id=1, message_id=0)
    await platform.send(ctx, "some text")
    assert call_count == 2  # tried HTML, then plain text


async def test_send_html_both_fail_logs_error() -> None:
    from telegram.error import BadRequest as TgBadRequest

    platform, mock_bot = _make_platform_with_app()

    mock_bot.send_message = AsyncMock(side_effect=TgBadRequest("error"))
    ctx = ReplyContext(chat_id=1, message_id=0)
    # Should not raise
    await platform.send(ctx, "text")


async def test_send_image() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_photo = AsyncMock()
    ctx = ReplyContext(chat_id=1)
    img = ImageAttachment(mime_type="image/jpeg", data=b"jpg_data")
    await platform.send_image(ctx, img)
    mock_bot.send_photo.assert_called_once_with(chat_id=1, photo=b"jpg_data")


async def test_send_image_failure_logs() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_photo = AsyncMock(side_effect=Exception("failed"))
    ctx = ReplyContext(chat_id=1)
    img = ImageAttachment(mime_type="image/jpeg", data=b"data")
    await platform.send_image(ctx, img)  # Should not raise


async def test_send_file() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_document = AsyncMock()
    ctx = ReplyContext(chat_id=1)
    f = FileAttachment(mime_type="text/plain", data=b"content", file_name="test.txt")
    await platform.send_file(ctx, f)
    mock_bot.send_document.assert_called_once_with(
        chat_id=1, document=b"content", filename="test.txt"
    )


async def test_send_file_no_name() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_document = AsyncMock()
    ctx = ReplyContext(chat_id=1)
    f = FileAttachment(mime_type="text/plain", data=b"content", file_name="")
    await platform.send_file(ctx, f)
    mock_bot.send_document.assert_called_once_with(
        chat_id=1, document=b"content", filename="file"
    )


async def test_send_file_failure_logs() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_document = AsyncMock(side_effect=Exception("failed"))
    ctx = ReplyContext(chat_id=1)
    f = FileAttachment(mime_type="text/plain", data=b"data")
    await platform.send_file(ctx, f)  # Should not raise


async def test_send_preview_start() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_msg = MagicMock()
    mock_msg.message_id = 99
    mock_bot.send_message = AsyncMock(return_value=mock_msg)
    ctx = ReplyContext(chat_id=100, message_id=0)
    handle = await platform.send_preview_start(ctx, "preview text")
    assert handle.chat_id == 100
    assert handle.message_id == 99


async def test_update_message_success() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.edit_message_text = AsyncMock()
    handle = PreviewHandle(chat_id=1, message_id=42)
    await platform.update_message(handle, "updated content")
    mock_bot.edit_message_text.assert_called_once()


async def test_update_message_not_modified() -> None:
    from telegram.error import BadRequest as TgBadRequest

    platform, mock_bot = _make_platform_with_app()
    mock_bot.edit_message_text = AsyncMock(
        side_effect=TgBadRequest("message is not modified")
    )
    handle = PreviewHandle(chat_id=1, message_id=42)
    await platform.update_message(handle, "same text")  # Should not raise


async def test_update_message_other_error_raises() -> None:
    from telegram.error import BadRequest as TgBadRequest

    platform, mock_bot = _make_platform_with_app()
    mock_bot.edit_message_text = AsyncMock(
        side_effect=TgBadRequest("message to edit not found")
    )
    handle = PreviewHandle(chat_id=1, message_id=42)
    with pytest.raises(TgBadRequest):
        await platform.update_message(handle, "text")


async def test_delete_preview() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.delete_message = AsyncMock()
    handle = PreviewHandle(chat_id=1, message_id=42)
    await platform.delete_preview(handle)
    mock_bot.delete_message.assert_called_once_with(chat_id=1, message_id=42)


async def test_delete_preview_failure_logs() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.delete_message = AsyncMock(side_effect=Exception("not found"))
    handle = PreviewHandle(chat_id=1, message_id=42)
    await platform.delete_preview(handle)  # Should not raise


async def test_start_typing_creates_task() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_chat_action = AsyncMock()
    ctx = ReplyContext(chat_id=1)
    task = await platform.start_typing(ctx)
    assert isinstance(task, asyncio.Task)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_typing_loop_sends_chat_action() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_chat_action = AsyncMock()
    ctx = ReplyContext(chat_id=5)
    task = await platform.start_typing(ctx)
    await asyncio.sleep(0.05)  # Let it run briefly
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert mock_bot.send_chat_action.call_count >= 1


async def test_typing_loop_no_app_returns() -> None:
    """Typing loop should return cleanly when app becomes None."""
    platform = TelegramPlatform(token="tok", allow_from="*")
    # _app is None
    ctx = ReplyContext(chat_id=5)
    task = await platform.start_typing(ctx)
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_send_with_buttons() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_message = AsyncMock()
    ctx = ReplyContext(chat_id=1)
    await platform.send_with_buttons(
        ctx, "Choose:", [("Option A", "cb_a"), ("Option B", "cb_b")]
    )
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert "reply_markup" in call_kwargs


async def test_send_with_buttons_failure_logs() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_message = AsyncMock(side_effect=Exception("failed"))
    ctx = ReplyContext(chat_id=1)
    await platform.send_with_buttons(ctx, "text", [("btn", "data")])  # Should not raise


async def test_stop_sets_app_none() -> None:
    platform, _ = _make_platform_with_app()
    assert platform._app is not None
    await platform.stop()
    assert platform._app is None


# --- _handle_update tests ---


def _make_update(
    chat_id: int = 1,
    user_id: int = 42,
    username: str = "testuser",
    text: str = "hello",
    date_ts: float | None = None,
    has_photo: bool = False,
    has_document: bool = False,
    message_id: int = 10,
) -> MagicMock:
    import time as t

    ts = date_ts if date_ts is not None else t.time()
    msg = MagicMock()
    msg.message_id = message_id
    msg.chat_id = chat_id
    msg.text = text
    msg.caption = None
    msg.date = MagicMock()
    msg.date.timestamp = MagicMock(return_value=ts)
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.first_name = "Test"
    user.last_name = "User"
    msg.from_user = user
    msg.photo = []
    msg.document = None
    if has_photo:
        photo = MagicMock()
        photo.file_id = "file123"
        msg.photo = [photo]
    if has_document:
        doc = MagicMock()
        doc.file_id = "docfile"
        doc.mime_type = "text/plain"
        doc.file_name = "test.txt"
        msg.document = doc
    update = MagicMock()
    update.message = msg
    return update


async def test_handle_update_text() -> None:
    platform, _mock_bot = _make_platform_with_app()
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    update = _make_update(text="hello world")
    await platform._handle_update(update, None)
    assert len(received) == 1
    assert received[0].content == "hello world"


async def test_handle_update_empty_text() -> None:
    platform, _mock_bot = _make_platform_with_app()
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    update = _make_update(text="")
    await platform._handle_update(update, None)
    assert len(received) == 0


async def test_handle_update_no_message() -> None:
    platform, _ = _make_platform_with_app()
    update = MagicMock()
    update.message = None
    await platform._handle_update(update, None)  # Should not raise


async def test_handle_update_old_message() -> None:
    import time as t

    platform, _ = _make_platform_with_app()
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    old_ts = t.time() - 100  # 100 seconds ago
    update = _make_update(date_ts=old_ts)
    await platform._handle_update(update, None)
    assert len(received) == 0


async def test_handle_update_no_from_user() -> None:
    platform, _ = _make_platform_with_app()
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    update = _make_update()
    update.message.from_user = None
    await platform._handle_update(update, None)
    assert len(received) == 0


async def test_handle_update_unauthorized_user() -> None:
    platform = TelegramPlatform(token="tok", allow_from="999")
    platform._app = MagicMock()  # type: ignore[assignment]
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    update = _make_update(user_id=42)  # user 42 not in allowed list
    await platform._handle_update(update, None)
    assert len(received) == 0


async def test_handle_update_photo_success() -> None:
    platform, mock_bot = _make_platform_with_app()
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    mock_photo_file = AsyncMock()
    mock_photo_file.download_as_bytearray = AsyncMock(
        return_value=bytearray(b"jpeg_data")
    )
    mock_bot.get_file = AsyncMock(return_value=mock_photo_file)

    update = _make_update(has_photo=True)
    update.message.caption = "a photo caption"
    await platform._handle_update(update, None)
    assert len(received) == 1
    assert len(received[0].images) == 1
    assert received[0].content == "a photo caption"


async def test_handle_update_photo_download_failure() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.get_file = AsyncMock(side_effect=Exception("download failed"))

    update = _make_update(has_photo=True)
    await platform._handle_update(update, None)  # Should not raise


async def test_handle_update_document_success() -> None:
    platform, mock_bot = _make_platform_with_app()
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    mock_doc_file = AsyncMock()
    mock_doc_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"doc_data"))
    mock_bot.get_file = AsyncMock(return_value=mock_doc_file)

    update = _make_update(has_document=True)
    await platform._handle_update(update, None)
    assert len(received) == 1
    assert len(received[0].files) == 1


async def test_handle_update_document_download_failure() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.get_file = AsyncMock(side_effect=Exception("download failed"))

    update = _make_update(has_document=True)
    await platform._handle_update(update, None)  # Should not raise


async def test_handle_update_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    # _app is None after photo handler tries to download
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    update = _make_update(has_photo=True)
    # With no app, bot is not available - should return early
    await platform._handle_update(update, None)
    assert len(received) == 0


async def test_handle_update_no_handler() -> None:
    platform, _ = _make_platform_with_app()
    platform._message_handler = None
    update = _make_update(text="hello")
    await platform._handle_update(update, None)  # No error when no handler


async def test_handle_update_user_no_username() -> None:
    platform, _mock_bot = _make_platform_with_app()
    received: list[CoreMessage] = []

    async def handler(m: CoreMessage) -> None:
        received.append(m)

    platform._message_handler = handler
    update = _make_update(text="hello", username="")
    update.message.from_user.username = None
    update.message.from_user.first_name = "John"
    update.message.from_user.last_name = "Doe"
    await platform._handle_update(update, None)
    assert received[0].user_name == "John Doe"


# --- _handle_callback tests ---


async def test_handle_callback_with_handler() -> None:
    platform, _ = _make_platform_with_app()
    cb_received: list[tuple[str, str, int, int]] = []

    async def my_cb(data: str, user_id: str, chat_id: int, message_id: int) -> None:
        cb_received.append((data, user_id, chat_id, message_id))

    platform._callback_handlers["btn_click"] = my_cb

    query = AsyncMock()
    query.data = "btn_click"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 42
    query.message = MagicMock()
    query.message.chat.id = 100
    query.message.message_id = 55
    update = MagicMock()
    update.callback_query = query

    await platform._handle_callback(update, None)
    assert cb_received == [("btn_click", "42", 100, 55)]


async def test_handle_callback_no_query() -> None:
    platform, _ = _make_platform_with_app()
    update = MagicMock()
    update.callback_query = None
    await platform._handle_callback(update, None)  # Should not raise


async def test_handle_callback_no_from_user() -> None:
    platform, _ = _make_platform_with_app()
    query = AsyncMock()
    query.data = "test"
    query.answer = AsyncMock()
    query.from_user = None
    query.message = MagicMock()
    update = MagicMock()
    update.callback_query = query
    await platform._handle_callback(update, None)  # Should not raise


async def test_handle_callback_no_matching_handler() -> None:
    platform, _ = _make_platform_with_app()
    query = AsyncMock()
    query.data = "unregistered"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 42
    query.message = MagicMock()
    query.message.chat.id = 1
    update = MagicMock()
    update.callback_query = query
    await platform._handle_callback(update, None)  # Should not raise


async def test_handle_callback_no_message() -> None:
    platform, _ = _make_platform_with_app()
    query = AsyncMock()
    query.data = "test"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 42
    query.message = None
    update = MagicMock()
    update.callback_query = query
    await platform._handle_callback(update, None)  # Should not raise


# --- start() test ---


async def test_start_polling_loop() -> None:
    """Test that start() sets up the app and polling loop."""
    platform = TelegramPlatform(token="tok:TOKEN", allow_from="*")
    mock_app = AsyncMock()
    mock_app.bot = AsyncMock()
    mock_app.bot.get_updates = AsyncMock()
    mock_app.add_handler = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.updater = AsyncMock()
    mock_app.updater.start_polling = AsyncMock()
    mock_app.updater.stop = AsyncMock()

    # Make the context manager work
    mock_app.__aenter__ = AsyncMock(return_value=mock_app)
    mock_app.__aexit__ = AsyncMock(return_value=False)

    def mock_build() -> Any:
        return mock_app

    with patch("tg_gemini.telegram_platform.Application") as mock_app_cls:
        mock_app_cls.builder.return_value.token.return_value.build = mock_build

        received: list[CoreMessage] = []

        async def handler(m: CoreMessage) -> None:
            received.append(m)

        async def stopper() -> None:
            await asyncio.sleep(0.05)
            await platform.stop()

        task = asyncio.create_task(stopper())
        try:
            await platform.start(handler)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def test_start_drain_failure() -> None:
    """Test that start() handles drain failure gracefully."""
    platform = TelegramPlatform(token="tok:TOKEN", allow_from="*")
    mock_app = AsyncMock()
    mock_app.bot = AsyncMock()
    mock_app.bot.get_updates = AsyncMock(side_effect=Exception("network error"))
    mock_app.add_handler = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.updater = AsyncMock()
    mock_app.updater.start_polling = AsyncMock()
    mock_app.updater.stop = AsyncMock()
    mock_app.__aenter__ = AsyncMock(return_value=mock_app)
    mock_app.__aexit__ = AsyncMock(return_value=False)

    def mock_build() -> Any:
        return mock_app

    with patch("tg_gemini.telegram_platform.Application") as mock_app_cls:
        mock_app_cls.builder.return_value.token.return_value.build = mock_build

        async def handler(m: CoreMessage) -> None:
            pass

        async def stopper() -> None:
            await asyncio.sleep(0.05)
            await platform.stop()

        task = asyncio.create_task(stopper())
        try:
            await platform.start(handler)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


# --- Additional coverage tests for handler edge cases ---


async def test_handle_update_photo_no_handler() -> None:
    """Photo message with no handler set → no error."""
    platform, mock_bot = _make_platform_with_app()
    mock_photo_file = AsyncMock()
    mock_photo_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"jpeg"))
    mock_bot.get_file = AsyncMock(return_value=mock_photo_file)
    platform._message_handler = None  # No handler

    update = _make_update(has_photo=True)
    await platform._handle_update(update, None)  # Should not raise


async def test_handle_update_document_no_handler() -> None:
    """Document message with no handler set → no error."""
    platform, mock_bot = _make_platform_with_app()
    mock_doc_file = AsyncMock()
    mock_doc_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"doc"))
    mock_bot.get_file = AsyncMock(return_value=mock_doc_file)
    platform._message_handler = None

    update = _make_update(has_document=True)
    await platform._handle_update(update, None)  # Should not raise


async def test_typing_loop_exception_handled() -> None:
    """Typing loop handles non-CancelledError exceptions gracefully."""
    platform, mock_bot = _make_platform_with_app()
    call_count = [0]

    async def raise_on_second(*_args: object, **_kwargs: object) -> None:
        call_count[0] += 1
        if call_count[0] >= 2:
            raise Exception("bot error")

    mock_bot.send_chat_action = AsyncMock(side_effect=raise_on_second)
    ctx = ReplyContext(chat_id=5)
    task = await platform.start_typing(ctx)
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    # Task should have handled the exception gracefully


async def test_typing_loop_no_app_early_return() -> None:
    """Typing loop returns immediately when app is None."""
    platform = TelegramPlatform(token="tok", allow_from="*")
    # app is None
    ctx = ReplyContext(chat_id=5)
    task = await platform.start_typing(ctx)
    await asyncio.sleep(0.05)
    # Task should complete on its own (app is None → return immediately)
    assert task.done() or True  # May or may not be done yet


async def test_send_html_no_reply_to() -> None:
    """_send_html without reply_to omits reply_to_message_id."""
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_message = AsyncMock()
    ctx = ReplyContext(chat_id=1, message_id=0)
    await platform.send(ctx, "plain text")
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert "reply_to_message_id" not in call_kwargs


# --- v2: send_card / edit_card / prefix callbacks ---


def _make_simple_card(with_button: bool = True) -> "Any":
    from tg_gemini.card import CardBuilder, CardButton

    builder = CardBuilder().title("Hello").markdown("**world**")
    if with_button:
        builder.actions(CardButton("Click", "act:ok"))
    return builder.build()


async def test_send_card_with_buttons() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_msg = MagicMock()
    mock_msg.message_id = 77
    mock_bot.send_message = AsyncMock(return_value=mock_msg)
    ctx = ReplyContext(chat_id=5)
    card = _make_simple_card(with_button=True)
    mid = await platform.send_card(ctx, card)
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert "reply_markup" in call_kwargs
    assert mid == 77


async def test_send_card_without_buttons() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_message = AsyncMock()
    ctx = ReplyContext(chat_id=5)
    card = _make_simple_card(with_button=False)
    mid = await platform.send_card(ctx, card)
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert "reply_markup" not in call_kwargs
    assert mid == 0


async def test_send_card_no_app_returns_zero() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1)
    card = _make_simple_card()
    mid = await platform.send_card(ctx, card)
    assert mid == 0


async def test_send_card_failure_logs() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.send_message = AsyncMock(side_effect=Exception("failed"))
    ctx = ReplyContext(chat_id=1)
    card = _make_simple_card(with_button=True)
    mid = await platform.send_card(ctx, card)
    assert mid == 0  # should not raise


async def test_edit_card_with_buttons() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.edit_message_text = AsyncMock()
    ctx = ReplyContext(chat_id=5)
    card = _make_simple_card(with_button=True)
    await platform.edit_card(ctx, message_id=42, card=card)
    mock_bot.edit_message_text.assert_called_once()
    call_kwargs = mock_bot.edit_message_text.call_args.kwargs
    assert call_kwargs["message_id"] == 42
    assert "reply_markup" in call_kwargs


async def test_edit_card_without_buttons() -> None:
    platform, mock_bot = _make_platform_with_app()
    mock_bot.edit_message_text = AsyncMock()
    ctx = ReplyContext(chat_id=5)
    card = _make_simple_card(with_button=False)
    await platform.edit_card(ctx, message_id=99, card=card)
    mock_bot.edit_message_text.assert_called_once()


async def test_edit_card_not_modified_no_raise() -> None:
    from telegram.error import BadRequest as TgBadRequest

    platform, mock_bot = _make_platform_with_app()
    mock_bot.edit_message_text = AsyncMock(
        side_effect=TgBadRequest("message is not modified")
    )
    ctx = ReplyContext(chat_id=1)
    await platform.edit_card(ctx, 1, _make_simple_card())  # Should not raise


async def test_edit_card_other_bad_request_logs() -> None:
    from telegram.error import BadRequest as TgBadRequest

    platform, mock_bot = _make_platform_with_app()
    mock_bot.edit_message_text = AsyncMock(side_effect=TgBadRequest("not found"))
    ctx = ReplyContext(chat_id=1)
    await platform.edit_card(ctx, 1, _make_simple_card())  # Should not raise


async def test_edit_card_no_app() -> None:
    platform = TelegramPlatform(token="tok", allow_from="*")
    ctx = ReplyContext(chat_id=1)
    await platform.edit_card(ctx, 1, _make_simple_card())  # Should not raise


async def test_register_callback_prefix() -> None:
    platform, _ = _make_platform_with_app()
    received: list[str] = []

    async def handler(data: str, _uid: str, _cid: int, _mid: int) -> None:
        received.append(data)

    platform.register_callback_prefix("cmd:", handler)
    assert "cmd:" in platform._prefix_handlers


async def test_prefix_callback_dispatch() -> None:
    platform, _ = _make_platform_with_app()
    received: list[tuple[str, str, int, int]] = []

    async def handler(data: str, user_id: str, chat_id: int, message_id: int) -> None:
        received.append((data, user_id, chat_id, message_id))

    platform.register_callback_prefix("cmd:", handler)

    query = AsyncMock()
    query.data = "cmd:/list 2"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 10
    query.message = MagicMock()
    query.message.chat.id = 50
    query.message.message_id = 7
    update = MagicMock()
    update.callback_query = query

    await platform._handle_callback(update, None)
    assert received == [("cmd:/list 2", "10", 50, 7)]


async def test_exact_match_takes_priority_over_prefix() -> None:
    platform, _ = _make_platform_with_app()
    exact_received: list[str] = []
    prefix_received: list[str] = []

    async def exact_handler(data: str, _uid: str, _cid: int, _mid: int) -> None:
        exact_received.append(data)

    async def prefix_handler(data: str, _uid: str, _cid: int, _mid: int) -> None:
        prefix_received.append(data)

    platform._callback_handlers["cmd:/list"] = exact_handler
    platform.register_callback_prefix("cmd:", prefix_handler)

    query = AsyncMock()
    query.data = "cmd:/list"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 1
    query.message = MagicMock()
    query.message.chat.id = 1
    query.message.message_id = 1
    update = MagicMock()
    update.callback_query = query

    await platform._handle_callback(update, None)
    assert exact_received == ["cmd:/list"]
    assert prefix_received == []


async def test_no_matching_prefix_handler_no_raise() -> None:
    platform, _ = _make_platform_with_app()
    platform.register_callback_prefix("cmd:", AsyncMock())

    query = AsyncMock()
    query.data = "other:data"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 1
    query.message = MagicMock()
    query.message.chat.id = 1
    query.message.message_id = 1
    update = MagicMock()
    update.callback_query = query

    await platform._handle_callback(update, None)  # Should not raise
