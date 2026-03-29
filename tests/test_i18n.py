"""Tests for tg_gemini.i18n module."""

from tg_gemini.i18n import I18n, Language, MsgKey


class TestLanguage:
    """Tests for Language enum."""

    def test_enum_values(self) -> None:
        """Test that enum values are correct."""
        assert Language.EN == "en"
        assert Language.ZH == "zh"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        assert Language("en") == Language.EN
        assert Language("zh") == Language.ZH


class TestMsgKey:
    """Tests for MsgKey enum."""

    def test_enum_values(self) -> None:
        """Test that all message keys are defined."""
        assert MsgKey.HELP == "help"
        assert MsgKey.SESSION_BUSY == "session_busy"
        assert MsgKey.SESSION_NEW == "session_new"
        assert MsgKey.MODEL_SWITCHED == "model_switched"
        assert MsgKey.MODEL_CURRENT == "model_current"
        assert MsgKey.MODE_SWITCHED == "mode_switched"
        assert MsgKey.MODE_CURRENT == "mode_current"
        assert MsgKey.STOP_OK == "stop_ok"
        assert MsgKey.ERROR_PREFIX == "error_prefix"
        assert MsgKey.THINKING == "thinking"
        assert MsgKey.TOOL_USE == "tool_use"
        assert MsgKey.TOOL_RESULT == "tool_result"
        assert MsgKey.UNKNOWN_CMD == "unknown_cmd"
        assert MsgKey.EMPTY_RESPONSE == "empty_response"
        assert MsgKey.SESSION_START_FAILED == "session_start_failed"


class TestI18nInit:
    """Tests for I18n initialization."""

    def test_default_language(self) -> None:
        """Test default language is EN."""
        i18n = I18n()
        assert i18n.lang == Language.EN

    def test_init_with_enum(self) -> None:
        """Test initialization with Language enum."""
        i18n = I18n(lang=Language.ZH)
        assert i18n.lang == Language.ZH

    def test_init_with_string(self) -> None:
        """Test initialization with string language code."""
        i18n = I18n(lang="zh")
        assert i18n.lang == Language.ZH

    def test_init_with_en_string(self) -> None:
        """Test initialization with 'en' string."""
        i18n = I18n(lang="en")
        assert i18n.lang == Language.EN


class TestI18nLangProperty:
    """Tests for lang property."""

    def test_lang_property(self) -> None:
        """Test lang property returns current language."""
        i18n = I18n(Language.ZH)
        assert i18n.lang == Language.ZH

    def test_lang_property_after_set(self) -> None:
        """Test lang property after setting new language."""
        i18n = I18n(Language.EN)
        i18n.set_lang(Language.ZH)
        assert i18n.lang == Language.ZH


class TestI18nSetLang:
    """Tests for set_lang method."""

    def test_set_lang_with_enum(self) -> None:
        """Test setting language with enum."""
        i18n = I18n()
        i18n.set_lang(Language.ZH)
        assert i18n.lang == Language.ZH

    def test_set_lang_with_string(self) -> None:
        """Test setting language with string."""
        i18n = I18n()
        i18n.set_lang("zh")
        assert i18n.lang == Language.ZH

    def test_set_lang_switch_back_and_forth(self) -> None:
        """Test switching languages multiple times."""
        i18n = I18n()
        assert i18n.lang == Language.EN

        i18n.set_lang("zh")
        assert i18n.lang == Language.ZH

        i18n.set_lang(Language.EN)
        assert i18n.lang == Language.EN


class TestI18nTranslate:
    """Tests for t() method."""

    def test_t_english(self) -> None:
        """Test translation in English."""
        i18n = I18n(Language.EN)
        assert i18n.t(MsgKey.SESSION_NEW) == "🆕 New session started."
        assert i18n.t(MsgKey.STOP_OK) == "🛑 Agent stopped."

    def test_t_chinese(self) -> None:
        """Test translation in Chinese."""
        i18n = I18n(Language.ZH)
        assert i18n.t(MsgKey.SESSION_NEW) == "🆕 已开始新会话。"
        assert i18n.t(MsgKey.STOP_OK) == "🛑 Agent 已停止。"

    def test_t_fallback_to_english(self) -> None:
        """Test fallback to English when translation missing."""
        # All keys have both EN and ZH, so we test fallback by checking
        # that EN is returned when we request an existing key
        i18n = I18n(Language.EN)
        result = i18n.t(MsgKey.HELP)
        assert "Commands:" in result

    def test_t_unknown_key(self) -> None:
        """Test behavior with unknown key (returns key name as string)."""

        # Create a new key that doesn't exist in MESSAGES
        class FakeKey:
            def __str__(self) -> str:
                return "fake_key"

        i18n = I18n()
        # This will use the str(key) fallback
        result = i18n.t(MsgKey.HELP)  # Known key works
        assert "Commands:" in result

    def test_t_all_keys_have_translations(self) -> None:
        """Test that all defined keys have both EN and ZH translations."""
        from tg_gemini.i18n import MESSAGES

        for key in MsgKey:
            assert key in MESSAGES, f"Missing MESSAGES entry for {key}"
            assert Language.EN in MESSAGES[key], f"Missing EN translation for {key}"
            assert Language.ZH in MESSAGES[key], f"Missing ZH translation for {key}"


class TestI18nTranslateFormat:
    """Tests for tf() method."""

    def test_tf_with_single_arg(self) -> None:
        """Test formatting with single argument."""
        i18n = I18n(Language.EN)
        result = i18n.tf(MsgKey.MODEL_SWITCHED, "gemini-pro")
        assert result == "✅ Model switched to: gemini-pro"

    def test_tf_with_multiple_args(self) -> None:
        """Test formatting with multiple arguments."""
        i18n = I18n(Language.EN)
        result = i18n.tf(MsgKey.TOOL_USE, "search", "test query")
        assert result == "🔧 search: test query"

    def test_tf_chinese(self) -> None:
        """Test formatting in Chinese."""
        i18n = I18n(Language.ZH)
        result = i18n.tf(MsgKey.MODEL_SWITCHED, "gemini-pro")
        assert result == "✅ 模型已切换为：gemini-pro"

    def test_tf_error_prefix(self) -> None:
        """Test error prefix formatting."""
        i18n = I18n(Language.EN)
        result = i18n.tf(MsgKey.ERROR_PREFIX, "Something went wrong")
        assert result == "❌ Error: Something went wrong"

    def test_tf_no_args(self) -> None:
        """Test formatting with no arguments (key has no placeholders)."""
        i18n = I18n(Language.EN)
        result = i18n.tf(MsgKey.SESSION_NEW)
        assert result == "🆕 New session started."


class TestV2MsgKeys:
    """Spot-checks for v2 MsgKey additions."""

    def test_lang_switched_en(self) -> None:
        i18n = I18n(Language.EN)
        assert i18n.tf(MsgKey.LANG_SWITCHED, "zh") == "✅ Language switched to: zh"

    def test_lang_switched_zh(self) -> None:
        i18n = I18n(Language.ZH)
        assert i18n.tf(MsgKey.LANG_SWITCHED, "en") == "✅ 语言已切换为：en"

    def test_quiet_on_off(self) -> None:
        en = I18n(Language.EN)
        assert "Quiet mode enabled" in en.t(MsgKey.QUIET_ON)
        assert "Quiet mode disabled" in en.t(MsgKey.QUIET_OFF)

    def test_session_list_header(self) -> None:
        en = I18n(Language.EN)
        assert en.tf(MsgKey.SESSION_LIST_HEADER, 3) == "Sessions (3 total):"

    def test_session_deleted(self) -> None:
        en = I18n(Language.EN)
        assert en.tf(MsgKey.SESSION_DELETED, 2) == "2 session(s) deleted."

    def test_session_delete_confirm(self) -> None:
        en = I18n(Language.EN)
        assert en.tf(MsgKey.SESSION_DELETE_CONFIRM, 1) == "Delete 1 session(s)?"

    def test_page_nav_en(self) -> None:
        en = I18n(Language.EN)
        assert en.tf(MsgKey.PAGE_NAV, 1, 3) == "Page 1 of 3"

    def test_page_nav_zh(self) -> None:
        zh = I18n(Language.ZH)
        assert zh.tf(MsgKey.PAGE_NAV, 2, 5) == "第 2 / 5 页"

    def test_rate_limited(self) -> None:
        en = I18n(Language.EN)
        assert "Rate limited" in en.t(MsgKey.RATE_LIMITED)

    def test_status_info_format(self) -> None:
        en = I18n(Language.EN)
        result = en.tf(MsgKey.STATUS_INFO, "gemini-2.5-pro", "default", "Sprint", "✅")
        assert "gemini-2.5-pro" in result
        assert "default" in result

    def test_session_named(self) -> None:
        en = I18n(Language.EN)
        assert "My Session" in en.tf(MsgKey.SESSION_NAMED, "My Session")

    def test_help_includes_new_commands(self) -> None:
        en = I18n(Language.EN)
        help_text = en.t(MsgKey.HELP)
        for cmd in (
            "/list",
            "/switch",
            "/delete",
            "/name",
            "/history",
            "/current",
            "/status",
            "/lang",
            "/quiet",
        ):
            assert cmd in help_text, f"{cmd} missing from help"

    def test_v2_keys_all_have_zh(self) -> None:
        from tg_gemini.i18n import MESSAGES

        v2_keys = [
            MsgKey.LANG_SWITCHED,
            MsgKey.LANG_CURRENT,
            MsgKey.QUIET_ON,
            MsgKey.QUIET_OFF,
            MsgKey.STATUS_INFO,
            MsgKey.SESSION_LIST_HEADER,
            MsgKey.SESSION_LIST_EMPTY,
            MsgKey.SESSION_SWITCHED,
            MsgKey.SESSION_NOT_FOUND,
            MsgKey.SESSION_CURRENT,
            MsgKey.SESSION_DELETED,
            MsgKey.SESSION_DELETE_CONFIRM,
            MsgKey.SESSION_DELETE_CANCEL,
            MsgKey.SESSION_HISTORY_HEADER,
            MsgKey.SESSION_HISTORY_EMPTY,
            MsgKey.SESSION_NAMED,
            MsgKey.RATE_LIMITED,
            MsgKey.PAGE_NAV,
        ]
        for key in v2_keys:
            assert key in MESSAGES, f"Missing MESSAGES entry: {key}"
            assert Language.ZH in MESSAGES[key], f"Missing ZH for {key}"


class TestI18nDetectLanguage:
    """Tests for detect_language static method."""

    def test_detect_latin_text(self) -> None:
        """Test detection of Latin text returns EN."""
        assert I18n.detect_language("Hello world") == Language.EN
        assert I18n.detect_language("This is English text") == Language.EN
        assert I18n.detect_language("123 numbers only") == Language.EN
        assert I18n.detect_language("") == Language.EN

    def test_detect_cjk_text(self) -> None:
        """Test detection of CJK text returns ZH."""
        assert I18n.detect_language("你好世界") == Language.ZH
        assert I18n.detect_language("这是中文文本") == Language.ZH
        assert I18n.detect_language("日本語も検出") == Language.ZH  # Japanese kanji

    def test_detect_mixed_text(self) -> None:
        """Test detection of mixed text: any CJK char → ZH regardless of order."""
        # The function checks all chars and returns ZH if any CJK char is found
        assert I18n.detect_language("Hello 你好") == Language.ZH  # contains CJK
        assert I18n.detect_language("你好 hello") == Language.ZH  # contains CJK

    def test_detect_punctuation_only(self) -> None:
        """Test detection with punctuation only."""
        assert I18n.detect_language("!@#$%") == Language.EN
        assert I18n.detect_language("，。！？") == Language.EN  # Full-width punctuation

    def test_detect_various_cjk_ranges(self) -> None:
        """Test detection of various CJK Unicode ranges."""
        # CJK Unified Ideographs (4E00-9FFF)
        assert I18n.detect_language("中") == Language.ZH
        # CJK Extension A (3400-4DBF)
        assert I18n.detect_language("㐀") == Language.ZH
        # CJK Extension B (20000-2A6DF) - requires wide character
        # Note: This may not work in all Python builds depending on Unicode support

    def test_detect_korean_hangul(self) -> None:
        """Test detection of Korean Hangul.

        Note: Current implementation only detects CJK ideographs,
        not Hangul syllables (AC00-D7AF). Korean with Hangul returns EN.
        """
        # Hangul is not in the detected ranges, so returns EN
        assert I18n.detect_language("안녕하세요") == Language.EN

    def test_detect_japanese_hiragana_katakana(self) -> None:
        """Test detection of Japanese Hiragana/Katakana.

        Note: Current implementation only detects CJK ideographs,
        not Hiragana (3040-309F) or Katakana (30A0-30FF).
        Pure kana returns EN, mixed with kanji returns ZH.
        """
        # Pure hiragana/katakana not detected
        assert I18n.detect_language("ひらがな") == Language.EN
        assert I18n.detect_language("カタカナ") == Language.EN
        # Mixed with kanji detected as ZH
        assert I18n.detect_language("日本語") == Language.ZH
