# 配置参考

配置文件为 TOML 格式。完整带注释的示例见项目根目录的 [`config.example.toml`](../config.example.toml)。

## 路径解析优先级

1. `--config` 参数指定的路径
2. 当前目录的 `config.toml`
3. `~/.tg-gemini/config.toml`（默认）

## 完整配置项

> **注意**：`data_dir`、`language` 等顶层字段必须写在任何 `[section]` 标题之前。

### 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `data_dir` | str | `"~/.tg-gemini"` | 存放 `sessions.json` 的目录 |
| `language` | str | `""` | `""` = 自动检测，`"en"` = 英文，`"zh"` = 中文 |

### `[telegram]`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `token` | str | **必填** | BotFather 提供的 Bot Token |
| `allow_from` | str | `"*"` | 白名单：`"*"` 全开，或逗号分隔的用户 ID |
| `group_reply_all` | bool | `false` | `true` = 响应群里所有消息；`false` = 仅响应 @mention、reply-to-bot、/command |
| `share_session_in_channel` | bool | `false` | `true` = 群内共享一个 Gemini 会话 |

**查找 Telegram 用户 ID**：向 [@userinfobot](https://t.me/userinfobot) 发任意消息。

### `[gemini]`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `work_dir` | str | `"."` | `gemini` 命令的工作目录 |
| `model` | str | `""` | 模型名，空字符串 = CLI 默认 |
| `mode` | str | `"default"` | 工具调用审批模式（见下表） |
| `api_key` | str | `""` | Gemini API Key，也可用环境变量 `GEMINI_API_KEY` |
| `cmd` | str | `"gemini"` | gemini 可执行文件名或路径 |
| `timeout_mins` | int | `0` | 每轮超时分钟（0 = 不限制） |

**Gemini 审批模式说明：**

| 模式 | CLI 标志 | 行为 |
|------|---------|------|
| `default` | 无 | 每次工具调用需确认（无交互环境下会卡住，**不推荐**） |
| `auto_edit` | `--approval-mode auto_edit` | 自动批准文件读写，其他操作需确认 |
| `yolo` | `-y` | 全自动批准所有操作（**推荐用于服务端**） |
| `plan` | `--approval-mode plan` | 只读计划模式，不执行工具 |

**可用模型（`gemini /model manage` 查看最新）：**

| 模型 | 特点 |
|------|------|
| `gemini-3.1-pro-preview` | 最新旗舰预览版 |
| `gemini-3-flash-preview` | 最新快速预览版 |
| `gemini-2.5-pro` | 稳定旗舰，强推理 |
| `gemini-2.5-flash` | 稳定快速，推荐日常使用 |
| `gemini-2.5-flash-lite` | 轻量版，响应最快 |

### `[log]`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | str | `"INFO"` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |

### `[display]`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `thinking_max_len` | int | `300` | Thinking 文本截断长度（正整数） |
| `tool_max_len` | int | `500` | 工具参数截断长度（正整数） |

### `[stream_preview]`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 开启流式预览 |
| `interval_ms` | int | `1500` | 两次编辑最小间隔（ms），避免 Telegram 429 限流 |
| `min_delta_chars` | int | `30` | 每次更新最少新增字符数 |
| `max_chars` | int | `2000` | 预览最大字符数（0 = 不限制），`finish()` 时发完整文本 |

### `[rate_limit]`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_messages` | int | `0` | 时间窗口内最大消息数（0 = 禁用限制） |
| `window_secs` | float | `60.0` | 时间窗口大小（秒） |

## 最小配置

只需必填字段即可启动：

```toml
[telegram]
token = "123456:ABC-DEF..."
```

## 典型生产配置

```toml
data_dir = "~/.tg-gemini"
language = "zh"

[telegram]
token = "123456:ABC-DEF..."
allow_from = "你的用户ID"

[gemini]
work_dir = "/home/user/projects"
model = "gemini-2.5-flash"
mode = "yolo"
timeout_mins = 10

[log]
level = "INFO"

[stream_preview]
interval_ms = 2000
```

## 群聊配置示例

```toml
[telegram]
token = "..."
allow_from = "*"
group_reply_all = false      # 只响应 @bot 或回复 bot
share_session_in_channel = false  # 每人独立会话
```

## 环境变量

`GEMINI_API_KEY` — 等效于 `gemini.api_key`，优先级低于配置文件。

## 配置验证

所有配置字段经过 pydantic v2 严格验证：
- 未知字段 → ValidationError
- 类型不匹配 → ValidationError
- 枚举值非法（如 `mode = "turbo"`）→ ValidationError
- 数值范围非法（如 `timeout_mins = -1`）→ ValidationError
