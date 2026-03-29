# 内部实现细节

## Gemini stream-json 协议

tg-gemini 消费 `gemini --output-format stream-json` 的 JSONL 输出。

### 事件类型

#### `init` — 会话初始化
```json
{"type": "init", "session_id": "abc123-def456", "model": "gemini-2.5-flash"}
```
处理：存储 `session_id` 供下次 `--resume` 使用。

#### `message` — 文本块
```json
{"type": "message", "role": "assistant", "content": "Hello", "delta": true}
```
- `delta: true` → 流式片段，立即作为 `EventText` 发出
- `delta: false`（或缺失）→ 完整消息，**缓冲**待分类

**缓冲分类规则：**
- 收到 `tool_use` → 缓冲内容作为 `EventThinking` 发出（可能被静音）
- 收到 `result` → 缓冲内容作为 `EventText` 发出

#### `tool_use` — 工具调用
```json
{
  "type": "tool_use",
  "tool_name": "read_file",
  "tool_id": "read-abc123",
  "parameters": {"file_path": "/src/main.py"}
}
```
处理：冻结预览 + 发送工具通知 `🔧 read_file: /src/main.py`（静音模式跳过）。

**内置参数格式化：**

| 工具 | 显示格式 |
|------|---------|
| `shell` / `Bash` | 命令字符串 |
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
错误时：`"status": "error", "error": {"message": "..."}`

处理：结果截断到 500 字符后作为 `📋 Result: ...` 发出（静音模式跳过）。

#### `error` — 错误
```json
{"type": "error", "severity": "error", "message": "Something failed"}
```

#### `result` — 会话结束
```json
{"type": "result", "status": "success", "stats": {"total_tokens": 500}}
```
处理：触发 `preview.finish()` → 发送最终响应，记录对话历史。

### 典型事件流

```
init          → 存储 session_id
message(δ)    → "Let me " → 流式预览更新
message(δ)    → "check..."
message(非δ)  → "I need to read the source." → 缓冲
tool_use      → read_file → 刷新缓冲为 THINKING，冻结预览
tool_result   → "file content" → 发送 📋 Result
message(δ)    → "Based on the code..." → 新预览开始
result        → finish(full_text) → 更新最终预览
```

---

## Markdown 转换器

将 Obsidian/标准 Markdown 转为 Telegram HTML（`parse_mode=HTML`）。

### 支持的转换

| Markdown | Telegram HTML |
|----------|---------------|
| `**bold**` 或 `__bold__` | `<b>bold</b>` |
| `*italic*` | `<i>italic</i>` |
| `***bold italic***` | `<b><i>bold italic</i></b>` |
| `~~strike~~` | `<s>strike</s>` |
| `` `code` `` | `<code>code</code>` |
| ` ```python\ncode\n``` ` | `<pre><code class="language-python">code</code></pre>` |
| `[text](url)` | `<a href="url">text</a>` |
| `[[wikilink]]` | 纯文本 |
| `> blockquote` | `<blockquote>...</blockquote>` |
| `> [!NOTE] 标题` | `<blockquote><b>NOTE: 标题</b>...</blockquote>` |
| `# Heading` | `<b>Heading</b>` |
| `---` / `***` | `──────────` |
| `- item` / `* item` | `• item` |
| `1. item` | `1. item` |
| `\| col1 \| col2 \|` | 纯文本表格（`col1 \| col2`） |
| `<`, `>`, `&`, `"` | HTML 实体转义 |

### 处理流程

```
输入 Markdown
      │
      ▼
逐行扫描（状态机）
  ├─ 代码块 (```) → 缓冲 → <pre><code>...</code></pre>
  ├─ 引用块 (>) → 缓冲 → <blockquote>...</blockquote>
  │   └─ Obsidian callout → <blockquote><b>TYPE: Title</b>...</blockquote>
  ├─ 表格 (|...|) → 纯文本
  ├─ 标题 (#) → <b>text</b>
  ├─ 分割线 → ──────────
  ├─ 列表 → • / 1.
  └─ 普通行 → 内联转换（占位符保护）
                1. 内联代码 → 占位符
                2. 链接 → 占位符
                3. Wikilink → 纯文本
                4. HTML 转义（&, <, >, "）
                5. ***粗斜体*** → 占位符
                6. **粗体** / __粗体__ → 占位符
                7. ~~删除线~~ → 占位符
                8. *斜体* → <i>...</i>
                9. 恢复所有占位符
```

### 占位符机制

避免多轮正则替换互相干扰：
```
"`code`"      → "\x00PH0\x00"  （第1轮提取）
"[text](url)" → "\x00PH1\x00"  （第2轮提取）
HTML 转义仅影响未被占位的文本
最后：恢复占位符 → "<code>code</code>"、'<a href="...">text</a>'
```

### 消息分割（code fence 感知 + 超长行分割）

Telegram 单条消息上限 4096 字符。`split_message()` 在分割点补全/重开代码围栏，保持代码块完整：

```
长消息：```python\ncode\n``` 跨越 4096 边界

第一块：```python\n...\n```   ← 补全闭合 fence
第二块：```python\n...\n```   ← 重开 fence，内容连续
```

当单行超过 4096 限制时，`split_message()` 会先将当前缓冲区刷新（flush），，然后将该行按剩余容量切分成多个片段，每个片段作为独立的块（chunk）。这确保了即使是没有换行符的超长代码行或长段落也能正确分割。

---

## 流式预览机制

### 节流策略

Telegram 限制：同一消息每秒最多 **1 次**编辑。StreamPreview 实现：

```
append_text("x") 被调用
        │
        ├─ 没有上次发送记录（第一次）→ 立即 flush
        │
        ├─ 距上次 >= interval_ms AND 新增 >= min_delta_chars → 立即 flush
        │
        └─ 否则 → 延迟 flush（到下一个 interval 触发）
                  如果已有延迟任务：不重复创建
```

### 预览生命周期

```
消息开始处理
    │
    ├─ 第一个 TEXT chunk
    │       → send_preview_start() → 发新消息 → PreviewHandle(chat_id, msg_id)
    │
    ├─ 后续 TEXT chunk → update_message(handle, text) → 编辑预览消息
    │
    ├─ TOOL_USE → freeze()
    │       → 最后编辑一次 + 停止更新 + detach()
    │         （预览消息成为永久消息，工具通知另发新消息）
    │
    └─ RESULT → finish(full_text)
                    ├─ 成功 → update_message(handle, full_text) → return True
                    │         （调用方跳过 platform.reply）
                    └─ 失败 → delete_preview(handle) → return False
                              （调用方另发新消息）
```

`max_chars` 仅限制**预览期间**的显示长度（超出显示 `…`），`finish()` 时始终发完整文本。

---

## 会话系统

### 持久化格式（v2）

`~/.tg-gemini/sessions.json`：

```json
{
  "version": 2,
  "sessions": {
    "uuid-v4": {
      "id": "uuid-v4",
      "user_key": "telegram:123:456",
      "agent_session_id": "gemini-session-id",
      "name": "Sprint 42",
      "history": [
        {"role": "user", "content": "你好", "timestamp": "2026-03-22T10:00:00+00:00"},
        {"role": "assistant", "content": "你好！", "timestamp": "2026-03-22T10:00:05+00:00"}
      ],
      "created_at": "2026-03-22T10:00:00+00:00",
      "updated_at": "2026-03-22T10:00:05+00:00"
    }
  },
  "active_sessions": {"telegram:123:456": "uuid-v4"},
  "session_counter": 1
}
```

### v1 → v2 自动迁移

启动时如果检测到旧格式（无 `"version"` 键）：
- 每条 `user_key → session` 记录迁移为 v2 格式
- 立即保存为 v2 格式

### Card 系统

`card.py` 提供 `CardBuilder` 流式 API，渲染为 Telegram HTML + `InlineKeyboardMarkup`：

```python
card = (
    CardBuilder()
    .title("Sessions (3 total):")
    .list_item("▶ 1. Sprint 42")           # 活跃会话，无按钮
    .list_item("2. Bug fix", CardButton("Switch", "act:cmd:/switch uuid"))
    .note("Page 1 of 1")
    .build()
)
```

Callback data 格式：
- `cmd:/list 2` → 重新渲染（分页）
- `act:cmd:/switch {uuid}` → 执行动作后重新渲染
- `sel:delete:{uuid}` → 切换选择状态
