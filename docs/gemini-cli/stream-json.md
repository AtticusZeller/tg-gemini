# Gemini CLI — `--output-format stream-json` 完整参考

> 源码依据：`gemini-cli/packages/core/src/output/types.ts`、`stream-json-formatter.ts`、
> `packages/cli/src/nonInteractiveCli.ts`、`packages/cli/src/utils/errors.ts`、
> `packages/core/src/tools/tool-error.ts`、`packages/core/src/tools/tools.ts`、
> `packages/core/src/tools/definitions/base-declarations.ts`、
> `packages/core/src/utils/errors.ts`

---

## 1. 触发条件

```bash
gemini --output-format stream-json -p "<prompt>"
# 或
gemini -o stream-json -p "<prompt>"
```

输出为 **JSONL**（newline-delimited JSON）：每行一个压缩 JSON 对象，后跟 `\n`，写到 **stdout**。stderr 保留给日志、调试输出和用户反馈。

---

## 2. 公共基础字段

所有事件均包含这两个字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | `string` | 事件类型（见下） |
| `timestamp` | `string` | ISO-8601，如 `"2025-10-10T12:00:00.000Z"` |

---

## 3. 事件类型完整规范

### 3.1 `init` — 会话初始化

触发时机：在发送用户 prompt 之前，formatter 创建后立即发出，**每次运行仅一次**。

```json
{
  "type": "init",
  "timestamp": "2025-10-10T12:00:00.000Z",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "model": "gemini-2.5-pro"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | `string` | UUID，由 `config.getSessionId()` 生成。使用 `--resume` 时为已有 session 的 UUID |
| `model` | `string` | 当前使用的模型名称，如 `"gemini-2.5-pro"`、`"gemini-2.5-flash"` |

---

### 3.2 `message` — 消息（用户或助手）

**用户消息**（每次运行仅一次，在 `init` 之后）：

```json
{
  "type": "message",
  "timestamp": "...",
  "role": "user",
  "content": "完整的用户输入字符串"
}
```

**助手流式消息块**（每个内容块一次，可多次）：

```json
{
  "type": "message",
  "timestamp": "...",
  "role": "assistant",
  "content": "单个文本增量片段",
  "delta": true
}
```

| 字段 | 类型 | 可能值 / 说明 |
|---|---|---|
| `role` | `string` | `"user"` \| `"assistant"` |
| `content` | `string` | 完整提示（user）或单次增量片段（assistant） |
| `delta` | `boolean` \| `undefined` | 仅 assistant 消息有此字段且值为 `true`；user 消息无此字段。**不存在 `delta: false`** |

> **关键规则**：在 `stream-json` 模式下，**所有**助手文本都以 `delta:true` 形式逐块到达。消费者必须**自行拼接**所有 `delta:true` 块，才能还原完整的助手回复。两次 `tool_use` / `result` 事件之间的所有 `message(assistant)` 块属于同一助手轮次。

---

### 3.3 `tool_use` — 模型请求调用工具

每次模型请求一个工具调用时发出（`GeminiEventType.ToolCallRequest`），在工具实际执行**之前**。

```json
{
  "type": "tool_use",
  "timestamp": "...",
  "tool_name": "run_shell_command",
  "tool_id": "call-abc123def456",
  "parameters": {
    "command": "ls -la /tmp",
    "description": "列出临时目录",
    "is_background": false
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `tool_name` | `string` | 工具注册名（见第 5 节完整列表） |
| `tool_id` | `string` | 本次调用的唯一 ID（`callId`），与对应 `tool_result` 的 `tool_id` 匹配 |
| `parameters` | `object` | 工具参数，key-value 对，键名见各工具定义（第 5 节） |

---

### 3.4 `tool_result` — 工具执行完毕

工具执行完成后发出，与 `tool_use` 通过 `tool_id` 配对。

**成功：**

```json
{
  "type": "tool_result",
  "timestamp": "...",
  "tool_id": "call-abc123def456",
  "status": "success",
  "output": "total 48\ndrwxr-xr-x  8 user  staff  256 ..."
}
```

**失败：**

```json
{
  "type": "tool_result",
  "timestamp": "...",
  "tool_id": "call-xyz789",
  "status": "error",
  "error": {
    "type": "file_not_found",
    "message": "No such file or directory: /nonexistent/path"
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `tool_id` | `string` | 对应 `tool_use` 的 `tool_id` |
| `status` | `string` | `"success"` \| `"error"` |
| `output` | `string` \| `undefined` | 成功时的展示结果（`resultDisplay` 字段为字符串时）；可能不存在 |
| `error` | `object` \| `undefined` | 失败时存在；字段见下表 |
| `error.type` | `string` | `ToolErrorType` 枚举值（见第 6 节）或 `"TOOL_EXECUTION_ERROR"`（兜底） |
| `error.message` | `string` | 原始错误消息文本 |

> 注意：`output` 和 `error` 均为可选。成功的工具调用如果没有文本显示结果，则 `output` 字段不存在。

---

### 3.5 `error` — 非致命流内警告

仅在以下两种情况下触发，**不会中止执行**，后续仍会发出 `result`：

```json
{
  "type": "error",
  "timestamp": "...",
  "severity": "warning",
  "message": "Loop detected, stopping execution"
}
```

```json
{
  "type": "error",
  "timestamp": "...",
  "severity": "error",
  "message": "Maximum session turns exceeded"
}
```

| 字段 | 类型 | 可能值 |
|---|---|---|
| `severity` | `string` | `"warning"` — 检测到死循环；`"error"` — 超过最大 turns |
| `message` | `string` | 固定字符串之一（见上例） |

> `error` 事件 ≠ 致命错误。致命错误通过 `result` 事件（`status:"error"`）+ 非零退出码表达。

---

### 3.6 `result` — 最终事件（总是最后一个）

**每次运行仅发出一次**，在进程退出前必定发出（包括所有错误路径）。

**成功：**

```json
{
  "type": "result",
  "timestamp": "...",
  "status": "success",
  "stats": {
    "total_tokens": 1250,
    "input_tokens": 950,
    "output_tokens": 300,
    "cached": 400,
    "input": 550,
    "duration_ms": 3200,
    "tool_calls": 3,
    "models": {
      "gemini-2.5-pro": {
        "total_tokens": 1250,
        "input_tokens": 950,
        "output_tokens": 300,
        "cached": 400,
        "input": 550
      }
    }
  }
}
```

**失败（致命错误）：**

```json
{
  "type": "result",
  "timestamp": "...",
  "status": "error",
  "error": {
    "type": "FatalTurnLimitedError",
    "message": "Reached max session turns for this session. ..."
  },
  "stats": {
    "total_tokens": 800,
    "input_tokens": 600,
    "output_tokens": 200,
    "cached": 0,
    "input": 600,
    "duration_ms": 0,
    "tool_calls": 1,
    "models": { ... }
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | `string` | `"success"` \| `"error"` |
| `error` | `object` \| `undefined` | 仅 `status:"error"` 时存在 |
| `error.type` | `string` | 异常类名（见下表）或 `ToolErrorType` 字符串 |
| `error.message` | `string` | 错误消息文本 |
| `stats` | `object` | 始终存在（出错时 `duration_ms` 可能为 `0`） |

**`stats` 字段详解：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `total_tokens` | `number` | `input_tokens + output_tokens` |
| `input_tokens` | `number` | 发送给模型的 prompt tokens 总量 |
| `cached` | `number` | `input_tokens` 中来自缓存的部分 |
| `input` | `number` | `input_tokens - cached`（实际计费的新输入） |
| `output_tokens` | `number` | 模型生成的 candidates tokens |
| `duration_ms` | `number` | 从会话开始到 `result` 发出的毫秒数；错误路径可能为 `0` |
| `tool_calls` | `number` | 整个会话中的工具调用总次数 |
| `models` | `object` | 按模型名分组的 token 统计，每项含上述 5 个 token 字段（无 `duration_ms`/`tool_calls`） |

**`result.error.type` 的可能值（致命异常类名）：**

| `error.type` 值 | 退出码 | 触发条件 |
|---|---|---|
| `FatalAuthenticationError` | 41 | 认证失败 |
| `FatalInputError` | 42 | prompt 或参数无效（含 `@file` 不存在等） |
| `FatalSandboxError` | 44 | 沙箱启动失败 |
| `FatalConfigError` | 52 | 配置文件错误 |
| `FatalTurnLimitedError` | 53 | 超过 `maxSessionTurns` 设置值 |
| `FatalToolExecutionError` / `no_space_left` | 54 | 磁盘空间不足（唯一致命的工具错误） |
| `FatalCancellationError` | 130 | Ctrl+C / SIGINT |
| `Error`（或其他） | 1 | API 错误、网络异常等通用错误 |

---

## 4. 完整事件序列

### 正常流（含工具调用）

```
init
message (role=user)
message (role=assistant, delta=true)   ← 0..N 个流式文本块
message (role=assistant, delta=true)
tool_use                               ← 工具调用请求
tool_result                            ← 工具执行结果
message (role=assistant, delta=true)   ← 工具后续文本块
...
result (status=success)
```

### 死循环检测

```
init
message (role=user)
error (severity=warning, message="Loop detected, stopping execution")
result (status=success)
```

### 超过最大 turns（流内警告 + 致命退出）

```
init
message (role=user)
...
error (severity=error, message="Maximum session turns exceeded")
result (status=error, error.type=FatalTurnLimitedError)  ← process.exit(53)
```

### 致命错误（无 tool 活动）

```
init
message (role=user)
result (status=error, error.type=FatalAuthenticationError)  ← process.exit(41)
```

### AgentExecutionStopped（正常终止）

```
init
message (role=user)
tool_use
tool_result (status=success, error.type=stop_execution)  ← STOP_EXECUTION hook
result (status=success)
```

---

## 5. 内置工具：`tool_name` 与 `parameters` 字段

`tool_use` 事件中 `tool_name` 的所有可能值及对应参数键名：

### 执行类

#### `run_shell_command`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `command` | `string` | ✓ | 要执行的 shell 命令 |
| `description` | `string` | — | 人类可读的操作说明 |
| `dir_path` | `string` | — | 工作目录路径 |
| `is_background` | `boolean` | — | `true` 则后台执行，不等待结果 |
| `wait_for_previous` | `boolean` | — | 是否等待前序工具完成（并行控制） |

Kind: `Execute`（有副作用，需用户确认）

---

### 文件系统类

#### `read_file`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_path` | `string` | ✓ | 文件绝对路径或相对路径 |
| `start_line` | `number` | — | 起始行号（1-based） |
| `end_line` | `number` | — | 结束行号（含） |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Read`（只读）

#### `read_many_files`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `include` | `string[]` | ✓ | glob 模式列表，匹配要读取的文件 |
| `exclude` | `string[]` | — | 排除的 glob 模式列表 |
| `recursive` | `boolean` | — | 是否递归搜索子目录 |
| `useDefaultExcludes` | `boolean` | — | 是否应用默认排除规则（`node_modules` 等） |
| `file_filtering_options` | `object` | — | 细粒度过滤选项 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Read`（只读）。`@file` 语法触发此工具。

#### `write_file`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_path` | `string` | ✓ | 目标文件路径（不存在则创建，存在则覆盖） |
| `content` | `string` | ✓ | 文件完整内容 |
| `description` | `string` | — | 操作说明 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Edit`（有副作用，需用户确认）

#### `replace`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_path` | `string` | ✓ | 目标文件路径 |
| `old_string` | `string` | ✓ | 要被替换的精确文本 |
| `new_string` | `string` | ✓ | 替换后的文本 |
| `instruction` | `string` | — | 人类可读的说明 |
| `allow_multiple` | `boolean` | — | 是否允许替换多处（默认仅替换第一处） |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Edit`（有副作用，需用户确认）

#### `glob`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pattern` | `string` | ✓ | glob 模式，如 `"**/*.ts"` |
| `dir_path` | `string` | — | 搜索根目录（默认工作目录） |
| `case_sensitive` | `boolean` | — | 大小写敏感（默认 `false`） |
| `respect_git_ignore` | `boolean` | — | 遵从 `.gitignore`（默认 `true`） |
| `respect_gemini_ignore` | `boolean` | — | 遵从 `.geminiignore`（默认 `true`） |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Search`（只读）

#### `grep_search`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pattern` | `string` | ✓ | 正则表达式搜索模式 |
| `dir_path` | `string` | — | 搜索目录（默认工作目录） |
| `include_pattern` | `string` | — | 限定搜索的文件 glob（如 `"*.ts"`） |
| `exclude_pattern` | `string` | — | 排除文件 glob |
| `names_only` | `boolean` | — | 仅返回文件名，不返回匹配行 |
| `max_matches_per_file` | `number` | — | 每文件最大匹配数 |
| `total_max_matches` | `number` | — | 总最大匹配数 |
| `fixed_strings` | `boolean` | — | 将 pattern 视为固定字符串（ripgrep 模式） |
| `context` | `number` | — | 匹配行前后各显示的行数（ripgrep 模式） |
| `after` | `number` | — | 匹配行后显示的行数（ripgrep 模式） |
| `before` | `number` | — | 匹配行前显示的行数（ripgrep 模式） |
| `no_ignore` | `boolean` | — | 忽略 gitignore / geminiignore（ripgrep 模式） |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Search`（只读）。旧别名：`search_file_content`。

#### `list_directory`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `dir_path` | `string` | ✓ | 要列出的目录路径 |
| `ignore` | `string[]` | — | 要忽略的文件/目录名 |
| `file_filtering_options` | `object` | — | 过滤选项 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Read`（只读）

---

### 网络类

#### `google_web_search`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `query` | `string` | ✓ | 搜索查询字符串 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Search`（只读）

#### `web_fetch`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `prompt` | `string` | ✓ | 包含 URL 的 prompt（工具自动提取 URL） |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Fetch`（只读）

---

### 交互类

#### `ask_user`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `questions` | `Question[]` | ✓ | 问题列表 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

`Question` 对象字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | `string` | ✓ | 问题文本 |
| `header` | `string` | — | 简短标签（≤12字符） |
| `type` | `string` | — | 问题类型 |
| `options` | `Option[]` | — | 选项列表 |
| `multiSelect` | `boolean` | — | 是否允许多选 |
| `placeholder` | `string` | — | 输入框占位符 |

`Option` 对象字段：`label`（string），`description`（string）

Kind: `Communicate`

#### `write_todos`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `todos` | `Todo[]` | ✓ | 任务列表 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

`Todo` 对象字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `description` | `string` | 任务描述 |
| `status` | `string` | `"pending"` \| `"in_progress"` \| `"completed"` \| `"cancelled"` |

Kind: `Other`

---

### 记忆类

#### `save_memory`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `fact` | `string` | ✓ | 要持久化到 `GEMINI.md` 的事实文本 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Think`

#### `get_internal_docs`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | `string` | ✓ | 内部文档路径 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Think`

#### `activate_skill`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | `string` | ✓ | `.gemini/skills/` 目录下的 skill 名称 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Other`

---

### 规划类

#### `enter_plan_mode`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `reason` | `string` | ✓ | 进入 Plan Mode 的原因 |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Plan`（切换到只读规划模式）

#### `exit_plan_mode`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `plan_path` | `string` | ✓ | 规划文件路径（由 enter_plan_mode 写入） |
| `wait_for_previous` | `boolean` | — | 并行控制 |

Kind: `Plan`

---

### 系统类（内部）

#### `complete_task`

| 参数键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `result` | `string` | ✓ | subagent 返回给 parent agent 的结果 |

用于 subagent 通信，**用户不可见**。

---

## 6. `ToolErrorType` 枚举完整列表

出现在 `tool_result.error.type` 字段中。可恢复错误允许模型自我修正；不可恢复错误（仅 `no_space_left`）触发 `result(status:error)` + exit 54。

### 通用

| 值 | 分类 | 说明 |
|---|---|---|
| `invalid_tool_params` | 可恢复 | 参数校验失败 |
| `unknown` | 可恢复 | 未知错误 |
| `unhandled_exception` | 可恢复 | 未捕获的异常 |
| `tool_not_registered` | 可恢复 | 工具未注册 |
| `execution_failed` | 可恢复 | 通用执行失败 |
| `policy_violation` | 可恢复 | 安全策略拒绝 |

### 文件系统

| 值 | 分类 | 说明 |
|---|---|---|
| `file_not_found` | 可恢复 | 文件或目录不存在 |
| `file_write_failure` | 可恢复 | 写入文件失败 |
| `read_content_failure` | 可恢复 | 读取文件内容失败 |
| `attempt_to_create_existing_file` | 可恢复 | 尝试创建已存在的文件 |
| `file_too_large` | 可恢复 | 文件超过大小限制 |
| `permission_denied` | 可恢复 | 权限拒绝 |
| `no_space_left` | **不可恢复** | 磁盘空间不足 → exit 54 |
| `target_is_directory` | 可恢复 | 目标是目录而非文件 |
| `path_not_in_workspace` | 可恢复 | 路径超出工作目录范围 |
| `search_path_not_found` | 可恢复 | 搜索路径不存在 |
| `search_path_not_a_directory` | 可恢复 | 搜索路径不是目录 |

### 编辑相关（`replace` 工具）

| 值 | 分类 | 说明 |
|---|---|---|
| `edit_preparation_failure` | 可恢复 | 编辑准备阶段失败 |
| `edit_no_occurrence_found` | 可恢复 | `old_string` 在文件中未找到 |
| `edit_expected_occurrence_mismatch` | 可恢复 | 匹配数量与预期不符 |
| `edit_no_change` | 可恢复 | 替换前后内容相同 |
| `edit_no_change_llm_judgement` | 可恢复 | 模型判定无需修改 |

### 工具特定

| 值 | 工具 | 说明 |
|---|---|---|
| `glob_execution_error` | `glob` | glob 执行失败 |
| `grep_execution_error` | `grep_search` | grep 执行失败 |
| `ls_execution_error` | `list_directory` | ls 执行失败 |
| `path_is_not_a_directory` | `list_directory` | 路径不是目录 |
| `mcp_tool_error` | MCP 工具 | MCP 工具执行失败 |
| `memory_tool_execution_error` | `save_memory` | 记忆工具执行失败 |
| `read_many_files_search_error` | `read_many_files` | 批量读取搜索失败 |
| `shell_execute_error` | `run_shell_command` | shell 执行失败 |
| `discovered_tool_execution_error` | 发现的工具 | 动态工具执行失败 |
| `web_fetch_no_url_in_prompt` | `web_fetch` | prompt 中未找到 URL |
| `web_fetch_fallback_failed` | `web_fetch` | fallback 策略失败 |
| `web_fetch_processing_error` | `web_fetch` | 页面处理失败 |
| `web_search_failed` | `google_web_search` | 搜索请求失败 |
| `stop_execution` | hook | 触发停止执行（exit as success） |

---

## 7. 退出码

| 代码 | 错误类 | 触发条件 |
|---|---|---|
| `0` | — | 正常完成 |
| `1` | 通用 `Error` | API 错误、网络错误、未分类异常 |
| `41` | `FatalAuthenticationError` | 认证失败 |
| `42` | `FatalInputError` | prompt / `@file` / 参数无效 |
| `44` | `FatalSandboxError` | 沙箱启动失败 |
| `52` | `FatalConfigError` | 配置文件错误 |
| `53` | `FatalTurnLimitedError` | 超过 `maxSessionTurns` |
| `54` | `FatalToolExecutionError` | `no_space_left`（唯一致命工具错误） |
| `130` | `FatalCancellationError` | Ctrl+C / SIGINT |

`result` 事件**总是**在 `process.exit()` 之前发出，包括所有错误路径。

---

## 8. CLI 标志（headless 相关）

| 标志 | 别名 | 类型 | 默认 | 说明 |
|---|---|---|---|---|
| `--output-format stream-json` | `-o stream-json` | string | `text` | 启用 JSONL 流式输出 |
| `--prompt "<text>"` | `-p` | string | — | 提示文本，触发 headless 模式 |
| `--model <name>` | `-m` | string | `auto` | 模型名，如 `gemini-2.5-pro` |
| `--resume <id>` | `-r` | string | — | 恢复会话：`"latest"`、1-based 索引号、或 UUID |
| `--approval-mode <mode>` | — | string | `default` | `default` \| `auto_edit` \| `yolo` \| `plan` |
| `--yolo` | `-y` | boolean | `false` | `--approval-mode=yolo` 的简写（已弃用） |
| `--debug` | `-d` | boolean | `false` | 详细 stderr 调试日志 |
| `--sandbox` | `-s` | boolean | `false` | 沙箱模式执行 |

> `--yolo` 与 `--approval-mode` 不可同时使用。`--prompt` 与位置参数 query 不可同时使用。

---

## 9. Session / Resume 机制

- Session 文件存储在 `~/.gemini/tmp/<project_hash>/chats/` 目录，文件名以时间戳开头。
- `--resume latest`：加载 `startTime` 最新的 session。
- `--resume <N>`：按 1-based 索引（按创建时间升序）加载 session。
- `--resume <uuid>`：按完整 UUID 加载 session。
- Resume 后，`init` 事件仍然发出，`session_id` 为已有 session 的 UUID。
- 消费者应将每次 `init` 事件的 `session_id` 存储起来，下次传给 `--resume` 以实现连续对话。

---

## 10. `wait_for_previous` 参数

所有工具的 `parameters` 中均可包含 `wait_for_previous: boolean`（由框架自动注入到 schema 中）：

- `false`（或省略）：与其他工具**并行**执行。
- `true`：等待本 turn 中**所有已请求的工具**完成后再开始。

当工具依赖前序工具的输出时，模型应设置 `wait_for_previous: true`。

---

## 11. `tool_result.output` 的内容规律

`output` 是工具的 `resultDisplay` 字段（字符串类型时）映射而来：

| 工具 | `output` 典型内容 |
|---|---|
| `run_shell_command` | 命令的 stdout 文本 |
| `read_file` | 文件内容（可能附行号） |
| `read_many_files` | 多文件内容拼接 |
| `glob` | 匹配到的文件路径列表 |
| `grep_search` | 匹配行列表 |
| `list_directory` | 目录内容列表 |
| `google_web_search` | 搜索结果摘要 |
| `web_fetch` | 页面提取文本 |
| `save_memory` | 确认消息 |
| `write_file` / `replace` | 操作确认消息 |
| `ask_user` | 用户回答文本 |

当 `resultDisplay` 不是字符串（如 `FileDiff`、`AnsiOutput`、`TodoList` 对象）时，`output` 字段**不存在**。
