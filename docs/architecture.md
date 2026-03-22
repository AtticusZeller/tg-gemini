# 架构设计

## 概览

tg-gemini 是一个极简中间件，单向链路：

```
手机 Telegram  ──→  tg-gemini (VPS)  ──→  gemini CLI (本地)
     ↑                                          │
     └──────────── 流式响应 ←───────────────────┘
```

**设计原则：**
- 单平台（Telegram），单 Agent（Gemini CLI）
- 不重复造轮子——直接调用 `gemini -p` 命令行
- 流式输出：Gemini 输出一段，Telegram 预览消息即时更新

## 组件关系图

```
┌─────────────────────────────────────────────────────────┐
│                      tg-gemini 进程                      │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │  cli.py  │───▶│engine.py │───▶│   gemini.py      │  │
│  │  typer   │    │ 消息路由  │    │ subprocess 包装   │  │
│  └──────────┘    └────┬─────┘    └──────────────────┘  │
│                       │                    │             │
│  ┌──────────────────┐ │  ┌─────────────┐  │             │
│  │telegram_platform │◀┘  │ streaming.py│◀─┘             │
│  │ python-tg-bot    │    │ 流式预览节流  │               │
│  └──────────────────┘    └─────────────┘               │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │config.py │  │session.py│  │markdown  │  │i18n.py │  │
│  │pydantic  │  │会话管理   │  │转换器     │  │中英双语 │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │card.py   │  │ratelimit │  │dedup.py  │              │
│  │卡片 UI   │  │速率限制   │  │消息去重   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                                         │
│  ┌────────────────┐  ┌──────────────────┐              │
│  │ commands.py    │  │ skills.py        │              │
│  │ .gemini/cmds   │  │ .gemini/skills   │              │
│  └────────────────┘  └──────────────────┘              │
└─────────────────────────────────────────────────────────┘
         │                              ▲
         ▼                              │
┌─────────────────┐           ┌─────────────────┐
│  Telegram API   │           │  gemini CLI     │
│  长轮询          │           │  --output-format│
│  消息接收/发送    │           │  stream-json    │
└─────────────────┘           └─────────────────┘
```

## 消息处理数据流

```
用户发 Telegram 消息
        │
        ▼
TelegramPlatform._handle_update()
  ├─ 过滤旧消息（>30s 丢弃）
  ├─ 验证 allow_from 白名单
  ├─ 群聊过滤（group_reply_all / @mention / reply-to-bot）
  ├─ 生成 session_key（per-user 或 shared）
  ├─ 提取文本/图片/文件
  └─ 构造 CoreMessage → Engine.handle_message()
              │
              ▼
         Engine.handle_message()
           ├─ 空消息? → 忽略
           ├─ 消息去重（MessageDedup）
           ├─ 速率限制（RateLimiter）
           ├─ /command? → handle_command()
           ├─ Session 忙? → 加入队列（最多5条）
           └─ → _process() → _run_gemini()
                                  │
                                  ▼
                        GeminiSession.send()
                          asyncio.create_subprocess_exec(
                            "gemini", "--output-format", "stream-json",
                            "-p", prompt, ...
                          )
                                  │
                              JSONL 流
                                  │
                    ┌─────────────▼──────────────┐
                    │    _read_loop() 逐行解析     │
                    │  init → 存储 session_id     │
                    │  message(delta) → EventText  │
                    │  message(非delta) → 缓冲     │
                    │  tool_use → 刷新缓冲为Thinking│
                    │  tool_result → EventToolResult│
                    │  error → EventError          │
                    │  result → 刷新缓冲为Text      │
                    └─────────────┬──────────────┘
                                  │ asyncio.Queue[Event]
                                  ▼
                         Engine._run_gemini() 消费事件
                           TEXT → StreamPreview.append_text()
                           THINKING → 发送 <i>思考中...</i>
                           TOOL_USE → freeze预览 + 发送工具通知
                           TOOL_RESULT → 发送结果摘要（quiet模式跳过）
                           ERROR → 发送错误消息
                           RESULT → preview.finish() 或 platform.reply()
                                  → session.add_history()（记录历史）
```

## 文件结构

```
src/tg_gemini/
├── __init__.py          # 版本号（importlib.metadata）
├── cli.py               # typer 入口：tg-gemini start
├── config.py            # pydantic v2 TOML 配置，frozen + extra=forbid
├── engine.py            # 消息路由、命令分发、事件循环、回调处理
├── gemini.py            # GeminiAgent + GeminiSession（子进程 + JSONL 解析）
├── commands.py          # CommandLoader：自动加载 .gemini/commands/*.toml
├── skills.py            # SkillRegistry：自动加载 .gemini/skills/*/SKILL.md
├── markdown.py          # Obsidian MD → Telegram HTML 转换器
├── models.py            # 共享数据类：Event、Message、ReplyContext 等
├── i18n.py              # 中英双语消息（EN/ZH）
├── session.py           # SessionManager（多会话 + 历史 + JSON 持久化）
├── streaming.py         # StreamPreview 节流更新
├── telegram_platform.py # python-telegram-bot v21+ 平台封装
├── card.py              # CardBuilder 卡片 UI（HTML + InlineKeyboardMarkup）
├── ratelimit.py         # 滑动窗口速率限制器
└── dedup.py             # TTL 消息去重

tests/                   # 717 个测试，98.52% 覆盖率
├── test_config.py
├── test_engine.py
├── test_gemini.py
├── test_i18n.py
├── test_markdown.py
├── test_models.py
├── test_session.py
├── test_streaming.py
├── test_telegram.py
├── test_cli.py
├── test_card.py
├── test_ratelimit.py
├── test_dedup.py
├── test_commands.py
└── test_skills.py
```

## 关键设计决策

### Session Key 格式

```
私聊 / 群聊独立模式：  telegram:{chat_id}:{user_id}
群聊共享模式：         telegram:{chat_id}:shared
```

同一用户在不同群组有不同 session。

### 对话 Resume 机制

```
第一轮：gemini --output-format stream-json -p "你好"
  → init 事件携带 session_id: "abc123"
  → 存入 session.agent_session_id

第二轮：gemini --output-format stream-json --resume abc123 -p "继续话题"
  → Gemini CLI 加载 ~/.gemini/tmp/.../chats/session-abc123.json
```

### 并发保护

每个 Session 有一个 `asyncio.Lock`：
- `try_lock()` 失败 → 消息加入队列（上限 5 条）→ 回复「⏳ Agent 正忙」
- 处理完成后 `unlock()` → 自动从队列取下一条

### 流式预览节流

Telegram 限制：同一消息每秒最多编辑 1 次。StreamPreview 实现滑动窗口节流：
- 距上次发送 ≥ `interval_ms` 且 新增 ≥ `min_delta_chars` → 立即 flush
- 否则 → 延迟到下一个 interval
- `finish()` 时始终发送完整文本（不受 `max_chars` 限制）

详细实现见 [internals.md](internals.md)。
