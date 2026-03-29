"""Tests for streaming.py: StreamPreview throttled message editing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from tg_gemini.config import StreamPreviewConfig
from tg_gemini.streaming import StreamPreview


def _make_preview(
    enabled: bool = True,
    interval_ms: int = 100,
    min_delta_chars: int = 5,
    max_chars: int = 0,
) -> tuple[StreamPreview, AsyncMock, AsyncMock, AsyncMock]:
    cfg = StreamPreviewConfig(
        enabled=enabled,
        interval_ms=interval_ms,
        min_delta_chars=min_delta_chars,
        max_chars=max_chars,
    )
    send_preview = AsyncMock(return_value=MagicMock())
    update_preview = AsyncMock()
    delete_preview = AsyncMock()
    preview = StreamPreview(cfg, send_preview, update_preview, delete_preview)
    return preview, send_preview, update_preview, delete_preview


async def test_append_text_disabled() -> None:
    preview, send, update, _ = _make_preview(enabled=False)
    await preview.append_text("hello world this is text")
    send.assert_not_called()
    update.assert_not_called()


async def test_append_text_sends_initial_preview() -> None:
    preview, send, _update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    send.assert_called_once_with("hello!")
    assert preview.full_text == "hello!"


async def test_append_text_updates_existing_preview() -> None:
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle

    await preview.append_text("hello!")
    send.assert_called_once()

    await preview.append_text(" world")
    update.assert_called_once_with(handle, "hello! world")


async def test_append_text_throttle_by_delta() -> None:
    """Small delta → schedule delayed flush, not immediate."""
    preview, send, update, _ = _make_preview(min_delta_chars=100, interval_ms=10000)
    handle = MagicMock()
    send.return_value = handle

    # First send (no last_sent_at)
    await preview.append_text("x" * 200)
    send.assert_called_once()

    send.reset_mock()
    # Small delta - should schedule, not send immediately
    await preview.append_text("y")  # only 1 char delta < 100
    update.assert_not_called()


async def test_append_text_schedules_flush() -> None:
    """Scheduled flush fires after delay."""
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=50)
    handle = MagicMock()
    send.return_value = handle

    # First chunk - enough delta, but interval must elapse
    await preview.append_text("hello!")
    send.assert_called_once()

    # Second chunk quickly - under interval so schedule
    update.reset_mock()
    await preview.append_text(" world")
    # Wait for scheduled flush
    await asyncio.sleep(0.2)  # > 50ms
    update.assert_called()


async def test_append_text_max_chars_truncation() -> None:
    preview, send, _, _ = _make_preview(min_delta_chars=1, interval_ms=0, max_chars=5)
    send.return_value = MagicMock()

    await preview.append_text("hello world")
    # Should be truncated to 5 chars + ellipsis
    call_arg = send.call_args[0][0]
    assert call_arg.startswith("hello")
    assert "…" in call_arg


async def test_append_text_degraded() -> None:
    preview, send, _update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    preview._degraded = True
    await preview.append_text("hello")
    send.assert_not_called()


async def test_send_preview_failure_degrades() -> None:
    preview, send, _update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    send.side_effect = Exception("API error")
    await preview.append_text("hello world!")
    assert preview._degraded is True


async def test_update_preview_failure_degrades() -> None:
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle

    await preview.append_text("hello!")
    update.side_effect = Exception("edit failed")
    await preview.append_text(" world")
    assert preview._degraded is True


async def test_freeze_cancels_pending_and_updates() -> None:
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle

    await preview.append_text("hello!")
    update.reset_mock()
    await preview.freeze()

    # After freeze, degraded
    assert preview._degraded is True
    # The freeze should have called update with current text
    update.assert_called_once_with(handle, "hello!")


async def test_freeze_no_preview_handle() -> None:
    preview, _send, update, _ = _make_preview()
    await preview.freeze()
    update.assert_not_called()
    assert preview._degraded is True


async def test_freeze_already_degraded() -> None:
    preview, _send, update, _ = _make_preview()
    preview._degraded = True
    preview._preview_handle = MagicMock()
    await preview.freeze()
    update.assert_not_called()


async def test_finish_returns_true_when_preview_active() -> None:
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle

    await preview.append_text("hello!")
    update.reset_mock()

    result = await preview.finish("final text")
    assert result is True
    update.assert_called_once_with(handle, "final text")


async def test_finish_returns_false_when_no_preview() -> None:
    preview, _send, _update, _ = _make_preview()
    result = await preview.finish("final text")
    assert result is False


async def test_finish_returns_false_when_empty_text() -> None:
    preview, send, _update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    result = await preview.finish("")
    assert result is False


async def test_finish_skips_identical_text_via_update() -> None:
    """If final_text == last_sent_text and last sent via update, skip update."""
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle

    await preview.append_text("hello!")
    # Force another update to set last_sent_via_update=True
    await preview.append_text(" world")  # This triggers update
    await asyncio.sleep(0)  # let any pending tasks settle

    # Now finish with exact same text
    full = preview.full_text
    # Manually set last_sent to full_text to simulate "already sent via update"
    preview._last_sent_text = full
    preview._last_sent_via_update = True
    update.reset_mock()

    result = await preview.finish(full)
    assert result is True
    update.assert_not_called()


async def test_finish_with_degraded_and_preview_handle_deletes() -> None:
    preview, send, _update, delete = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    preview._degraded = True

    result = await preview.finish("final")
    assert result is False
    delete.assert_called_once_with(handle)


async def test_finish_update_failure_deletes_preview() -> None:
    preview, send, update, delete = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    update.side_effect = Exception("edit failed")
    preview._degraded = False  # reset for finish test
    result = await preview.finish("final text")
    assert result is False
    delete.assert_called_once_with(handle)


async def test_detach_clears_handle() -> None:
    preview, send, _update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    assert preview._preview_handle is not None
    preview.detach()
    assert preview._preview_handle is None


async def test_full_text_property() -> None:
    preview, send, _, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    send.return_value = MagicMock()
    assert preview.full_text == ""
    await preview.append_text("abc")
    assert preview.full_text == "abc"
    await preview.append_text("def")
    assert preview.full_text == "abcdef"


async def test_cancel_scheduled_flush_on_freeze() -> None:
    """Scheduled flush task should be cancelled when freeze is called."""
    preview, send, _update, _ = _make_preview(min_delta_chars=100, interval_ms=10000)
    handle = MagicMock()
    send.return_value = handle

    # Trigger initial send
    await preview.append_text("x" * 200)
    send.assert_called_once()

    # Schedule a delayed flush
    await preview.append_text("y")  # small delta → schedule
    assert preview._flush_task is not None

    await preview.freeze()
    assert preview._flush_task is None


# --- Additional coverage tests ---


async def test_schedule_flush_already_scheduled() -> None:
    """_schedule_flush should not schedule a second task if already scheduled."""
    preview, send, _update, _ = _make_preview(min_delta_chars=100, interval_ms=10000)
    handle = MagicMock()
    send.return_value = handle

    # First: trigger initial send
    await preview.append_text("x" * 200)
    send.assert_called_once()

    # Second: small delta → triggers schedule
    await preview.append_text("y")
    task1 = preview._flush_task

    # Third: another small delta → should NOT create a new task
    await preview.append_text("z")
    task2 = preview._flush_task

    # Both references should be to the same task (or task1 might be None if it ran)
    assert task1 is task2 or task2 is None


async def test_do_flush_degraded_after_schedule() -> None:
    """If preview becomes degraded after a flush is scheduled, the do_flush should return early."""
    preview, send, update, _ = _make_preview(min_delta_chars=100, interval_ms=50)
    handle = MagicMock()
    send.return_value = handle

    # Trigger initial send
    await preview.append_text("x" * 200)
    send.assert_called_once()

    # Schedule a delayed flush (small delta)
    await preview.append_text("y")
    assert preview._flush_task is not None

    # Degrade the preview before the flush fires
    preview._degraded = True

    # Wait for scheduled flush to fire
    await asyncio.sleep(0.15)  # > 50ms

    # Should not have called update since we were degraded
    update.assert_not_called()


async def test_flush_locked_same_text_no_op() -> None:
    """_flush_locked should not update if display == last_sent_text."""
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle

    await preview.append_text("hello")
    send.assert_called_once_with("hello")

    # Manually set _last_sent_text to trigger the "same text" branch
    preview._last_sent_text = "hello"
    update.reset_mock()

    # Force direct call to _flush_locked
    async with preview._lock:
        await preview._flush_locked("hello")

    update.assert_not_called()


async def test_flush_locked_empty_text_no_op() -> None:
    """_flush_locked should not send empty text."""
    preview, send, _update, _ = _make_preview(min_delta_chars=1, interval_ms=0)

    async with preview._lock:
        await preview._flush_locked("")

    send.assert_not_called()


async def test_finish_delete_fails_gracefully() -> None:
    """finish() should not raise even if delete_preview raises."""
    preview, send, _update, delete = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    preview._degraded = True
    delete.side_effect = Exception("delete failed")

    result = await preview.finish("final")
    assert result is False  # No crash


async def test_freeze_update_exception_handled() -> None:
    """freeze() should not raise even if update fails."""
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    update.side_effect = Exception("update failed during freeze")

    preview._degraded = False  # Reset to allow freeze to try update
    await preview.freeze()
    # Should not raise


async def test_finish_no_preview_and_no_handle() -> None:
    """finish() returns False when both no preview handle and not degraded."""
    preview, _send, update, _ = _make_preview()
    result = await preview.finish("text")
    assert result is False
    update.assert_not_called()


async def test_freeze_empty_full_text_no_update() -> None:
    """freeze() with empty _full_text should not call update_preview."""
    preview, send, update, _ = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle

    # Manually set the preview handle without any text
    await preview.append_text("x")  # sends initial preview
    preview._full_text = ""  # Reset to empty
    send.reset_mock()
    update.reset_mock()
    preview._degraded = False  # allow freeze to try update

    await preview.freeze()
    # Since full_text is empty, _update_preview should NOT be called
    update.assert_not_called()


async def test_finish_update_and_delete_both_fail() -> None:
    """finish() when update AND delete both fail should not crash."""
    preview, send, update, delete = _make_preview(min_delta_chars=1, interval_ms=0)
    handle = MagicMock()
    send.return_value = handle
    await preview.append_text("hello!")
    preview._degraded = False

    update.side_effect = Exception("update failed")
    delete.side_effect = Exception("delete also failed")

    result = await preview.finish("final text")
    assert result is False  # Should complete without raising
