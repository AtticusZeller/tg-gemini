from tg_gemini.markdown import md_to_telegram_html, split_message_code_fence_aware


def test_md_to_html_empty() -> None:
    assert md_to_telegram_html("") == ""


def test_md_to_html_basic() -> None:
    assert md_to_telegram_html("**bold**") == "<b>bold</b>"
    assert md_to_telegram_html("__bold__") == "<b>bold</b>"
    assert md_to_telegram_html("*italic*") == "<i>italic</i>"
    assert md_to_telegram_html("_italic_") == "<i>italic</i>"
    assert md_to_telegram_html("~~strike~~") == "<s>strike</s>"


def test_md_to_html_escaping() -> None:
    assert md_to_telegram_html("<hello>") == "&lt;hello&gt;"
    assert md_to_telegram_html("`<b>`") == "<code>&lt;b&gt;</code>"


def test_md_to_html_code_blocks() -> None:
    md = "```python\nprint('hello')\n```"
    # Note: html.escape escapes ' to &#x27;
    expected = '<pre><code class="language-python">print(&#x27;hello&#x27;)</code></pre>'
    assert md_to_telegram_html(md) == expected


def test_md_to_html_code_blocks_no_lang() -> None:
    md = "```\nhello\n```"
    expected = "<pre><code>hello</code></pre>"
    assert md_to_telegram_html(md) == expected


def test_md_to_html_inline_code() -> None:
    assert md_to_telegram_html("`code`") == "<code>code</code>"


def test_md_to_html_nested() -> None:
    # Simple nesting without overlapping boundaries
    assert md_to_telegram_html("**bold** *italic*") == "<b>bold</b> <i>italic</i>"
    assert md_to_telegram_html("***bold italic***") == "<b><i>bold italic</i></b>"


def test_md_to_html_links() -> None:
    assert (
        md_to_telegram_html("[google](https://google.com)")
        == '<a href="https://google.com">google</a>'
    )


def test_md_to_html_headers() -> None:
    assert md_to_telegram_html("# Header") == "<b>Header</b>"
    assert md_to_telegram_html("### Header 3") == "<b>Header 3</b>"


def test_md_to_html_lists() -> None:
    assert md_to_telegram_html("- item") == "• item"
    assert md_to_telegram_html("* item") == "• item"


def test_md_to_html_horizontal_rule() -> None:
    assert md_to_telegram_html("---") == "——————————"
    assert md_to_telegram_html("***") == "——————————"
    assert md_to_telegram_html("___") == "——————————"


def test_md_to_html_blockquote() -> None:
    assert md_to_telegram_html("> quote") == "<blockquote>quote</blockquote>"


def test_md_to_html_obsidian_wikilinks() -> None:
    assert md_to_telegram_html("[[Link]]") == "Link"
    assert md_to_telegram_html("[[Link|Text]]") == "Text"


def test_md_to_html_obsidian_callouts() -> None:
    md = "> [!info] Title\n> Content"
    html = md_to_telegram_html(md)
    # The callout regex matches "> [!info] Title" and converts to "<b>info: Title</b>"
    # Then blockquote matches "> Content"
    assert "<b>info: Title</b>" in html
    assert "<blockquote>Content</blockquote>" in html


def test_md_to_html_complex() -> None:
    md = """# Title
- List item 1
- **Bold** and _italic_
```python
x = 1
```
[Link](url)
"""
    html = md_to_telegram_html(md)
    assert "<b>Title</b>" in html
    assert "• List item 1" in html
    assert "<b>Bold</b>" in html
    assert "<i>italic</i>" in html
    assert '<pre><code class="language-python">x = 1</code></pre>' in html
    assert '<a href="url">Link</a>' in html


def test_split_message_basic() -> None:
    max_len = 100
    text = "a" * 200
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    for c in chunks:
        assert len(c) <= max_len


def test_split_message_no_split_needed() -> None:
    text = "short message"
    assert split_message_code_fence_aware(text) == [text]


def test_split_message_exact_len() -> None:
    text = "a" * 10
    # This triggers the "True" branch of the initial length check
    assert split_message_code_fence_aware(text, max_len=10) == [text]


def test_split_message_loop_entry() -> None:
    # This triggers the "False" branch of the initial length check
    # so we enter the while loop
    text = "a" * 11
    chunks = split_message_code_fence_aware(text, max_len=10)
    expected_chunks = 2
    assert len(chunks) == expected_chunks


def test_split_message_no_split_needed_long() -> None:
    # Trigger False path of "if len(text) <= max_len"
    # with a string longer than default 4096 but a very large max_len
    text = "a" * 5000
    assert split_message_code_fence_aware(text, max_len=10000) == [text]


def test_split_message_force_split_no_newline() -> None:
    # Trigger split_at = max_len
    text = "a" * 20
    max_len = 10
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    assert len(chunks[0]) == max_len


def test_split_message_newline() -> None:
    max_len = 120
    safe_len = 70
    # Include a newline to trigger split_at != -1
    text = "a" * 70 + "\n" + "b" * 130
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    assert len(chunks[0]) == safe_len


def test_split_message_newline_found() -> None:
    max_len = 120
    text = "a" * 60 + "\n" + "b" * 60
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    assert chunks[0] == "a" * 60
    assert "b" * 60 in chunks[1]


def test_split_message_code_fence() -> None:
    max_len = 100
    code = "x = " + "1" * 150
    text = f'<pre><code class="language-python">{code}</code></pre>'
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    assert chunks[0].endswith("</code></pre>")
    assert chunks[1].startswith('<pre><code class="language-python">')


def test_split_message_code_fence_simple() -> None:
    max_len = 100
    code = "x = " + "1" * 150
    text = f"<pre><code>{code}</code></pre>"
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    assert chunks[0].endswith("</code></pre>")
    assert chunks[1].startswith("<pre><code>")


def test_split_message_no_code_tag() -> None:
    max_len = 10
    text = "<pre>Just some text"
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    assert "<pre>" in chunks[0]


def test_split_message_no_code_tag_v2() -> None:
    # Target line 161-162 in markdown.py
    # text starts with <pre>, then we split BEFORE any <code> tag
    text = "<pre>          " + "a" * 50
    max_len = 10 # Split after "<pre>     "
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks


def test_split_message_no_code_tag_v3() -> None:
    text = "<pre> " + "a" * 50
    max_len = 5
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks


def test_split_message_outside_code() -> None:
    max_len = 50
    text = "<pre><code>code</code></pre>\nOutside text"
    chunks = split_message_code_fence_aware(text, max_len=max_len)
    assert len(chunks) == 1
    
    text_long = "<pre><code>code</code></pre>" + "a" * 150
    chunks = split_message_code_fence_aware(text_long, max_len=max_len)
    min_chunks = 2
    assert len(chunks) >= min_chunks
    # 50 is enough to split AFTER </pre>
    assert chunks[0].endswith("</pre>") or "</code></pre>" in chunks[0]


def test_split_message_empty() -> None:
    assert split_message_code_fence_aware("") == [""]


def test_split_message_skip_loop() -> None:
    # Trigger 119 -> 151 (Skip while loop)
    # The first 'if len(text) <= max_len' handles strings <= 4096 (or max_len).
    # To reach the 'while' check and skip it, we need to bypass the FIRST check
    # but fail the WHILE check.
    # Wait, if bypassed first, text is NOT empty.
    # Let's look at the code:
    # 115: if len(text) <= max_len: return [text]
    # 119: while text:
    # If it passed 115, text is > max_len. So it WILL enter 119.
    # The only way to NOT enter 119 is if text is empty.
    # But if text is empty, it would have returned at 115 (0 <= 4096).
    # Ah! Maybe 119->151 means the loop TERMINATES.
    assert split_message_code_fence_aware("abc", max_len=10) == ["abc"]
