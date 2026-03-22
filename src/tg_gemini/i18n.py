"""Internationalization support for tg-gemini."""

from enum import StrEnum

__all__ = ["MESSAGES", "I18n", "Language", "MsgKey"]


class Language(StrEnum):
    """Supported languages."""

    EN = "en"
    ZH = "zh"


class MsgKey(StrEnum):
    """Message keys for translation lookups."""

    HELP = "help"
    SESSION_BUSY = "session_busy"
    SESSION_NEW = "session_new"
    MODEL_SWITCHED = "model_switched"
    MODEL_CURRENT = "model_current"
    MODE_SWITCHED = "mode_switched"
    MODE_CURRENT = "mode_current"
    STOP_OK = "stop_ok"
    ERROR_PREFIX = "error_prefix"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    UNKNOWN_CMD = "unknown_cmd"
    EMPTY_RESPONSE = "empty_response"
    SESSION_START_FAILED = "session_start_failed"


MESSAGES: dict[MsgKey, dict[Language, str]] = {
    MsgKey.HELP: {
        Language.EN: "Commands: /new – new session | /stop – stop agent | /model [name] – switch model | /mode [mode] – switch mode (default/auto_edit/yolo/plan) | /help – this help",
        Language.ZH: "命令：/new – 新会话 | /stop – 停止 agent | /model [名称] – 切换模型 | /mode [模式] – 切换模式（default/auto_edit/yolo/plan）| /help – 帮助",
    },
    MsgKey.SESSION_BUSY: {
        Language.EN: "⏳ Agent is busy, please wait.",
        Language.ZH: "⏳ Agent 正忙，请稍候。",
    },
    MsgKey.SESSION_NEW: {
        Language.EN: "🆕 New session started.",
        Language.ZH: "🆕 已开始新会话。",
    },
    MsgKey.MODEL_SWITCHED: {
        Language.EN: "✅ Model switched to: {}",
        Language.ZH: "✅ 模型已切换为：{}",
    },
    MsgKey.MODEL_CURRENT: {
        Language.EN: "Current model: {}",
        Language.ZH: "当前模型：{}",
    },
    MsgKey.MODE_SWITCHED: {
        Language.EN: "✅ Mode switched to: {}",
        Language.ZH: "✅ 模式已切换为：{}",
    },
    MsgKey.MODE_CURRENT: {Language.EN: "Current mode: {}", Language.ZH: "当前模式：{}"},
    MsgKey.STOP_OK: {
        Language.EN: "🛑 Agent stopped.",
        Language.ZH: "🛑 Agent 已停止。",
    },
    MsgKey.ERROR_PREFIX: {Language.EN: "❌ Error: {}", Language.ZH: "❌ 错误：{}"},
    MsgKey.THINKING: {Language.EN: "💭 Thinking…", Language.ZH: "💭 思考中…"},
    MsgKey.TOOL_USE: {Language.EN: "🔧 {}: {}", Language.ZH: "🔧 {}：{}"},
    MsgKey.TOOL_RESULT: {Language.EN: "📋 Result: {}", Language.ZH: "📋 结果：{}"},
    MsgKey.UNKNOWN_CMD: {
        Language.EN: "Unknown command. Use /help for available commands.",
        Language.ZH: "未知命令，使用 /help 查看可用命令。",
    },
    MsgKey.EMPTY_RESPONSE: {Language.EN: "（no response）", Language.ZH: "（无响应）"},
    MsgKey.SESSION_START_FAILED: {
        Language.EN: "❌ Failed to start agent session: {}",
        Language.ZH: "❌ 启动 agent 会话失败：{}",
    },
}


class I18n:
    """Internationalization helper for message translation."""

    def __init__(self, lang: Language | str = Language.EN):
        """Initialize with a language.

        Args:
            lang: Language enum or string code ("en" or "zh").
        """
        self._lang = Language(lang) if isinstance(lang, str) else lang

    @property
    def lang(self) -> Language:
        """Get the current language."""
        return self._lang

    def set_lang(self, lang: Language | str) -> None:
        """Set the current language.

        Args:
            lang: Language enum or string code ("en" or "zh").
        """
        self._lang = Language(lang) if isinstance(lang, str) else lang

    def t(self, key: MsgKey) -> str:
        """Translate a message key, falling back to EN.

        Args:
            key: The message key to translate.

        Returns:
            The translated string, or the key name if not found.
        """
        translations = MESSAGES.get(key, {})
        return translations.get(self._lang, translations.get(Language.EN, str(key)))

    def tf(self, key: MsgKey, *args: object) -> str:
        """Translate a message key and format with args.

        Args:
            key: The message key to translate.
            *args: Format arguments.

        Returns:
            The translated and formatted string.
        """
        return self.t(key).format(*args)

    @staticmethod
    def detect_language(text: str) -> Language:
        """Detect language from text content.

        CJK characters (Chinese, Japanese, Korean) are detected as ZH.
        Everything else defaults to EN.

        Args:
            text: The text to analyze.

        Returns:
            Detected Language enum.
        """
        for ch in text:
            cp = ord(ch)
            if (
                0x4E00 <= cp <= 0x9FFF  # CJK Unified Ideographs
                or 0x3400 <= cp <= 0x4DBF  # CJK Extension A
                or 0x20000 <= cp <= 0x2A6DF  # CJK Extension B
            ):
                return Language.ZH
        return Language.EN
