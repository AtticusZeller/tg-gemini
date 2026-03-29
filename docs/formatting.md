# Format Conversion

This document details how `tg-gemini` converts standard Markdown from the Gemini CLI into Telegram-compatible HTML.

## 1. Context

AI agents emit standard Markdown (or Obsidian-style Markdown). The Telegram Bot API supports a restricted subset of HTML for text formatting. To provide a rich user experience while avoiding API errors, `tg-gemini` performs a "surgical" conversion.

## 2. Conversion Strategy

The conversion logic resides in `src/tg_gemini/markdown.py`. It uses a multi-phase approach to handle nested formatting and escaping correctly.

### Phase 1: Protection
- **Code Blocks:** Fenced code blocks (`` ` ``` ` ``) are extracted and replaced with temporary placeholders (e.g., `\x00CB0\x00`).
- **Inline Code:** Single backtick code is extracted and replaced with placeholders (e.g., `\x00IC0\x00`).
- This ensures that characters inside code blocks are not accidentally formatted as Markdown or HTML.

### Phase 2: HTML Escaping
- The remaining text is escaped using `html.escape()`.
- Special characters like `<`, `>`, and `&` are converted to their entity equivalents (`&lt;`, `&gt;`, `&amp;`).

### Phase 3: Markdown Mapping
- **Triple Stars:** `***text***` -> `<b><i>text</i></b>`
- **Bold:** `**text**` or `__text__` -> `<b>text</b>`
- **Italic:** `*text*` or `_text_` -> `<i>text</i>` (with word boundary checks for underscores).
- **Strikethrough:** `~~text~~` -> `<s>text</s>`
- **Links:** `[text](url)` -> `<a href="url">text</a>`
- **Headings:** `# Heading` -> `<b>Heading</b>` (Headings are flattened to bold).
- **Lists:** `- item` or `* item` -> `• item`
- **Horizontal Rules:** `---` or `***` -> `——————————`
- **Wikilinks:** `[[Link|Text]]` -> `Text`, `[[Link]]` -> `Link`
- **Callouts (Obsidain):** `> [!info] Title` -> `<b>info: Title</b>` (Supported types include info, warn, error, etc.)

### Phase 4: Reinsertion
- The protected code blocks and inline code are reinserted into the final string, wrapped in `<pre><code>` or `<code>` tags respectively.

## 3. Streaming Considerations

During streaming, the `accumulated` text is passed through the conversion engine before being sent to Telegram. Because Telegram's HTML parser is strict, the engine ensures that all tags are properly balanced and escaped even if the Markdown is incomplete (e.g., a trailing `**` that hasn't been closed yet).

## 4. Message Chunking

If a final response exceeds Telegram's 4096-character limit, the middleware handles splitting the message while attempting to maintain syntactical correctness (e.g., not splitting in the middle of an HTML tag).
