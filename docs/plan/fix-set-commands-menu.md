# Plan: Fix `set_commands_menu` 403 Forbidden

## 问题

启动时日志显示：
```
WARNING failed to set commands menu , error=Forbidden('403: Forbidden')
```

`set_my_commands` API 调用返回 403。

## 可能原因分析

### 原因 1：Bot 权限不足

Telegram Bot API 中 `setMyCommands` 需要 Bot 至少在一个群组/频道中有管理员权限。如果 Bot 从未加入过任何群组，API 调用会被拒绝。

### 原因 2：时序问题（主要）

`_refresh_commands_menu` 作为 `on_started` 回调在 `updater.start_polling()` 后立即执行，此时 Bot API 内部状态可能未完全初始化。

## 已实施修复（方案 B 变体）

不通过 `on_started` 回调，而是在事件循环稳定后调用。通过在 `TelegramPlatform.start()` 中添加 `on_started` 参数，在 `app.start()` + `updater.start_polling()` 后立即调用：

```python
# telegram_platform.py
async def start(
    self,
    handler: MessageHandlerType,
    on_started: Callable[[], Awaitable[None]] | None = None,
) -> None:
    ...
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        if on_started:
            await on_started()  # Bot API 上下文已就绪
        try:
            while self._app is not None:
                await asyncio.sleep(0.5)
        finally:
            ...

# engine.py
async def start(self) -> None:
    self._platform.register_callback_prefix("cmd:", ...)
    await self._platform.start(
        self.handle_message, on_started=self._refresh_commands_menu
    )
```

## 仍存在的问题

如果 Bot 从未加入任何群组/频道，`set_my_commands` API 仍会返回 403（原因 1）。这是 Telegram API 限制，非代码问题。**解决方案**：将 Bot 加入一个你管理员的群组即可。

## 验证

1. `INFO commands menu set` 日志出现（不再有 WARNING）→ 成功
2. Telegram 中发送 `/help`，命令列表正确显示 → 成功
3. 仍报 WARNING → Bot 需要先加入一个群组
