# cc-connect Format Conversion (Markdown to HTML)

This document details how **cc-connect** handles text formatting and conversion between Markdown (emitted by AI agents) and various platform-specific formats (HTML, Plain Text).

## 1. Overview

AI agents generally output standard Markdown. Since different messaging platforms have varying levels of support for rich text, `cc-connect` provides three primary conversion strategies in its `core` package:

1.  **Markdown to Simple HTML:** For platforms like Telegram.
2.  **Markdown to Plain Text (Strip):** For platforms like WeChat or LINE.
3.  **Structured Cards:** For platforms like Feishu/Lark.

## 2. Markdown to Simple HTML

**Method:** `core.MarkdownToSimpleHTML(md string)`
**File:** `core/markdown_html.go`

This method converts a subset of Markdown into a limited set of HTML tags. This is specifically designed for the **Telegram Bot API**, which supports a restricted HTML mode.

### Supported Mappings

| Markdown | HTML Tag | Notes |
| :--- | :--- | :--- |
| `**bold**` / `__bold__` | `<b>bold</b>` | |
| `*italic*` | `<i>italic</i>` | |
| `~~strike~~` | `<s>strike</s>` | |
| `` `code` `` | `<code>code</code>` | Inline code |
| ` ```lang ... ``` ` | `<pre><code>...</code></pre>` | Code blocks (escaped) |
| `[text](url)` | `<a href="url">text</a>` | Hyperlinks |
| `> quote` | `<blockquote>quote</blockquote>` | Blockquotes |
| `# Heading` | `<b>Heading</b>` | Headings are converted to bold text |
| `* list item` | `• text` | Converted to bullet points |
| `---` | `——————————` | Horizontal rules |

### Implementation Details
- **Regex-Based:** Uses a series of regular expressions to identify patterns.
- **Placeholder Protection:** To handle nested formatting (e.g., *italic* inside **bold**), it uses a placeholder system (`\x00PH0\x00`) to protect already-converted HTML tags from being matched by subsequent regex passes.
- **HTML Escaping:** All content is properly escaped (e.g., `<` becomes `&lt;`) before being wrapped in HTML tags to prevent broken messages.

## 3. Markdown to Plain Text (Stripping)

**Method:** `core.StripMarkdown(md string)`
**File:** `core/markdown.go`

Used for platforms that do not support any formatting. It removes all Markdown syntax while preserving the readability of the content.

### Logic
- **Removes:** Backticks, asterisks, underscores, hashes, and blockquote markers.
- **Transforms:** Links `[text](url)` are converted to `text (url)`.
- **Cleanup:** Collapses multiple consecutive blank lines to keep the output concise.

## 4. Rich Card Degradation

**Method:** `Card.RenderText()`
**File:** `core/card.go`

When a structured `Card` (used for interactive menus or status reports) is sent to a platform that doesn't support cards, it is "degraded" to plain text.

- **Headings:** Wrapped in double asterisks (`**Title**`).
- **Dividers:** Rendered as `---`.
- **Buttons:** Displayed as bracketed text hints (e.g., `[New Session]  [List Sessions]`).
- **Notes:** Displayed as normal text at the bottom.

## 5. Chunking & Code Fences

**Method:** `core.SplitMessageCodeFenceAware(text string, maxLen int)`
**File:** `core/markdown_html.go`

Messaging platforms often have a maximum message length (e.g., 4096 characters for Telegram). If a long message is split in the middle of a code block, it breaks the formatting.

- **Logic:** This utility splits the text into chunks but detects if a chunk ends inside a ` ``` ` block. 
- **Repair:** If it does, it automatically appends a closing ` ``` ` to the current chunk and prepends an opening ` ``` ` to the next chunk, ensuring every message fragment is syntactically valid HTML/Markdown.

---
**Source References:**
- `core/markdown_html.go`
- `core/markdown.go`
- `core/card.go`
- `platform/telegram/telegram.go`
