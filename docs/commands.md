# Bot 命令参考

在 Telegram 对话框中输入以下命令。

## 快速一览

| 命令 | 功能 |
|------|------|
| `/new` | 开启新 Gemini 会话（清除上下文） |
| `/list [页码]` | 查看所有会话列表 |
| `/switch <目标>` | 切换活跃会话（索引/ID/名称） |
| `/current` | 查看当前活跃会话 |
| `/history` | 查看最近对话历史 |
| `/name <名称>` | 重命名当前会话 |
| `/delete` | 删除会话（交互式选择） |
| `/status` | 显示当前状态（模型/模式/会话/静音） |
| `/model [名称]` | 查看或切换模型 |
| `/mode [模式]` | 查看或切换工具调用模式 |
| `/lang [代码]` | 查看或切换界面语言 |
| `/quiet` | 切换静音模式（隐藏工具通知） |
| `/stop` | 终止当前 Gemini 子进程 |
| `/help` | 显示命令帮助 |

---

## 会话管理命令

### `/new` — 开启新会话

清除当前会话上下文，从零开始。适合切换任务场景。

```
/new
```

**响应：** 🆕 New session started. / 🆕 已开始新会话。

---

### `/list [页码]` — 会话列表

以卡片形式显示当前用户的所有会话（5条/页）。每条会话旁有 **Switch** 按钮。

```
/list       # 第 1 页
/list 2     # 第 2 页
```

会话排序：最近使用的在前。活跃会话用 `▶` 标记。

---

### `/switch <目标>` — 切换会话

切换活跃会话。`<目标>` 支持三种格式：

```
/switch 1           # 按列表位置（1-based）
/switch abc12345    # 按 Session ID 前缀
/switch Sprint      # 按会话名称（模糊匹配）
```

**响应：** ✅ Switched to session: Sprint 1 / ✅ 已切换到会话：Sprint 1

---

### `/current` — 当前会话

显示当前活跃会话的名称或摘要。

```
/current
```

---

### `/history` — 对话历史

显示当前会话最近 10 条对话记录（用户消息 + Gemini 回复）。

```
/history
```

---

### `/name <新名称>` — 重命名会话

给当前活跃会话起一个易识别的名字。

```
/name 代码审查任务
/name Sprint 42
```

**响应：** ✅ Session renamed to: 代码审查任务

---

### `/delete` — 删除会话

交互式多选删除流程：

1. 发送 `/delete` → 显示所有会话，每条旁边有 **Toggle** 按钮
2. 点击 Toggle 勾选要删除的会话（☑ = 已选，☐ = 未选）
3. 点击 ✅ Confirm 确认删除 / ❌ Cancel 取消

如果删除了当前活跃会话，自动切换到最近使用的下一个会话。

---

## 模型与模式命令

### `/model [名称]` — 查看/切换模型

```
# 查看当前模型和可用列表
/model

# 切换到指定模型
/model gemini-2.5-flash
/model gemini-2.5-pro
```

**查看响应示例：**
```
Current model: (default)

  • gemini-3.1-pro-preview
  • gemini-3-flash-preview
  • gemini-2.5-pro
  • gemini-2.5-flash
  • gemini-2.5-flash-lite
```

切换后仅影响下一次发给 Gemini 的消息，不影响当前 session resume。

---

### `/mode [模式]` — 查看/切换模式

```
/mode               # 查看当前模式
/mode yolo          # 全自动
/mode auto_edit     # 自动批准文件操作
/mode plan          # 只读计划模式
/mode default       # 标准模式（服务端不推荐）
```

| 模式 | 说明 |
|------|------|
| `default` | 每次工具调用需手动确认（无交互会卡住） |
| `auto_edit` | 自动批准文件读写，其他需确认 |
| `yolo` | 全自动批准（推荐服务端使用）|
| `plan` | 只读，只生成计划不执行工具 |

---

## 状态与界面命令

### `/status` — 查看状态

以卡片形式显示当前配置状态：

```
/status
```

**显示内容：** 模型名 / 工具调用模式 / 当前会话名 / 静音是否开启

---

### `/lang [代码]` — 查看/切换语言

```
/lang       # 显示语言选择卡片（带按钮）
/lang zh    # 切换中文
/lang en    # 切换英文
```

语言影响所有系统消息（如 `/help`、错误提示、状态通知）。

---

### `/quiet` — 切换静音模式

每次调用切换开/关状态。

```
/quiet   # 开启 → 🔇 Quiet mode enabled.
/quiet   # 关闭 → 🔔 Quiet mode disabled.
```

**静音模式开启时：** 工具调用通知（🔧）和工具结果（📋）不再发送。Gemini 的最终文本回复不受影响。

适合不关心中间步骤、只要结果的场景。

---

### `/stop` — 终止 Agent

发送 SIGTERM 到当前 Gemini 子进程；3 秒内未退出则 SIGKILL。

```
/stop
```

**响应：** 🛑 Agent stopped.

如果没有正在运行的 Agent，仍会收到响应（不报错）。

---

### `/help` — 帮助

```
/help
```

显示所有可用命令的简短说明。

---

## 普通消息

任何非 `/` 开头的消息都直接发给 Gemini：

```
帮我分析这个项目的架构

解释一下 src/main.py 的逻辑

写一个 Python 函数计算斐波那契数列
```

### 发送图片

直接发送图片（可附加说明文字）。图片保存为临时文件，以 `@filepath` 方式传给 Gemini：

```
[发送截图] 这个错误是什么原因？
```

### 发送文件

直接发送文件（PDF、代码、日志等）：

```
[发送 error.log] 分析这个日志
```

---

## 群聊行为

当 `group_reply_all = false`（默认）时，群聊中的消息过滤规则：

| 消息类型 | 是否处理 |
|---------|---------|
| `/command` | ✅ 始终处理 |
| 含 `@机器人用户名` | ✅ 处理 |
| 回复机器人的消息 | ✅ 处理 |
| 其他普通消息 | ❌ 忽略 |

当 `group_reply_all = true` 时，所有群消息都会被处理。

会话键：`share_session_in_channel = false`（默认）时每人独立；`true` 时全群共享。

---

## 自定义 Commands

从 `<work_dir>/.gemini/commands/` 自动加载（`work_dir` 来自 `[gemini].work_dir` 配置）。

### 目录结构

```
work_dir/
└── .gemini/
    └── commands/
        ├── review.toml       → /review
        └── git/
            └── commit.toml   → /git_commit
```

> 嵌套路径中的 `/` 和 `:` 统一用 `_` 连接。

### TOML 格式

```toml
description = "Review code for issues"
prompt = """
You are an expert code reviewer. Review this:

{{args}}
"""
```

### 语法

| 语法 | 说明 |
|------|------|
| `{{args}}` | 替换为用户参数 |
| `@{filepath}` | 注入文件内容 |
| `!{cmd}` | 执行 shell 命令 |

---

## Skills

从 `<work_dir>/.gemini/skills/` **自动加载**，无需额外配置（与 Commands 同一 `work_dir`）。
可通过 `[skills].dirs` 追加额外目录。

### 目录结构

```
work_dir/
└── .gemini/
    └── skills/
        ├── review/
        │   └── SKILL.md
        └── refactor/
            └── SKILL.md
```

### SKILL.md 格式

```markdown
---
name: Code Review
description: Review code for issues
---

You are an expert code reviewer. Review the provided code:

1. Check for bugs
2. Check for security issues

Provide actionable feedback.
```

### 追加额外 Skill 目录（可选）

默认已自动加载 `<work_dir>/.gemini/skills/`，如需追加其他目录：

```toml
[skills]
dirs = ["~/.tg-gemini/skills", "/path/to/more/skills"]
```

---

## Commands 和 Skills 优先级

1. **内置命令** — `/new`, `/help`, `/list` 等（最高优先级）
2. **Commands** — `<work_dir>/.gemini/commands/`
3. **Skills** — `<work_dir>/.gemini/skills/` + `[skills].dirs` 追加目录

**命令名规范化**：所有非 `[a-z0-9]` 字符统一替换为 `_`（如 `git/commit.toml` → `/git_commit`），确保符合 Telegram 命令格式要求。

使用 `/commands reload` 重新加载所有 Commands 和 Skills，并刷新 Telegram 命令菜单。
