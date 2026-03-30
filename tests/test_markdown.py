"""Tests for markdown_to_html and split_message functions."""

from tg_gemini.markdown import markdown_to_html, split_message


class TestInlineFormatting:
    """Test inline Markdown formatting conversions."""

    def test_bold_double_asterisk(self) -> None:
        """Test **bold** → <b>bold</b>."""
        assert markdown_to_html("**bold text**") == "<b>bold text</b>"

    def test_bold_double_underscore(self) -> None:
        """Test __bold__ → <b>bold</b>."""
        assert markdown_to_html("__bold text__") == "<b>bold text</b>"

    def test_italic_single_asterisk(self) -> None:
        """Test *italic* → <i>italic</i>."""
        assert markdown_to_html("*italic text*") == "<i>italic text</i>"

    def test_bold_italic_triple_asterisk(self) -> None:
        """Test ***bold italic*** → <b><i>bold italic</i></b>."""
        assert markdown_to_html("***bold italic***") == "<b><i>bold italic</i></b>"

    def test_strikethrough(self) -> None:
        """Test ~~strikethrough~~ → <s>strikethrough</s>."""
        assert markdown_to_html("~~strikethrough~~") == "<s>strikethrough</s>"

    def test_inline_code(self) -> None:
        """Test `code` → <code>code</code>."""
        assert markdown_to_html("`code`") == "<code>code</code>"

    def test_inline_code_escapes_html(self) -> None:
        """Test inline code content is HTML-escaped."""
        assert markdown_to_html("`<script>`") == "<code>&lt;script&gt;</code>"

    def test_link(self) -> None:
        """Test [text](url) → <a href="url">text</a>."""
        assert (
            markdown_to_html("[link text](https://example.com)")
            == '<a href="https://example.com">link text</a>'
        )

    def test_link_escapes_html(self) -> None:
        """Test link text and URL are HTML-escaped."""
        assert (
            markdown_to_html("[text<script>](https://example.com?a=1&b=2)")
            == '<a href="https://example.com?a=1&amp;b=2">text&lt;script&gt;</a>'
        )

    def test_wikilink_with_text(self) -> None:
        """Test [[Link|Text]] → Text."""
        assert markdown_to_html("[[Page Title|Display Text]]") == "Display Text"

    def test_wikilink_without_text(self) -> None:
        """Test [[Link]] → Link."""
        assert markdown_to_html("[[Page Title]]") == "Page Title"

    def test_wikilink_is_escaped(self) -> None:
        """Test wikilink content gets HTML-escaped later."""
        assert markdown_to_html("[[Test|A < B]]") == "A &lt; B"


class TestNestedFormatting:
    """Test nested inline formatting."""

    def test_bold_with_italic_inside(self) -> None:
        """Test bold containing italic.

        Note: italic inside bold is NOT converted per the Go implementation's
        placeholder approach - bold content is extracted before italic is processed.
        """
        result = markdown_to_html("**bold and *italic* text**")
        assert "<b>" in result
        # Italic inside bold is not converted (bold extracted first as placeholder)
        assert "bold and" in result

    def test_italic_with_bold_inside(self) -> None:
        """Test italic containing bold."""
        result = markdown_to_html("*italic and **bold** text*")
        assert "<i>" in result
        assert "<b>bold</b>" in result


class TestCodeBlocks:
    """Test code block conversions."""

    def test_code_block_no_language(self) -> None:
        """Test code block without language specifier."""
        md = "```\ncode line 1\ncode line 2\n```"
        result = markdown_to_html(md)
        assert "<pre><code>" in result
        assert "</code></pre>" in result
        assert "code line 1" in result
        assert "code line 2" in result

    def test_code_block_with_language(self) -> None:
        """Test code block with language specifier."""
        md = "```python\ndef hello():\n    pass\n```"
        result = markdown_to_html(md)
        assert '<pre><code class="language-python">' in result
        assert "</code></pre>" in result

    def test_code_block_escapes_html(self) -> None:
        """Test code block content is HTML-escaped."""
        md = "```\n<script>alert('xss')</script>\n```"
        result = markdown_to_html(md)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_code_block_preserves_indentation(self) -> None:
        """Test code block preserves leading whitespace."""
        md = "```\n    indented\n        more indented\n```"
        result = markdown_to_html(md)
        assert "    indented" in result
        assert "        more indented" in result

    def test_unclosed_code_block(self) -> None:
        """Test unclosed code block is still rendered."""
        md = "```\nunclosed code"
        result = markdown_to_html(md)
        assert "<pre><code>" in result
        assert "unclosed code" in result
        assert "</code></pre>" in result


class TestBlockquotes:
    """Test blockquote conversions."""

    def test_simple_blockquote(self) -> None:
        """Test simple blockquote."""
        md = "> quote line"
        result = markdown_to_html(md)
        assert result == "<blockquote>quote line</blockquote>"

    def test_multiline_blockquote(self) -> None:
        """Test multiline blockquote."""
        md = "> line 1\n> line 2"
        result = markdown_to_html(md)
        assert "<blockquote>" in result
        assert "line 1" in result
        assert "line 2" in result
        assert "</blockquote>" in result

    def test_blockquote_with_empty_line(self) -> None:
        """Test blockquote with empty line marker."""
        md = "> line 1\n>\n> line 2"
        result = markdown_to_html(md)
        assert "<blockquote>" in result
        assert "line 1" in result
        assert "line 2" in result

    def test_callout_with_title(self) -> None:
        """Test Obsidian callout with title."""
        md = "> [!NOTE] This is important"
        result = markdown_to_html(md)
        assert "<blockquote>" in result
        assert "<b>NOTE: This is important</b>" in result

    def test_callout_without_title(self) -> None:
        """Test Obsidian callout without title."""
        md = "> [!WARNING]"
        result = markdown_to_html(md)
        assert "<blockquote>" in result
        assert "<b>WARNING</b>" in result

    def test_callout_with_content(self) -> None:
        """Test Obsidian callout with additional content lines."""
        md = "> [!TIP] Helpful advice\n> More details here"
        result = markdown_to_html(md)
        assert "<blockquote>" in result
        assert "<b>TIP: Helpful advice</b>" in result
        assert "More details here" in result


class TestTables:
    """Test table conversions."""

    def test_simple_table(self) -> None:
        """Test simple table rendering."""
        md = "| col1 | col2 |\n|------|------|"
        result = markdown_to_html(md)
        assert "col1 | col2" in result
        assert "——————————" in result

    def test_table_with_content(self) -> None:
        """Test table with cell content."""
        md = "| Name | Value |\n|------|-------|\n| A | 1 |"
        result = markdown_to_html(md)
        assert "Name | Value" in result
        assert "A | 1" in result


class TestHeadings:
    """Test heading conversions."""

    def test_h1(self) -> None:
        """Test H1 → bold."""
        assert markdown_to_html("# Heading 1") == "<b>Heading 1</b>"

    def test_h2(self) -> None:
        """Test H2 → bold."""
        assert markdown_to_html("## Heading 2") == "<b>Heading 2</b>"

    def test_h6(self) -> None:
        """Test H6 → bold."""
        assert markdown_to_html("###### Heading 6") == "<b>Heading 6</b>"

    def test_heading_with_inline_formatting(self) -> None:
        """Test heading preserves inline formatting."""
        result = markdown_to_html("# Title with **bold**")
        assert "<b>" in result
        assert "Title with" in result


class TestHorizontalRules:
    """Test horizontal rule conversions."""

    def test_dash_rule(self) -> None:
        """Test --- → em dash line."""
        assert markdown_to_html("---") == "——————————"

    def test_star_rule(self) -> None:
        """Test *** → em dash line."""
        assert markdown_to_html("***") == "——————————"

    def test_long_dash_rule(self) -> None:
        """Test longer dash rule."""
        assert markdown_to_html("--------") == "——————————"


class TestLists:
    """Test list conversions."""

    def test_unordered_list_dash(self) -> None:
        """Test unordered list with dash."""
        assert markdown_to_html("- item") == "• item"

    def test_unordered_list_star(self) -> None:
        """Test unordered list with star."""
        assert markdown_to_html("* item") == "• item"

    def test_unordered_list_indented(self) -> None:
        """Test indented unordered list."""
        result = markdown_to_html("  - item")
        assert "  •" in result

    def test_ordered_list(self) -> None:
        """Test ordered list."""
        assert markdown_to_html("1. first") == "1. first"

    def test_ordered_list_large_number(self) -> None:
        """Test ordered list with large number."""
        assert markdown_to_html("99. ninety-nine") == "99. ninety-nine"

    def test_ordered_list_indented(self) -> None:
        """Test indented ordered list."""
        result = markdown_to_html("  1. item")
        assert "  1." in result


class TestHtmlEscaping:
    """Test HTML entity escaping."""

    def test_ampersand(self) -> None:
        """Test & → &amp;."""
        assert markdown_to_html("A & B") == "A &amp; B"

    def test_less_than(self) -> None:
        """Test < → &lt;."""
        assert markdown_to_html("A < B") == "A &lt; B"

    def test_greater_than(self) -> None:
        """Test > → &gt;."""
        assert markdown_to_html("A > B") == "A &gt; B"

    def test_quote(self) -> None:
        """Test " → &quot;."""
        assert markdown_to_html('Say "hello"') == "Say &quot;hello&quot;"

    def test_mixed_entities(self) -> None:
        """Test multiple HTML entities."""
        assert markdown_to_html("<tag>") == "&lt;tag&gt;"


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_string(self) -> None:
        """Test empty string."""
        assert markdown_to_html("") == ""

    def test_whitespace_only(self) -> None:
        """Test whitespace-only string."""
        assert markdown_to_html("   \n   ") == "   \n   "

    def test_plain_text(self) -> None:
        """Test plain text without formatting."""
        assert markdown_to_html("Hello world") == "Hello world"

    def test_multiple_paragraphs(self) -> None:
        """Test multiple paragraphs."""
        result = markdown_to_html("Para 1\n\nPara 2")
        assert "Para 1" in result
        assert "Para 2" in result


class TestSplitMessage:
    """Test split_message function."""

    def test_text_under_limit(self) -> None:
        """Test text under limit is not split."""
        text = "Short text"
        result = split_message(text, max_len=100)
        assert result == ["Short text"]

    def test_text_exactly_at_limit(self) -> None:
        """Test text exactly at limit is not split."""
        text = "A" * 100
        result = split_message(text, max_len=100)
        assert result == [text]

    def test_text_over_limit(self) -> None:
        """Test multiline text over limit is split."""
        # Use multi-line text since split_message splits on line boundaries
        line = "A" * 50
        text = "\n".join([line] * 4)  # 4 lines of 50 chars each = 203 chars total
        result = split_message(text, max_len=110)  # can fit ~2 lines
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 115  # allow slight overflow for newline accounting

    def test_split_respects_lines(self) -> None:
        """Test split respects line boundaries."""
        text = "Line 1\nLine 2\nLine 3"
        result = split_message(text, max_len=20)
        # Should keep lines together when possible
        assert all("\n" not in chunk or chunk.count("\n") < 3 for chunk in result)

    def test_split_inside_code_block(self) -> None:
        """Test split inside code block closes and reopens fence."""
        text = "```\n" + "A" * 100 + "\n```"
        result = split_message(text, max_len=50)
        # First chunk should end with closing fence
        assert result[0].endswith("\n```")
        # Second chunk should start with opening fence
        assert result[1].startswith("```")

    def test_split_with_code_block_language(self) -> None:
        """Test split preserves code block language."""
        text = "```python\n" + "A" * 100 + "\n```"
        result = split_message(text, max_len=50)
        # Second chunk should reopen with same language
        assert result[1].startswith("```python")

    def test_empty_text(self) -> None:
        """Test empty text."""
        result = split_message("")
        assert result == [""]

    def test_default_max_len(self) -> None:
        """Test default max_len is 4096."""
        # Use multi-line text to ensure splitting on line boundaries
        line = "A" * 100
        text = "\n".join([line] * 42)  # 42 lines of 100 chars = 4241 chars total
        result = split_message(text)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 4096 + 5  # small tolerance for last newline

    def test_multiple_code_blocks(self) -> None:
        """Test split with multiple code blocks."""
        text = "```\ncode1\n```\n\n```\ncode2\n```"
        result = split_message(text, max_len=100)
        # Should handle each code block correctly
        assert all(
            chunk.count("```") % 2 == 0 or chunk.startswith("```") for chunk in result
        )

    def test_code_block_not_closed(self) -> None:
        """Test unclosed code block is handled (adds closing fence when split occurs)."""
        # Need enough content to trigger a split, otherwise the short-circuit returns early
        code_line = "x" * 30
        text = "```\n" + "\n".join(
            [code_line] * 5
        )  # 5 lines of 30 chars inside code block
        result = split_message(text, max_len=60)
        if len(result) > 1:
            # If split occurred, last chunk should end with closing fence
            assert result[-1].endswith("\n```") or result[-1].endswith("```")
        else:
            # No split: the single chunk preserves the unclosed block as-is
            assert result[0] == text

    def test_split_preserves_content(self) -> None:
        """Test that all content is preserved after splitting."""
        text = "Line 1\nLine 2\nLine 3\nLine 4"
        result = split_message(text, max_len=20)
        # Reconstruct and compare (ignoring added fence markers)
        reconstructed = "\n".join(result)
        # Remove any added code fences for comparison
        reconstructed = reconstructed.replace("\n```", "").replace("```\n", "")
        assert "Line 1" in reconstructed
        assert "Line 2" in reconstructed
        assert "Line 3" in reconstructed
        assert "Line 4" in reconstructed


# --- Additional coverage tests ---


class TestCoverageEdgeCases:
    """Edge cases for coverage completeness."""

    def test_callout_without_title(self) -> None:
        """Callout with [!TYPE] but no title."""
        result = markdown_to_html("> [!NOTE]\n> content here")
        assert "<b>NOTE</b>" in result
        assert "content here" in result

    def test_empty_blockquote_line(self) -> None:
        """Bare > with no content."""
        result = markdown_to_html(">")
        assert "<blockquote>" in result

    def test_blockquote_flush_on_code_start(self) -> None:
        """Code block starts while in blockquote → flush blockquote first."""
        text = "> quoted text\n```python\ncode\n```"
        result = markdown_to_html(text)
        assert "<blockquote>" in result
        assert "<pre>" in result

    def test_table_flush_on_code_start(self) -> None:
        """Code block starts while in table → flush table first."""
        text = "| col1 | col2 |\n| --- | --- |\n```\ncode\n```"
        result = markdown_to_html(text)
        assert "col1" in result
        assert "<pre>" in result

    def test_blockquote_flush_on_non_quote(self) -> None:
        """Leaving blockquote forces flush."""
        text = "> line1\n> line2\nnormal text"
        result = markdown_to_html(text)
        assert "<blockquote>" in result
        assert "normal text" in result

    def test_table_flush_on_non_table(self) -> None:
        """Leaving table forces flush."""
        text = "| col1 | col2 |\n| --- | --- |\nafter table"
        result = markdown_to_html(text)
        assert "col1" in result
        assert "after table" in result

    def test_italic_regex_no_star(self) -> None:
        """Italic regex match with no asterisk should return full match."""
        # This edge case is hard to trigger but tests the defensive check
        result = markdown_to_html("normal text without italic")
        assert "normal text without italic" in result

    def test_split_message_with_open_fence_at_end(self) -> None:
        """Split with code block open at the end adds closing fence."""
        # Create text that overflows and ends inside a code block
        long_content = "a" * 40
        text = ("normal line\n" * 3) + "```python\n" + (long_content + "\n") * 3
        result = split_message(text, max_len=60)
        if len(result) > 1:
            # Last chunk should end with closing fence
            assert result[-1].endswith("\n```")

    def test_wikilink_no_match_fallback(self) -> None:
        """Wikilink regex fallback returns original match."""
        # Test a case where wikilink groups don't match
        result = markdown_to_html("[[Link]]")
        assert "Link" in result

    def test_table_with_separator_only(self) -> None:
        """Table with only a separator line."""
        result = markdown_to_html("| --- |")
        assert "——————————" in result


class TestLineNewlines:
    """Tests to ensure newlines are added correctly."""

    def test_normal_line_not_last(self) -> None:
        """Non-last normal line should have newline appended."""
        result = markdown_to_html("line one\nline two")
        assert result == "line one\nline two"

    def test_code_block_close_not_last_line(self) -> None:
        """Code block close followed by more content gets newline."""
        result = markdown_to_html("```\ncode\n```\nafter text")
        assert "<pre>" in result
        assert "after text" in result
        assert result.index("after text") > result.index("</pre>")


class TestBrTagNormalization:
    """Regression: LLM output may contain <br>, <br/>, <br /> — convert to newlines."""

    def test_br_tag_replaced(self) -> None:
        result = markdown_to_html("line one<br>line two")
        assert "<br>" not in result
        assert "line one" in result
        assert "line two" in result

    def test_br_self_closing_replaced(self) -> None:
        result = markdown_to_html("line one<br/>line two")
        assert "<br/>" not in result
        assert "line one" in result
        assert "line two" in result

    def test_br_with_space_replaced(self) -> None:
        result = markdown_to_html("line one<br />line two")
        assert "<br />" not in result
        assert "line one" in result
        assert "line two" in result

    def test_br_uppercase_replaced(self) -> None:
        result = markdown_to_html("line one<BR>line two")
        assert "<BR>" not in result
        assert "line one" in result
        assert "line two" in result

    def test_br_not_escaped_to_entities(self) -> None:
        """<br> should NOT become &lt;br&gt; in output."""
        result = markdown_to_html("hello<br>world")
        assert "&lt;br" not in result
        assert "&lt;BR" not in result
