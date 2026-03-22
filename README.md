# tg-gemini

<div align="center">

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://github.com/atticuszeller/tg-gemini)
[![Test](https://github.com/atticuszeller/tg-gemini/actions/workflows/main.yml/badge.svg)](https://github.com/atticuszeller/tg-gemini/actions/workflows/main.yml)

**Telegram ↔ Gemini CLI 中间件**

在 VPS 上持续运行，将 Telegram 消息转发给 `gemini -p --output-format stream-json`，实时流式返回响应。

</div>

---

## 目录

- [项目定位](#项目定位)
- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [安装](#安装)
- [配置参考](#配置参考)
- [CLI 命令](#cli-命令)
- [Telegram Bot 命令](#telegram-bot-命令)
- [模块参考](#模块参考)
- [Gemini stream-json 协议](#gemini-stream-json-协议)
- [Markdown 转换](#markdown-转换)
- [流式预览机制](#流式预览机制)
- [会话管理](#会话管理)
- [开发指南](#开发指南)

---

## 项目定位

tg-gemini 是一个**极简中间件**，只做一件事：

```
手机 Telegram  ──→  tg-gemini (VPS)  ──→  gemini CLI (本地)
     ↑                                          │
     └──────────── 流式响应 ←───────────────────┘
```

**设计原则：**
- 单平台（Telegram），单 Agent（Gemini CLI）
- 不重复造轮子——直接调用 `gemini -p` 命令行
- 流式输出：Gemini 输出一段，Telegram 预览消息即时更新
- Obsidian Markdown → Telegram HTML 无损转换

**对比 cc-connect（Go 版本）：**

| 特性 | cc-connect | tg-gemini |
|------|-----------|-----------|
| 平台 | 多平台 | 仅 Telegram |
| Agent | 多 Agent | 仅 Gemini CLI |
| 代码量 | ~15000 行 | ~800 行 |
| 安装 | 编译 Go | `pip install tg-gemini` |

---

## 架构设计

### 组件关系图

```
┌─────────────────────────────────────────────────────────┐
│                      tg-gemini 进程                      │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │  cli.py  │───▶│engine.py │───▶│   gemini.py      │  │
│  │  typer   │    │ 消息路由  │    │ subprocess包装    │  │
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
└─────────────────────────────────────────────────────────┘
         │                              ▲
         ▼                              │
┌─────────────────┐           ┌─────────────────┐
│  Telegram API   │           │  gemini CLI     │
│  长轮询          │           │  --output-format│
│  消息接收/发送    │           │  stream-json    │
└─────────────────┘           └─────────────────┘
```

### 消息处理数据流

```
用户发 Telegram 消息
        │
        ▼
TelegramPlatform._handle_update()
  ├─ 过滤旧消息（>30s 丢弃）
  ├─ 验证 allow_from 白名单
  ├─ 提取文本/图片/文件
  └─ 构造 CoreMessage → Engine.handle_message()
              │
              ▼
         Engine.handle_message()
           ├─ 空消息? → 忽略
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
                           TOOL_RESULT → 发送结果摘要
                           ERROR → 发送错误消息
                           RESULT → preview.finish() 或 platform.reply()
```

### 文件结构

```
src/tg_gemini/
├── __init__.py          # 版本号
├── cli.py               # typer 入口：tg-gemini start
├── config.py            # pydantic v2 TOML 配置
├── engine.py            # 消息路由、命令分发、事件循环
├── gemini.py            # GeminiAgent + GeminiSession（子进程 + JSONL）
├── markdown.py          # Obsidian MD → Telegram HTML 转换器
├── models.py            # 共享数据类：Event、Message、Session 等
├── i18n.py              # 中英双语消息（EN/ZH）
├── session.py           # 会话管理器（asyncio 锁 + JSON 持久化）
├── streaming.py         # StreamPreview 节流更新
└── telegram_platform.py # python-telegram-bot v21+ 平台封装

tests/
├── test_config.py
├── test_engine.py
├── test_gemini.py
├── test_i18n.py
├── test_markdown.py
├── test_models.py
├── test_session.py
├── test_streaming.py
├── test_telegram.py
└── test_cli.py
```

---

## 快速开始

### 前置条件

1. **Python 3.12+** 和 **uv**
2. **Gemini CLI** 已安装并登录：
   ```bash
   npm install -g @google/gemini-cli
   gemini  # 完成首次登录
   ```
3. **Telegram Bot Token**：通过 [@BotFather](https://t.me/botfather) 创建

### 5 分钟上手

```bash
# 1. 安装
pip install tg-gemini
# 或使用 uv
uv tool install tg-gemini

# 2. 创建配置
mkdir -p ~/.tg-gemini
cat > ~/.tg-gemini/config.toml << 'EOF'
[telegram]
token = "123456:ABC-DEF..."
allow_from = "你的Telegram用户ID"

[gemini]
work_dir = "/path/to/your/project"
EOF

# 3. 启动
tg-gemini start

# 或指定配置文件
tg-gemini start --config /path/to/config.toml
```

---

## 安装

### 从 PyPI 安装

```bash
pip install tg-gemini
```

### 使用 uv（推荐）

```bash
# 作为工具安装（全局可用）
uv tool install tg-gemini

# 在项目中安装
uv add tg-gemini
```

### 从源码安装（开发模式）

```bash
git clone https://github.com/atticuszeller/tg-gemini
cd tg-gemini
uv sync --all-groups
# 此时 tg-gemini 命令即可用
```

---

## 配置参考

配置文件为 TOML 格式。路径解析优先级：

1. `--config` 参数指定的路径
2. 当前目录的 `config.toml`
3. `~/.tg-gemini/config.toml`（默认）

### 完整配置示例

```toml
# ~/.tg-gemini/config.toml

# ── Telegram ──────────────────────────────────────────────
[telegram]
# BotFather 给的 Bot Token（必填）
token = "123456:ABC-DEFghijklmno..."

# 白名单："*" 允许所有人，或逗号分隔的用户 ID
# 查找自己的 ID：向 @userinfobot 发消息
allow_from = "123456789,987654321"


# ── Gemini CLI ────────────────────────────────────────────
[gemini]
# gemini 命令的工作目录（影响 Gemini 能访问哪些文件）
work_dir = "/home/user/projects/myproject"

# 模型名称（空字符串 = 使用 CLI 默认值）
# 可选：gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite
model = ""

# 审批模式
# default   = 每次工具调用都需要确认（注意：无交互，建议用 yolo）
# auto_edit = 自动批准文件编辑类操作
# yolo      = 自动批准所有操作（-y 标志）
# plan      = 只读计划模式
mode = "yolo"

# Gemini API Key（可选，也可设置环境变量 GEMINI_API_KEY）
api_key = ""

# gemini 可执行文件名（PATH 中可找到即可）
cmd = "gemini"

# 每轮超时分钟数（0 = 不限制）
timeout_mins = 0


# ── 数据目录 ──────────────────────────────────────────────
# 存放 sessions.json 等持久化数据
data_dir = "~/.tg-gemini"

# ── 语言 ──────────────────────────────────────────────────
# "" = 自动检测（根据用户消息中是否含 CJK 字符判断）
# "en" = 强制英文
# "zh" = 强制中文
language = ""


# ── 日志 ──────────────────────────────────────────────────
[log]
# 日志级别：DEBUG, INFO, WARNING, ERROR
level = "INFO"


# ── 显示设置 ──────────────────────────────────────────────
[display]
# Thinking 消息最大显示字符数（截断后加 …）
thinking_max_len = 300

# 工具调用参数最大显示字符数
tool_max_len = 500


# ── 流式预览 ──────────────────────────────────────────────
[stream_preview]
# 是否开启流式预览（边生成边更新 Telegram 消息）
enabled = true

# 两次更新之间最小间隔（毫秒）——避免触发 Telegram 限流
interval_ms = 1500

# 每次更新最少新增字符数（累积够了才更新）
min_delta_chars = 30

# 预览消息最大字符数（超出部分加 … 截断，finish 时发完整响应）
max_chars = 2000
```

### 配置项速查表

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `telegram.token` | str | **必填** | Bot Token |
| `telegram.allow_from` | str | `"*"` | 用户白名单 |
| `gemini.work_dir` | str | `"."` | CLI 工作目录 |
| `gemini.model` | str | `""` | 模型名，空=CLI默认 |
| `gemini.mode` | str | `"default"` | `default/auto_edit/yolo/plan` |
| `gemini.api_key` | str | `""` | API Key（可选） |
| `gemini.cmd` | str | `"gemini"` | 可执行文件名 |
| `gemini.timeout_mins` | int | `0` | 子进程超时分钟（0=不限，超时后自动 kill） |
| `data_dir` | str | `"~/.tg-gemini"` | 数据目录 |
| `language` | str | `""` | 语言，空=自动 |
| `log.level` | str | `"INFO"` | 日志级别 |
| `display.thinking_max_len` | int | `300` | 思考文本截断长度 |
| `display.tool_max_len` | int | `500` | 工具参数截断长度 |
| `stream_preview.enabled` | bool | `true` | 开启流式预览 |
| `stream_preview.interval_ms` | int | `1500` | 最小更新间隔(ms) |
| `stream_preview.min_delta_chars` | int | `30` | 最小更新字符增量 |
| `stream_preview.max_chars` | int | `2000` | 预览最大字符数 |

---

## CLI 命令

### `tg-gemini start`

启动 bot 服务，长轮询等待 Telegram 消息。

```bash
tg-gemini start [OPTIONS]
```

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--config PATH` | `-c PATH` | 指定配置文件路径 |
| `--help` | `-h` | 显示帮助 |

**示例：**

```bash
# 使用默认配置（~/.tg-gemini/config.toml）
tg-gemini start

# 指定配置文件
tg-gemini start --config /etc/tg-gemini/prod.toml
tg-gemini start -c ~/work/config.toml

# 后台运行（systemd 或 nohup）
nohup tg-gemini start > /var/log/tg-gemini.log 2>&1 &
```

**退出：** `Ctrl+C` 优雅停止。

### 配置文件不存在时的错误

```
Config file not found: /path/to/config.toml
```

### 作为 systemd 服务运行

创建 `/etc/systemd/system/tg-gemini.service`：

```ini
[Unit]
Description=tg-gemini Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
ExecStart=/home/ubuntu/.local/bin/tg-gemini start --config /home/ubuntu/.tg-gemini/config.toml
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tg-gemini
sudo systemctl status tg-gemini
sudo journalctl -u tg-gemini -f
```

---

## Telegram Bot 命令

在 Telegram 对话框中输入以下命令：

### `/new` — 开启新会话

```
/new
```

清除当前会话上下文，从零开始与 Gemini 对话。适合切换任务场景。

**响应：**
- 🆕 New session started.（英文）
- 🆕 已开始新会话。（中文）

---

### `/help` — 查看帮助

```
/help
```

**响应示例（英文）：**
```
Commands: /new – new session | /stop – stop agent |
/model [name] – switch model | /mode [mode] – switch mode
(default/auto_edit/yolo/plan) | /help – this help
```

---

### `/stop` — 停止 Agent

```
/stop
```

发送 SIGTERM 终止当前正在运行的 Gemini 子进程（等待最多 3 秒后强制 SIGKILL）。

**响应：**
- 🛑 Agent stopped.

---

### `/model` — 查看/切换模型

```
# 查看当前模型和可用模型列表
/model

# 切换到指定模型
/model gemini-2.5-flash
/model gemini-2.5-pro
```

**查看响应示例：**
```
Current model: gemini-2.5-flash

  • gemini-2.5-pro
  • gemini-2.5-flash
  • gemini-2.5-flash-lite
  • gemini-2.0-flash
```

**切换响应：**
- ✅ Model switched to: gemini-2.5-flash

---

### `/mode` — 查看/切换模式

```
# 查看当前模式
/mode

# 切换模式
/mode default      # 标准模式（工具调用需确认，但无交互所以会卡住）
/mode auto_edit    # 自动批准文件编辑类操作
/mode yolo         # 全自动，适合自动化任务
/mode plan         # 只读计划模式，不执行工具
```

**模式说明：**

| 模式 | Gemini CLI 标志 | 适用场景 |
|------|----------------|---------|
| `default` | 无额外标志 | 谨慎使用，需手动确认工具调用 |
| `auto_edit` | `--approval-mode auto_edit` | 自动批准文件读写，其他需确认 |
| `yolo` | `-y` | 全自动，信任 Gemini 的判断 |
| `plan` | `--approval-mode plan` | 只读，仅生成计划不执行 |

---

### 普通消息

任何非 `/` 开头的消息都会直接发送给 Gemini：

```
帮我分析这个项目的架构

解释一下 src/main.py 的逻辑

写一个 Python 函数，计算斐波那契数列
```

### 发送图片

直接发送图片（可附带说明文字），图片会保存为临时文件并通过 `@filepath` 方式传给 Gemini：

```
[发送图片] 这个截图里的错误是什么原因？
```

### 发送文件

直接发送文档文件（PDF、代码文件等），同样通过临时文件传给 Gemini：

```
[发送 error.log] 分析这个日志文件
```

---

## 模块参考

### `models.py` — 数据模型

核心数据类，所有模块共享：

```python
class EventType(StrEnum):
    TEXT        # Gemini 输出的文本（delta 或最终）
    THINKING    # 思考过程文本（工具调用前的推理）
    TOOL_USE    # 工具调用（read_file, shell, 等）
    TOOL_RESULT # 工具执行结果
    ERROR       # 错误事件
    RESULT      # 会话结束（done=True，携带 session_id）

@dataclass
class Event:
    type: EventType
    content: str = ""        # 文本内容
    tool_name: str = ""      # 工具名 / 工具ID
    tool_input: str = ""     # 工具参数摘要
    session_id: str = ""     # Gemini 会话 ID（init 事件携带）
    done: bool = False       # RESULT 事件为 True
    error: Exception | None = None

@dataclass
class Message:
    session_key: str         # "telegram:{chatID}:{userID}"
    platform: str            # "telegram"
    user_id: str
    user_name: str
    content: str             # 消息文本
    message_id: str = ""
    chat_name: str = ""
    images: list[ImageAttachment] = ...
    files: list[FileAttachment] = ...
    reply_ctx: Any = None    # ReplyContext 实例
```

---

### `config.py` — 配置加载

```python
from tg_gemini.config import load_config, resolve_config_path

# 加载配置
cfg = load_config(Path("config.toml"))

# 自动解析路径（按优先级）
path = resolve_config_path(None)         # 使用默认路径
path = resolve_config_path("my.toml")   # 使用指定路径
```

---

### `gemini.py` — Gemini 子进程包装

#### `GeminiAgent` — 工厂类

```python
agent = GeminiAgent(
    work_dir="/my/project",
    model="gemini-2.5-flash",
    mode="yolo",
    cmd="gemini",
    api_key="",
    timeout_mins=0,
)

# 创建新会话
session = agent.start_session()

# 从已有 session_id 恢复对话
session = agent.start_session(resume_id="abc123-def456")

# 获取可用模型列表
models = agent.available_models()

# 运行时切换模型/模式
agent.model = "gemini-2.5-pro"
agent.mode = "auto_edit"
```

#### `GeminiSession` — 单轮对话

```python
# 发送消息（非阻塞，立即返回）
await session.send(
    prompt="分析这个文件",
    images=[ImageAttachment(mime_type="image/jpeg", data=bytes(...))],
    files=[FileAttachment(mime_type="text/plain", data=b"...", file_name="x.txt")],
)

# 消费事件（阻塞直到 RESULT 事件）
while True:
    event = await asyncio.wait_for(session.events.get(), timeout=120)
    if event.done:
        break
    # 处理 event...

# 获取会话 ID（用于下次 resume）
sid = session.current_session_id

# 终止子进程（SIGTERM → 3s → SIGKILL）
await session.kill()

# 关闭会话（标记 alive=False 并调用 kill）
await session.close()
```

**底层 CLI 调用示意：**

```bash
# 新会话
gemini --output-format stream-json -y -m gemini-2.5-flash -p "prompt"

# 恢复会话
gemini --output-format stream-json -y --resume abc123 -p "continuation"

# 带图片（临时文件路径前置）
gemini --output-format stream-json -y -p "/tmp/tg-gemini-img-0.jpg 分析图片"
```

---

### `streaming.py` — 流式预览

```python
preview = StreamPreview(
    config=cfg.stream_preview,
    send_preview=lambda text: platform.send_preview_start(ctx, text),
    update_preview=lambda handle, text: platform.update_message(handle, text),
    delete_preview=lambda handle: platform.delete_preview(handle),
)

# 追加文本（内部节流，不会每字都 API 调用）
await preview.append_text("Hello ")
await preview.append_text("World")

# 工具调用前冻结（停止更新）
await preview.freeze()

# 完成并发送最终文本（返回 True 表示预览已更新，无需再 reply）
sent = await preview.finish(full_text)
if not sent:
    await platform.reply(ctx, full_text)

# 分离预览消息（保留消息但停止追踪）
preview.detach()
```

**节流逻辑：**

```
新文本到达
    │
    ├─ 距上次发送 < interval_ms AND 新增 < min_delta_chars
    │       └─ 延迟 flush（不立即发）
    │
    ├─ 距上次发送 ≥ interval_ms OR 没有上次发送
    │       └─ 立即 flush
    │
    └─ max_chars 截断：超出部分显示为 "…"（finish 时发完整版）
```

---

### `telegram_platform.py` — Telegram 平台

```python
platform = TelegramPlatform(token="xxx", allow_from="*")

# 启动长轮询（阻塞）
await platform.start(engine.handle_message)

# 停止（在另一个协程中调用）
await platform.stop()

# 发送/回复
await platform.send(ctx, "消息内容（支持 Markdown）")
await platform.reply(ctx, "**bold** text")  # 作为回复发送

# 流式预览
handle = await platform.send_preview_start(ctx, "初始内容")
await platform.update_message(handle, "更新内容")
await platform.delete_preview(handle)

# 图片/文件
await platform.send_image(ctx, ImageAttachment(...))
await platform.send_file(ctx, FileAttachment(...))

# 打字指示器（返回 Task，cancel 停止）
typing_task = await platform.start_typing(ctx)
# ... 处理中 ...
typing_task.cancel()
```

---

### `session.py` — 会话管理

```python
manager = SessionManager(store_path=Path("~/.tg-gemini/sessions.json"))

# 获取或创建会话
session = manager.get_or_create("telegram:123:456")

# 开启新会话（替换旧的，持久化）
session = manager.new_session("telegram:123:456")

# 查询
session = manager.get("telegram:123:456")  # None 如果不存在

# Session 锁（防止并发处理同一用户的多条消息）
acquired = await session.try_lock()   # True = 成功
await session.unlock()                # 释放

# Gemini 会话 ID（用于对话 resume）
session.agent_session_id = "gemini-session-uuid"
```

**持久化格式（`sessions.json`）：**

```json
{
  "telegram:123456:789": {
    "id": "uuid-v4",
    "agent_session_id": "gemini-session-id",
    "created_at": "2024-01-01T10:00:00",
    "updated_at": "2024-01-01T10:30:00"
  }
}
```

---

### `markdown.py` — Markdown 转换器

将 Obsidian/标准 Markdown 转为 Telegram HTML：

```python
from tg_gemini.markdown import markdown_to_html, split_message

html = markdown_to_html("**粗体** 和 *斜体*")
# → "<b>粗体</b> 和 <i>斜体</i>"

# 自动分割超长消息（保持代码块完整）
chunks = split_message(long_html, max_len=4096)
```

**支持的转换：**

| Markdown 语法 | Telegram HTML |
|--------------|---------------|
| `**bold**` 或 `__bold__` | `<b>bold</b>` |
| `*italic*` | `<i>italic</i>` |
| `***bold italic***` | `<b><i>bold italic</i></b>` |
| `~~strike~~` | `<s>strike</s>` |
| `` `code` `` | `<code>code</code>` |
| ` ```python\ncode\n``` ` | `<pre><code class="language-python">code</code></pre>` |
| `[text](url)` | `<a href="url">text</a>` |
| `[[wikilink]]` | `wikilink`（纯文本） |
| `[[Link\|别名]]` | `别名`（纯文本） |
| `> blockquote` | `<blockquote>...</blockquote>` |
| `> [!NOTE] 标题` | `<blockquote><b>NOTE: 标题</b>...</blockquote>` |
| `# Heading` | `<b>Heading</b>` |
| `---` 或 `***` | `——————————` |
| `- item` 或 `* item` | `• item` |
| `1. item` | `1. item` |
| `\| col1 \| col2 \|` | `col1 \| col2`（纯文本表格） |
| `<`, `>`, `&`, `"` | HTML 实体转义 |

**消息分割（code fence 感知）：**

```
长消息：```python\ncode\n``` 刚好跨越 4096 边界

第一块：```python\n...\n```  ← 补全闭合 fence
第二块：```python\n...\n```  ← 重开 fence，内容连续
```

---

### `i18n.py` — 国际化

```python
from tg_gemini.i18n import I18n, Language, MsgKey

i18n = I18n(lang=Language.ZH)

# 翻译
msg = i18n.t(MsgKey.SESSION_NEW)      # "🆕 已开始新会话。"
msg = i18n.tf(MsgKey.MODEL_SWITCHED, "flash")  # "✅ 模型已切换为：flash"

# 自动检测语言（含 CJK 字符 → ZH，否则 → EN）
lang = I18n.detect_language("你好 world")  # Language.ZH
lang = I18n.detect_language("hello")       # Language.EN
```

**支持的消息键：**

| MsgKey | EN | ZH |
|--------|----|----|
| `HELP` | Commands: /new... | 命令：/new... |
| `SESSION_BUSY` | ⏳ Agent is busy... | ⏳ Agent 正忙... |
| `SESSION_NEW` | 🆕 New session started. | 🆕 已开始新会话。 |
| `MODEL_SWITCHED` | ✅ Model switched to: {} | ✅ 模型已切换为：{} |
| `MODE_SWITCHED` | ✅ Mode switched to: {} | ✅ 模式已切换为：{} |
| `STOP_OK` | 🛑 Agent stopped. | 🛑 Agent 已停止。 |
| `ERROR_PREFIX` | ❌ Error: {} | ❌ 错误：{} |
| `TOOL_USE` | 🔧 {}: {} | 🔧 {}：{} |
| `TOOL_RESULT` | 📋 Result: {} | 📋 结果：{} |
| `UNKNOWN_CMD` | Unknown command... | 未知命令... |
| `EMPTY_RESPONSE` | （no response） | （无响应） |

---

## Gemini stream-json 协议

tg-gemini 消费 `gemini --output-format stream-json` 的 JSONL 输出。

### 事件类型

#### `init` — 会话初始化

```json
{"type": "init", "session_id": "abc123-def456", "model": "gemini-2.5-flash"}
```

tg-gemini 处理：存储 `session_id` 供下次 `--resume` 使用。

#### `message` — 文本块

```json
{"type": "message", "role": "assistant", "content": "Hello", "delta": true}
```

- `delta: true` → 流式片段，立即作为 `EventText` 发出
- `delta: false`（或缺失）→ 完整消息，**缓冲**待分类

**缓冲分类规则：**
- 收到 `tool_use` 事件 → 缓冲内容作为 `EventThinking` 发出
- 收到 `result` 事件 → 缓冲内容作为 `EventText` 发出

#### `tool_use` — 工具调用

```json
{
  "type": "tool_use",
  "tool_name": "read_file",
  "tool_id": "read-abc123",
  "parameters": {"file_path": "/src/main.py"}
}
```

tg-gemini 处理：冻结预览 + 发送工具通知 `🔧 read_file: /src/main.py`。

**内置参数格式化规则：**

| 工具 | 显示格式 |
|------|---------|
| `shell` / `Bash` / `run_shell_command` | 命令字符串 |
| `read_file` / `ReadFile` | 文件路径 |
| `write_file` / `WriteFile` | `` `path`\n```\ncontent\n``` `` |
| `replace` / `ReplaceInFile` | `` `path`\n```diff\n...\n``` `` |
| `list_directory` | 目录路径 |
| `google_web_search` | 搜索词 |
| `web_fetch` | URL 或 prompt |
| 其他 | `key: value, ...` |

#### `tool_result` — 工具结果

```json
{"type": "tool_result", "tool_id": "read-abc123", "status": "success", "output": "content..."}
```

错误时：
```json
{"type": "tool_result", "tool_id": "...", "status": "error", "error": {"message": "..."}}
```

tg-gemini 处理：结果截断到 500 字符后作为 `📋 Result: ...` 发出。

#### `error` — 错误

```json
{"type": "error", "severity": "error", "message": "Something failed"}
```

tg-gemini 处理：作为 `❌ Error: [error] Something failed` 发出。

#### `result` — 会话结束

```json
{"type": "result", "status": "success", "stats": {"total_tokens": 500, ...}}
```

错误时：
```json
{"type": "result", "status": "error", "error": {"message": "Turn limit exceeded"}}
```

tg-gemini 处理：触发 `preview.finish()` → 发送最终响应。

### 典型事件流示例

```
init          → 存储 session_id
message(δ)    → "Let me " → 流式预览更新
message(δ)    → "check the "
message(δ)    → "file..."
message(非δ)  → "I need to read the source." → 缓冲
tool_use      → read_file → 刷新缓冲为 THINKING，冻结预览
tool_result   → "file content here" → 发送 📋 Result
message(δ)    → "Based on " → 新预览开始
message(δ)    → "the code..."
result        → finish(full_text) → 最终更新预览
```

---

## Markdown 转换

### 处理流程

```
输入 Markdown
      │
      ▼
逐行扫描（状态机）
  ├─ 代码块 (```) → 缓冲代码行 → <pre><code class="language-X">...</code></pre>
  ├─ 引用块 (>) → 缓冲引用行 → <blockquote>...</blockquote>
  │   └─ Obsidian callout (> [!TYPE] Title) → <blockquote><b>TYPE: Title</b>...</blockquote>
  ├─ 表格 (|...|) → 缓冲表格行 → "col1 | col2" 纯文本
  ├─ 标题 (#) → <b>text</b>
  ├─ 分割线 (---/***) → ——————————
  ├─ 无序列表 (- /*) → • item
  ├─ 有序列表 (1.) → 1. item
  └─ 普通行 → convertInlineHTML()
                  │
                  ▼
          内联转换（占位符保护机制）
            1. 内联代码 → 占位符
            2. 链接 → 占位符
            3. Wikilink → 纯文本
            4. HTML 转义（&, <, >, "）
            5. ***粗斜体*** → 占位符
            6. **粗体**/__粗体__ → 占位符
            7. ~~删除线~~ → 占位符
            8. *斜体* → <i>...</i>
            9. 恢复所有占位符
```

### 占位符机制

避免多轮正则替换互相干扰：

```python
# 第1轮：提取内联代码为占位符
"`code`" → "\x00PH0\x00"

# 第2轮：提取链接为占位符
"[text](url)" → "\x00PH1\x00"

# 第4轮：HTML 转义剩余文本（占位符不受影响）
"a & b" → "a &amp; b"

# 最后：恢复所有占位符
"\x00PH0\x00" → "<code>code</code>"
"\x00PH1\x00" → '<a href="url">text</a>'
```

---

## 流式预览机制

### 为什么需要节流？

Telegram Bot API 限制：同一消息每秒最多 **1次** 编辑（全局限制更低）。直接把每个字符都 edit 会触发 `429 Too Many Requests`。

### 节流策略

```
append_text("x") 被调用
        │
        ├─ 没有上次发送记录（第一次）
        │       └─ 立即 flush
        │
        ├─ 距上次发送 >= interval_ms (1500ms)
        │   AND 新增字符 >= min_delta_chars (30)
        │       └─ 立即 flush
        │
        └─ 否则
                └─ 延迟 flush（distance_to_next_interval 后触发）
                   如果已有延迟任务：不重复创建
```

### 预览生命周期

```
消息开始处理
    │
    ├─ 第一个 TEXT chunk → send_preview_start() → 新消息 (预览消息)
    │                                              handle = PreviewHandle(chat_id, msg_id)
    │
    ├─ 后续 TEXT chunk → update_message(handle, text) → 编辑预览消息
    │
    ├─ TOOL_USE → freeze() → 最后编辑一次 + 停止更新 + detach()
    │             (预览消息成为永久消息，工具通知另发新消息)
    │
    └─ RESULT → finish(full_text)
                    ├─ 成功 → update_message(handle, full_text) → return True
                    │         （调用方跳过 reply）
                    └─ 失败 → delete_preview(handle) → return False
                              （调用方另发新消息）
```

### max_chars 截断说明

预览期间超过 `max_chars` 的部分显示为 `…`，但 `finish()` 时总是发送完整文本（不受此限制）。这是有意为之——预览只是中间状态，最终响应不被截断。

---

## 会话管理

### 会话键格式

```
telegram:{chat_id}:{user_id}
```

例：`telegram:123456789:987654321`

同一用户在不同群组有不同会话。

### 对话 Resume 机制

Gemini CLI 支持通过 `--resume <session_id>` 继续上一次对话：

```
第一轮：gemini --output-format stream-json -p "你好"
  → init 事件携带 session_id: "abc123"
  → 存入 session.agent_session_id

第二轮：gemini --output-format stream-json --resume abc123 -p "继续刚才的话题"
  → Gemini CLI 加载 ~/.gemini/tmp/.../chats/session-abc123.json
  → 对话上下文继续
```

`/new` 命令会清除 `agent_session_id`，下次对话将开启全新会话。

### 并发保护

每个用户会话有一个 `asyncio.Lock`：

```
用户 A 发消息 → try_lock() 成功 → 开始处理
用户 A 发第二条消息 → try_lock() 失败（已锁）→ 加入队列（最多5条）
                                                → 回复 "⏳ Agent 正忙"

第一条处理完 → unlock() → 从队列取下一条 → 开始处理
```

---

## 开发指南

### 环境搭建

```bash
git clone https://github.com/atticuszeller/tg-gemini
cd tg-gemini
uv sync --all-groups
```

### 开发命令

所有命令通过 `bash dev.sh <command>` 执行：

| 命令 | 说明 |
|------|------|
| `bash dev.sh format` | ruff check --fix + ruff format |
| `bash dev.sh lint` | ty check + ruff check + ruff format --check |
| `bash dev.sh test` | coverage run pytest + 覆盖率报告 |
| `bash dev.sh test -k foo` | 运行匹配 "foo" 的单个测试 |
| `bash dev.sh check` | 完整检查：format → lint → test → pre-commit |
| `bash dev.sh bump` | git-cliff changelog + 版本号提升 + push tags |
| `bash dev.sh docs dev` | mkdocs serve（本地预览文档） |

### 代码质量要求

| 工具 | 要求 |
|------|------|
| **ty** | 全量类型注解，零 error |
| **ruff** | `select = ["ALL"]`，显式 ignore 列表 |
| **pytest** | 所有 warning 视为 error |
| **coverage** | ≥ 95%（branch coverage） |
| **commits** | Conventional Commits（feat/fix/refactor/test/chore） |

### 测试结构

```bash
# 运行所有测试
bash dev.sh test

# 运行特定模块测试
uv run pytest tests/test_gemini.py -v

# 运行特定测试
uv run pytest tests/test_markdown.py -k "test_bold" -v

# 查看覆盖率详情
uv run coverage html
open htmlcov/index.html
```

**测试文件对应关系：**

| 测试文件 | 覆盖模块 | 关键测试 |
|---------|---------|---------|
| `test_models.py` | `models.py` | 数据类实例化、字段默认值 |
| `test_config.py` | `config.py` | TOML 加载、路径解析、验证错误 |
| `test_i18n.py` | `i18n.py` | EN/ZH 翻译、格式化、语言检测 |
| `test_markdown.py` | `markdown.py` | 各种 Markdown 语法转换、消息分割 |
| `test_session.py` | `session.py` | 锁机制、并发、JSON 持久化 |
| `test_gemini.py` | `gemini.py` | JSONL fixture 集成（4 种完整事件序列）、超时/kill、事件解析 |
| `test_streaming.py` | `streaming.py` | 节流逻辑、freeze/finish 生命周期 |
| `test_telegram.py` | `telegram_platform.py` | 消息处理、权限过滤、API 调用 |
| `test_engine.py` | `engine.py` | 消息路由、命令分发、端到端场景（真实 GeminiSession）、session resume 循环 |
| `test_cli.py` | `cli.py` | 启动流程、配置加载、参数解析 |

### 添加新功能

典型扩展流程（以新增 `/status` 命令为例）：

1. **`i18n.py`** — 添加消息键：
   ```python
   class MsgKey(StrEnum):
       STATUS = "status"

   MESSAGES[MsgKey.STATUS] = {
       Language.EN: "Status: model={}, mode={}",
       Language.ZH: "状态：模型={}，模式={}",
   }
   ```

2. **`engine.py`** — 添加命令处理：
   ```python
   async def handle_command(self, msg: Message, raw: str) -> bool:
       match cmd:
           case "/status":
               await self._cmd_status(msg)

   async def _cmd_status(self, msg: Message) -> None:
       text = self._i18n.tf(MsgKey.STATUS, self._agent.model or "default", self._agent.mode)
       await self._reply(msg, text)
   ```

3. **`tests/test_engine.py`** — 添加测试：
   ```python
   async def test_handle_command_status() -> None:
       engine, agent, platform = _make_engine()
       agent.model = "flash"
       agent.mode = "yolo"
       msg = _make_message()
       result = await engine.handle_command(msg, "/status")
       assert result is True
       platform.send.assert_called_once()
   ```

### 版本发布

```bash
# 1. 确保所有检查通过
bash dev.sh check

# 2. 提升版本（自动更新 changelog、打 tag、push）
bash dev.sh bump

# 3. CI/CD 自动发布到 PyPI
```

---

## 常见问题

### Q: Gemini CLI 没有响应

检查：
```bash
# 测试 CLI 是否正常
gemini -p "hello" --output-format stream-json

# 检查认证
gemini  # 应进入交互模式
```

### Q: Telegram 收不到消息

检查 `allow_from` 配置，用 `/start` 向机器人发消息，同时查看日志：
```bash
tg-gemini start  # 看控制台日志
# 或
journalctl -u tg-gemini -f
```

### Q: 流式预览不工作

可能是 Telegram API 限流。增大 `stream_preview.interval_ms` 值：
```toml
[stream_preview]
interval_ms = 3000  # 从 1500 增加到 3000
```

### Q: 对话没有历史记忆

使用 `/new` 会清除会话 ID。重启服务后会话也不会保留（v1 限制）。需要上下文记忆时，不要发 `/new`，服务重启后会自动恢复到最近一次会话。

### Q: 如何限制只有自己能用

找到自己的 Telegram ID（向 @userinfobot 发消息），然后设置：
```toml
[telegram]
allow_from = "你的ID"
```
