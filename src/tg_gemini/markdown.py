import html
import re


def md_to_telegram_html(text: str) -> str:
    """Convert Markdown to a subset of HTML supported by Telegram.

    Supports:
    - Fenced code blocks (with language)
    - Inline code
    - Bold, Italic, Strikethrough
    - Links
    - Headers (converted to bold)
    - Lists (bullet points)
    - Blockquotes (including Obsidian callouts)
    - Horizontal rules
    - Obsidian Wikilinks [[link]] -> link
    """
    if not text:
        return ""

    # Phase 1: Extract and protect code blocks
    code_blocks: list[str] = []

    def _replace_fenced(m: re.Match[str]) -> str:
        lang = m.group(1) or ""
        code = html.escape(m.group(2).strip())
        if lang:
            block = f'<pre><code class="language-{lang}">{code}</code></pre>'
        else:
            block = f"<pre><code>{code}</code></pre>"
        code_blocks.append(block)
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```(\w*)\n(.*?)```", _replace_fenced, text, flags=re.DOTALL)

    inline_codes: list[str] = []

    def _replace_inline(m: re.Match[str]) -> str:
        inline_codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _replace_inline, text)

    # Phase 2: Handle block-level and Obsidian elements BEFORE escaping
    # Horizontal rules
    text = re.sub(r"^\s*[\-\*_]{3,}\s*$", "——————————", text, flags=re.MULTILINE)

    # Wikilinks: [[Link|Text]] -> Text, [[Link]] -> Link
    text = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", text)

    # Blockquotes & Callouts
    placeholders: list[str] = []

    def _add_ph(tag: str, content: str) -> str:
        placeholders.append(f"<{tag}>{content}</{tag}>")
        return f"\x00PH{len(placeholders) - 1}\x00"

    # Obsidian Callouts: > [!info] Title -> <b>INFO: Title</b>
    text = re.sub(
        r"^>\s*\[!(\w+)\]\s*(.*)$",
        lambda m: _add_ph("b", f"{m.group(1).lower()}: {m.group(2)}"),
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # Standard Blockquotes
    text = re.sub(
        r"^>\s+(.+)$", lambda m: _add_ph("blockquote", m.group(1)), text, flags=re.MULTILINE
    )

    # Phase 3: HTML escape remaining content
    text = html.escape(text)

    # Phase 4: Basic Markdown transforms (inline)
    # Triple stars (Bold-Italic)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", lambda m: _add_ph("b", f"<i>{m.group(1)}</i>"), text)

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: _add_ph("b", m.group(1)), text)
    text = re.sub(r"__(.+?)__", lambda m: _add_ph("b", m.group(1)), text)

    # Italic
    text = re.sub(r"\*(.+?)\*", lambda m: _add_ph("i", m.group(1)), text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", lambda m: _add_ph("i", m.group(1)), text)

    text = re.sub(r"~~(.+?)~~", lambda m: _add_ph("s", m.group(1)), text)

    # Links
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)

    # Headers and Lists
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^[\-\*]\s+", "• ", text, flags=re.MULTILINE)

    # Reinsert placeholders
    for i, ph in enumerate(placeholders):
        text = text.replace(f"\x00PH{i}\x00", ph)

    # Phase 5: Reinsert protected code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CB{i}\x00", block)
    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00IC{i}\x00", code)

    return text


def split_message_code_fence_aware(text: str, max_len: int = 4096) -> list[str]:
    """Split a message into chunks while respecting code blocks.

    If a chunk ends inside a code block, it closes the block in the current chunk
    and re-opens it in the next chunk.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Find the best place to split
        # Prefer newlines
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            # Fallback to max_len
            split_at = max_len

        chunk = text[:split_at]
        remaining = text[split_at:]

        # Check if we are inside a code block
        pre_count = chunk.count("<pre>")
        pre_close_count = chunk.count("</pre>")

        if pre_count > pre_close_count:
            # Inside a code block!
            last_pre_start = chunk.rfind("<pre>")
            # Find the code tag inside it
            code_tag_match = re.search(r"<code[^>]*>", chunk[last_pre_start:])
            if code_tag_match:
                code_tag = code_tag_match.group(0)
                chunk += "</code></pre>"
                remaining = f"<pre>{code_tag}{remaining}"

        chunks.append(chunk)
        text = remaining.strip("\n")  # Strip leading newline for next chunk

    return chunks
