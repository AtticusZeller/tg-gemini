# Plan: v4 改进 — 日志增强、Skills/Commands 支持、Telegram 菜单

## 背景

v3 已实现核心功能（群聊支持），但存在三个体验问题：

1. **日志消息太少** — 关键路径缺少 INFO 级别日志，排障困难
2. **未支持 Gemini CLI 生态** — 无法识别 `.gemini/commands/*.toml` 命令和 Skills
3. **Telegram 命令菜单未设置** — 用户看不到可用的 `/command` 列表

**参考实现**:
- Gemini CLI Commands: `docs/gemini-cli/command.md`
- cc-connect Skills: `core/skill.go` — 从 `<skill_name>/SKILL.md` 加载
- cc-connect Commands: `core/command.go` — 从 `.gemini/commands/*.toml` 加载

---

## 概念区分

| 特性 | **Skills** (技能) | **Commands** (命令) |
|------|-------------------|---------------------|
| **来源** | `SKILL.md` in skill dirs | `.gemini/commands/*.toml` |
| **格式** | Markdown + YAML frontmatter | TOML |
| **用途** | 预定义的 agent 能力 | 用户自定义快捷提示 |
| **调用** | `/skill_name args` | `/command_name args` |
| **prompt** | 指导 agent 如何执行 | 直接发送给 agent 的内容 |

---

## Task 1: 增强日志覆盖

### 目标
关键路径都有 INFO/DEBUG 级别日志。

### 新增日志点

| 文件 | 位置 | 级别 | 内容 |
|------|------|------|------|
| `cli.py` | `start()` | INFO | `tg-gemini starting, version=X.Y.Z` |
| `cli.py` | 初始化后 | INFO | `loaded N skills, M commands` |
| `config.py` | `load_config()` | INFO | `config loaded from path` |
| `telegram_platform.py` | `start()` | INFO | `bot started: @username` |
| `telegram_platform.py` | `start()` | INFO | `commands menu set: N commands` |
| `engine.py` | `handle_command()` | INFO | `executing: cmd=X, user=Y` |
| `engine.py` | `_run_gemini()` | INFO | `gemini started: model=X` |
| `commands.py` | `load()` | INFO | `loaded command: /name from path` |
| `skills.py` | `load()` | INFO | `loaded skill: name from path` |

---

## Task 2: Skills 系统

### 目标
支持从 skill 目录加载 Skills，格式与 cc-connect 一致。

### 目录结构

```
<skill_dir>/
├── review/
│   └── SKILL.md
├── git/
│   └── SKILL.md
└── test/
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
3. Check for performance problems

Provide actionable feedback.
```

### 实现

```python
# src/tg_gemini/skills.py
from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class Skill:
    name: str              # 目录名 (review, git)
    display_name: str      # frontmatter name or 目录名
    description: str       # frontmatter description or 第一行
    prompt: str            # body 内容
    source_dir: Path


class SkillRegistry:
    def __init__(self, skill_dirs: list[Path]) -> None:
        self._skill_dirs = skill_dirs
        self._skills: dict[str, Skill] = {}

    def load(self) -> int:
        """扫描 skill_dirs 加载所有 SKILL.md"""
        count = 0
        for dir_path in self._skill_dirs:
            if not dir_path.exists():
                continue
            for subdir in dir_path.iterdir():
                if not subdir.is_dir():
                    continue
                skill_file = subdir / "SKILL.md"
                if skill_file.exists():
                    try:
                        skill = self._parse_skill(skill_file, subdir.name)
                        self._skills[skill.name.lower()] = skill
                        count += 1
                    except Exception as exc:
                        logger.warning("failed to load skill", path=str(skill_file), error=exc)
        return count

    def _parse_skill(self, file: Path, name: str) -> Skill:
        content = file.read_text()
        frontmatter, body = self._extract_frontmatter(content)

        return Skill(
            name=name,
            display_name=frontmatter.get("name", name),
            description=frontmatter.get("description", body.strip().split("\n")[0][:80]),
            prompt=body.strip(),
            source_dir=file.parent,
        )

    def _extract_frontmatter(self, content: str) -> tuple[dict, str]:
        """提取 YAML frontmatter，返回 (frontmatter_dict, body)"""
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        try:
            frontmatter = yaml.safe_load(parts[1]) or {}
            return frontmatter, parts[2]
        except yaml.YAMLError:
            return {}, content

    def get(self, name: str) -> Skill | None:
        """name 比较时忽略大小写和连字符/下划线"""
        normalized = name.lower().replace("-", "_")
        for key, skill in self._skills.items():
            if key.replace("-", "_") == normalized:
                return skill
        return None

    def list_all(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    @staticmethod
    def build_invocation_prompt(skill: Skill, args: str) -> str:
        """构建调用 skill 的完整 prompt"""
        parts = [
            f"The user wants you to execute the skill: {skill.display_name or skill.name}",
            "",
            f"## Description: {skill.description}",
            "",
            "## Skill Instructions:",
            skill.prompt,
        ]
        if args:
            parts.extend(["", "## User Arguments:", args])
        parts.extend(["", "Please follow the skill instructions to complete the task."])
        return "\n".join(parts)
```

---

## Task 3: Gemini Commands 系统

### 目标
支持从 `.gemini/commands/` 加载 TOML 命令。

### 目录结构

```
<work_dir>/
└── .gemini/
    └── commands/
        ├── review.toml       → /review
        ├── test.toml         → /test
        └── git/
            └── commit.toml   → /git-commit  (`:` 自动替换为 `-`，Telegram 不支持 `:`)
```

### TOML 格式

```toml
# .gemini/commands/review.toml
description = "Review code for issues"
prompt = """
You are an expert code reviewer. Review this:

{{args}}
"""
```

### 完整语法支持

| 语法 | 说明 | 示例 |
|------|------|------|
| `{{args}}` | 替换为用户参数 | `prompt = "Review: {{args}}"` |
| `!{cmd}` | 执行 shell 命令（需用户确认） | `!{git diff --staged}` |
| `@{filepath}` | 注入文件内容 | `@{docs/guide.md}` |

### 实现

```python
# src/tg_gemini/commands.py
from dataclasses import dataclass
from pathlib import Path
import tomllib
import shlex
import subprocess

@dataclass
class GeminiCommand:
    name: str              # "review" or "git-commit" (`:` 替换为 `-`)
    description: str
    prompt: str
    source_path: Path


class CommandLoader:
    def __init__(self, work_dir: Path) -> None:
        self._work_dir = work_dir
        self._commands: dict[str, GeminiCommand] = {}

    def load(self) -> int:
        """扫描 .gemini/commands/ 加载所有 .toml"""
        commands_dir = self._work_dir / ".gemini" / "commands"
        if not commands_dir.exists():
            return 0

        count = 0
        for toml_file in commands_dir.rglob("*.toml"):
            try:
                cmd = self._parse_command(toml_file, commands_dir)
                self._commands[cmd.name.lower()] = cmd
                count += 1
            except Exception as exc:
                logger.warning("failed to load command", path=str(toml_file), error=exc)
        return count

    def _parse_command(self, file: Path, base_dir: Path) -> GeminiCommand:
        """解析单个 toml 文件"""
        rel_path = file.relative_to(base_dir)
        # git/commit.toml -> git:commit
        name = str(rel_path.with_suffix("")).replace("/", ":").replace("\\", ":")

        with file.open("rb") as f:
            data = tomllib.load(f)

        prompt = data.get("prompt", "").strip()
        if not prompt:
            raise ValueError("missing 'prompt' field")

        description = data.get("description", f"Command: {name}")

        return GeminiCommand(
            name=name,
            description=description,
            prompt=prompt,
            source_path=file,
        )

    def get(self, name: str) -> GeminiCommand | None:
        """获取命令，name 比较忽略大小写"""
        return self._commands.get(name.lower())

    def list_all(self) -> list[GeminiCommand]:
        return sorted(self._commands.values(), key=lambda c: c.name)

    async def expand_prompt(self, command: GeminiCommand, args: str) -> str:
        """
        完整语法支持:
        1. {{args}} -> 用户参数
        2. !{cmd} -> shell 命令输出（需确认）
        3. @{filepath} -> 文件内容
        """
        prompt = command.prompt

        # Step 1: 处理 @{filepath} 文件注入
        prompt = await self._inject_files(prompt)

        # Step 2: 处理 {{args}}
        if "{{args}}" in prompt:
            prompt = prompt.replace("{{args}}", args)
        elif args:
            # Gemini CLI 行为：无 {{args}} 时追加到末尾
            prompt = prompt + "\n\n" + args

        # Step 3: 处理 !{cmd} shell 命令
        prompt = await self._execute_shell_commands(prompt)

        return prompt

    async def _inject_files(self, prompt: str) -> str:
        """替换 @{filepath} 为文件内容"""
        import re
        pattern = r'@\{([^}]+)\}'

        def replace_file(match: re.Match) -> str:
            filepath = match.group(1).strip()
            full_path = self._work_dir / filepath
            if not full_path.exists():
                return f"[File not found: {filepath}]"
            try:
                return full_path.read_text()
            except Exception as exc:
                return f"[Error reading {filepath}: {exc}]"

        return re.sub(pattern, replace_file, prompt)

    async def _execute_shell_commands(self, prompt: str) -> str:
        """替换 !{cmd} 为命令输出（需用户确认 - v4.1 实现）"""
        # v4 版本：直接执行（风险）
        # v4.1 版本：通过 Telegram 发送确认对话框
        import re
        pattern = r'!\{([^}]+)\}'

        def replace_cmd(match: re.Match) -> str:
            cmd = match.group(1).strip()
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=30, cwd=self._work_dir
                )
                output = result.stdout
                if result.stderr:
                    output += f"\n[stderr: {result.stderr}]"
                if result.returncode != 0:
                    output += f"\n[exit code: {result.returncode}]"
                return output
            except Exception as exc:
                return f"[Command failed: {exc}]"

        return re.sub(pattern, replace_cmd, prompt)

    def reload(self) -> int:
        self._commands.clear()
        return self.load()
```

---

## Task 4: Engine 集成 Skills + Commands

### 命令解析逻辑

用户输入 `/xxx`，Engine 按以下顺序解析：

1. **内置命令** (`/new`, `/help`, `/list` 等) — 最高优先级
2. **Commands** (`/review`, `/git:commit`) — 从 `.gemini/commands/` 加载
3. **Skills** (`/skill_name`) — 从 skill dirs 加载

### 实现

```python
# engine.py
class Engine:
    def __init__(
        self,
        config: AppConfig,
        agent: GeminiAgent,
        platform: TelegramPlatform,
        sessions: SessionManager,
        i18n: I18n,
        rate_limiter: RateLimiter | None = None,
        dedup: MessageDedup | None = None,
        skill_dirs: list[Path] | None = None,
    ) -> None:
        # ... existing init ...

        # Load Commands
        self._cmd_loader = CommandLoader(Path(config.gemini.work_dir))
        cmd_count = self._cmd_loader.load()

        # Load Skills
        self._skill_registry = SkillRegistry(skill_dirs or [])
        skill_count = self._skill_registry.load()

        logger.info("commands and skills loaded", commands=cmd_count, skills=skill_count)

    async def handle_command(self, msg: Message, raw: str) -> bool:
        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]  # "/git-commit@botname" -> "/git-commit"
        args = parts[1].strip() if len(parts) > 1 else ""
        cmd_name = cmd[1:]  # 去掉前导 "/"

        # 1. 内置命令
        match cmd:
            case "/new": await self._cmd_new(msg); return True
            case "/help": await self._cmd_help(msg); return True
            case "/commands":
                if args == "reload":
                    await self._reload_commands_and_menu(msg)
                return True
            # ... other built-in commands ...

        # 2. Commands (自定义命令)
        if command := self._cmd_loader.get(cmd_name):
            logger.info("executing command", cmd=cmd_name, args=args)
            expanded = await self._cmd_loader.expand_prompt(command, args)
            await self._send_to_gemini(msg, expanded)
            return True

        # 3. Skills (技能)
        if skill := self._skill_registry.get(cmd_name):
            logger.info("executing skill", skill=skill.name, args=args)
            prompt = SkillRegistry.build_invocation_prompt(skill, args)
            await self._send_to_gemini(msg, prompt)
            return True

        # 未知命令
        await self._reply(msg, self._i18n.t(MsgKey.UNKNOWN_CMD))
        return True

    async def _send_to_gemini(self, msg: Message, content: str) -> None:
        """发送内容给 Gemini 处理"""
        new_msg = Message(
            session_key=msg.session_key,
            platform=msg.platform,
            user_id=msg.user_id,
            user_name=msg.user_name,
            content=content,
            reply_ctx=msg.reply_ctx,
        )
        session = self._sessions.get_or_create(msg.session_key)
        await self._process(new_msg, session)

    async def _reload_commands_and_menu(self, msg: Message) -> None:
        """重新加载命令和 skills，刷新菜单"""
        cmd_count = self._cmd_loader.reload()
        self._skill_registry.invalidate()
        skill_count = self._skill_registry.load()

        await self._reply(msg, f"Reloaded: {cmd_count} commands, {skill_count} skills")
        await self._refresh_commands_menu()
```

---

## Task 5: Telegram 命令菜单

### 实现

```python
# telegram_platform.py
from telegram import BotCommand

async def set_commands_menu(self, commands: list[tuple[str, str]]) -> None:
    """设置 Telegram 命令菜单"""
    if not self._app:
        return
    try:
        bot_commands = [
            BotCommand(name, desc[:100])
            for name, desc in commands
        ]
        await self._app.bot.set_my_commands(bot_commands)
        logger.info("commands menu set", count=len(bot_commands))
    except Exception as exc:
        logger.warning("failed to set commands menu", error=exc)


# engine.py
async def _refresh_commands_menu(self) -> None:
    """构建完整命令列表并刷新菜单"""
    commands: list[tuple[str, str]] = [
        # 内置命令
        ("new", "Start new session"),
        ("list", "List all sessions"),
        ("switch", "Switch active session"),
        ("current", "Show current session"),
        ("history", "Show conversation history"),
        ("name", "Rename session"),
        ("delete", "Delete sessions"),
        ("status", "Show status"),
        ("model", "Show/switch model"),
        ("mode", "Show/switch mode"),
        ("lang", "Switch language"),
        ("quiet", "Toggle quiet mode"),
        ("stop", "Stop agent"),
        ("help", "Show help"),
    ]

    # Commands（优先于 Skills，前缀 [CMD]）
    for cmd in self._cmd_loader.list_all():
        commands.append((cmd.name, f"[CMD] {cmd.description}"))

    # Skills（前缀 [SKILL]）
    for skill in self._skill_registry.list_all():
        commands.append((skill.name, f"[SKILL] {skill.description}"))

    await self._platform.set_commands_menu(commands)
```

---

## 依赖关系

```
Task 2 (Skills) ──┐
                  ├──→ Task 4 (Engine) ──→ Task 5 (Menu) ──→ 测试
Task 3 (Commands)─┘         ↑
                            │
Task 1 (Logs) ──────────────┘
```

**执行顺序**: Task 2 → Task 3 → Task 1 → Task 4 → Task 5

---

## 文件变更

| 文件 | 变更 |
|------|------|
| `src/tg_gemini/skills.py` | **新增** — SkillRegistry |
| `src/tg_gemini/commands.py` | **新增** — CommandLoader |
| `src/tg_gemini/engine.py` | 集成 Skills + Commands，刷新菜单 |
| `src/tg_gemini/telegram_platform.py` | 增加 `set_commands_menu` |
| `src/tg_gemini/cli.py` | 传递 `skill_dirs` 给 Engine |
| `tests/test_skills.py` | **新增** — Skills 测试 |
| `tests/test_commands.py` | **新增** — Commands 测试 |

---

## 配置示例

```toml
# config.toml
[telegram]
token = "BOT_TOKEN"

[gemini]
work_dir = "."
mode = "yolo"

# Skill 目录（可选，默认不配置）
skill_dirs = ["~/.tg-gemini/skills", "./skills"]
```

---

## 使用示例

```bash
# 1. 创建 Command
mkdir -p .gemini/commands
cat > .gemini/commands/review.toml << 'EOF'
description = "Review code for issues"
prompt = """Review this code:

{{args}}

Focus on: bugs, security, performance."""
EOF

# 2. 创建 Skill
mkdir -p ~/.tg-gemini/skills/refactor
cat > ~/.tg-gemini/skills/refactor/SKILL.md << 'EOF'
---
name: Refactor Code
description: Refactor code to be cleaner
---

You are a refactoring expert. Analyze the code and suggest improvements for:
1. Readability
2. Performance
3. Maintainability

Provide before/after examples.
EOF

# 3. 在 Telegram 使用
/review @myfile.py        # 使用 Command
/refactor @myfile.py      # 使用 Skill
/commands reload          # 重新加载
```

---

## 验证清单

1. `bash dev.sh check` — 全通过，覆盖率 ≥98%
2. 启动日志显示：版本、加载的命令数、skill 数
3. Telegram 菜单显示所有命令（内置 + Commands + Skills）
4. `/review code` — Command 正确执行，`{{args}}` 替换
5. `/refactor code` — Skill 正确执行，调用 prompt 包装
6. `/git-commit` — 命名空间命令正确解析（`:` 替换为 `-`）
7. `/commands reload` — 重新加载并刷新菜单
