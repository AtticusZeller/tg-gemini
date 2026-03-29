# 开发指南

## 环境搭建

**前置要求：** Python 3.12+、uv

```bash
git clone https://github.com/atticuszeller/tg-gemini
cd tg-gemini
uv sync --all-groups
```

安装后 `tg-gemini` 命令即可用（`uv run tg-gemini start`）。

## 开发命令

所有命令通过 `bash dev.sh <command>` 执行：

| 命令 | 说明 |
|------|------|
| `bash dev.sh format` | ruff check --fix + ruff format |
| `bash dev.sh lint` | ty check + ruff check + ruff format --check |
| `bash dev.sh test` | coverage run pytest + 覆盖率报告 + HTML |
| `bash dev.sh test -k foo` | 运行匹配 "foo" 的测试 |
| `bash dev.sh check` | 完整流水线：format → lint → test → pre-commit |
| `bash dev.sh bump` | git-cliff changelog + bump-my-version + push tags |

## 代码质量要求

| 工具 | 要求 |
|------|------|
| **ty** | 全量类型注解，零 error |
| **ruff** | `select = ["ALL"]`，显式 ignore 列表 |
| **pytest** | 所有 warning 视为 error |
| **coverage** | ≥ 95%（branch coverage） |
| **commits** | Conventional Commits：`feat:` / `fix:` / `refactor:` / `test:` / `chore:` |

## 工具栈

| 工具 | 用途 |
|------|------|
| **uv** | 包管理、虚拟环境、运行命令 |
| **ruff** | Lint + 格式化（替代 flake8/black/isort） |
| **ty** | 类型检查（替代 mypy/pyright） |
| **pytest + coverage** | 测试 + 覆盖率 |
| **pydantic v2** | 配置验证 |
| **loguru** | 结构化日志 |

## 测试

### 运行测试

```bash
# 全量测试
bash dev.sh test

# 特定模块
uv run pytest tests/test_gemini.py -v

# 特定测试
uv run pytest tests/test_markdown.py -k "test_bold" -v

# 覆盖率 HTML 报告
uv run coverage html
open htmlcov/index.html
```

### 测试文件对应关系

| 测试文件 | 覆盖模块 | 关键测试场景 |
|---------|---------|------------|
| `test_models.py` | `models.py` | 数据类实例化、字段默认值 |
| `test_config.py` | `config.py` | TOML 加载、路径解析、pydantic 验证错误 |
| `test_i18n.py` | `i18n.py` | EN/ZH 翻译、格式化、CJK 语言检测 |
| `test_markdown.py` | `markdown.py` | 各种 Markdown 语法、消息分割 |
| `test_session.py` | `session.py` | 多会话、锁机制、v1→v2 迁移、JSON 持久化 |
| `test_gemini.py` | `gemini.py` | JSONL 完整事件序列、超时/kill、事件解析 |
| `test_streaming.py` | `streaming.py` | 节流逻辑、freeze/finish 生命周期 |
| `test_telegram.py` | `telegram_platform.py` | 消息处理、群聊过滤、callback 路由、API 调用 |
| `test_engine.py` | `engine.py` | 命令分发、端到端场景、session resume、callback |
| `test_cli.py` | `cli.py` | 启动流程、配置加载、参数解析 |
| `test_card.py` | `card.py` | CardBuilder 流式 API、render_text、collect_buttons |
| `test_ratelimit.py` | `ratelimit.py` | 滑动窗口、多 key 独立、cleanup loop |
| `test_dedup.py` | `dedup.py` | TTL 去重、expired 清理 |

## 添加新功能

以「新增 `/ping` 命令」为例：

**1. `i18n.py`** — 添加消息键：
```python
class MsgKey(StrEnum):
    PONG = "pong"

MESSAGES[MsgKey.PONG] = {
    Language.EN: "🏓 Pong!",
    Language.ZH: "🏓 Pong！",
}
```

**2. `engine.py`** — 注册命令处理：
```python
# 在 handle_command() 的 match 块中添加：
case "/ping":
    await self._cmd_ping(msg)

# 添加实现方法：
async def _cmd_ping(self, msg: Message) -> None:
    await self._reply(msg, self._i18n.t(MsgKey.PONG))
```

**3. `telegram_platform.py`** — 注册 CommandHandler（`start()` 中）：
```python
CommandHandler(
    ["start", ..., "ping"],  # 添加 "ping"
    self._handle_update,
)
```

**4. `tests/test_engine.py`** — 添加测试：
```python
async def test_handle_command_ping() -> None:
    engine, _agent, platform = _make_engine()
    msg = _make_message()
    await engine.handle_command(msg, "/ping")
    platform.send.assert_called_once()
    assert "Pong" in platform.send.call_args[0][1]
```

**5. `tests/test_i18n.py`** — 验证翻译覆盖：

`test_t_all_keys_have_translations` 会自动覆盖所有新 key。

## Python 编码规范

参考 [Trail of Bits Modern Python](https://github.com/trailofbits/cookiecutter-python)。关键规则：

- **不用** `from __future__ import annotations`（Python 3.12+）
- 用 `X | Y` 代替 `Union[X, Y]`，`X | None` 代替 `Optional[X]`
- 用 `list[X]`、`dict[K,V]`、`tuple[X, ...]` 内置类型
- 用 `type Alias = ...`（PEP 695）定义类型别名
- 依赖管理用 `uv add` / `uv remove`，不手动编辑 `pyproject.toml` 的 dependencies
- 开发依赖用 `[dependency-groups]`（PEP 735），不用 `optional-dependencies`

## 版本发布

```bash
# 1. 确保所有检查通过
bash dev.sh check

# 2. 提升版本（自动更新 CHANGELOG.md、打 tag、push）
bash dev.sh bump

# 3. GitHub Actions 自动发布到 PyPI（触发条件：tag push）
```

版本号存储在 `pyproject.toml`，`__version__` 通过 `importlib.metadata.version("tg-gemini")` 动态读取。
