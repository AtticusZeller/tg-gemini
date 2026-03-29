# Plan: Fix `set_commands_menu` 403 Forbidden

## 问题

启动时日志显示：
```
WARNING failed to set commands menu , error=Forbidden('403: Forbidden')
```

`set_my_commands` API 调用返回 403。

## 可能原因分析

### 原因 1：Bot 权限不足（最可能）

Telegram Bot API 中 `setMyCommands` 需要 Bot 至少在一个群组/频道中有管理员权限。如果 Bot 从未加入过任何群组，或者所在群组中 Bot 没有管理员权限，API 调用会被拒绝。

**验证方法**：将 Bot 加入一个你管理员的群组，然后发送 `/setcommands`（通过 @BotFather）测试是否成功。

### 原因 2：时序问题

`_refresh_commands_menu` 作为 `on_started` 回调在 `updater.start_polling()` 后立即执行，此时 Bot API 内部状态可能未完全初始化。

**验证方法**：在 `set_commands_menu` 调用前后加日志，确认是第一次调用失败还是每次都失败。

### 原因 3：Python Telegram Bot 库问题

`python-telegram-bot` v21+ 中 `bot.set_my_commands()` 的调用方式可能与 API 文档不一致。

## 修复方案

### 方案 A：忽略错误 + 重试（快速修复）

在 `set_commands_menu` 中，如果失败则等待 2 秒后重试一次：

```python
async def set_commands_menu(self, commands: list[tuple[str, str]]) -> None:
    if self._app is None:
        return
    bot_commands = [BotCommand(name, desc[:100]) for name, desc in commands]
    try:
        await self._app.bot.set_my_commands(bot_commands)
        logger.info("commands menu set", count=len(bot_commands))
    except Exception as exc:
        logger.warning("failed to set commands menu, retrying...", error=exc)
        await asyncio.sleep(2)
        try:
            await self._app.bot.set_my_commands(bot_commands)
            logger.info("commands menu set (retry)", count=len(bot_commands))
        except Exception as exc2:
            logger.error("failed to set commands menu after retry", error=exc2)
```

### 方案 B：启动后延迟调用（时序修复）

不通过 `on_started` 回调，而是在事件循环稳定后调用：

```python
# engine.py start() 中
async def _run() -> None:
    await rate_limiter.start()
    try:
        await engine.start()
        # 等待 3 秒后刷新命令菜单（Bot API 上下文已就绪）
        await asyncio.sleep(3)
        await engine._refresh_commands_menu()
    finally:
        await rate_limiter.stop()
```

### 方案 C：诊断日志（调查用）

在 `set_commands_menu` 中增加更详细的日志：

```python
logger.warning("failed to set commands menu", error=exc, error_type=type(exc).__name__)
```

## 建议执行顺序

1. **先诊断**：添加详细日志，确认错误类型
2. **方案 B 最稳妥**：延迟调用确保 API 上下文就绪
3. **方案 A 作为补充**：重试机制处理偶发失败

## 验证

修复后重新启动，确认：
1. `INFO commands menu set` 日志出现（不再有 WARNING）
2. Telegram 中发送 `/help`，命令列表正确显示
