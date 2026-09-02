"""Multi-line and Copied Code Cleaner for Python snippets.

Cleans code copied from documentation, ChatGPT, StackOverflow, or REPLs:
- Strips REPL prompts (>>> and ...)
- Strips line number prefixes (e.g. `1 | `, `1: `, `[1] `)
- Normalizes tabs to spaces
- Fixes uneven base indentation
"""

from __future__ import annotations

import re

# REPL prompts like `>>> ` or `... `
_REPL_PROMPT_RE = re.compile(r"^(\s*)(?:>>>|\.\.\.)(?:\s|$)(.*)$")

# Line number prefixes like `12 | `, `1: `, `[1] `
_LINE_NUM_RE = re.compile(r"^(\s*)(?:\d+\s*[|:]|\[\d+\])[ \t]?(.*)$")


def clean_pasted_code(text: str) -> str:
    """Cleans up pasted Python code snippets, stripping prompts and line numbers."""
    if not text or not text.strip():
        return text

    lines = text.splitlines()
    cleaned_lines: list[str] = []

    # 1. Check if all non-empty lines have REPL prompts
    non_empty = [line for line in lines if line.strip()]
    has_repl = non_empty and any(_REPL_PROMPT_RE.match(line) for line in non_empty)
    has_line_nums = non_empty and any(_LINE_NUM_RE.match(line) for line in non_empty)

    for line in lines:
        curr = line

        # Strip REPL prompts if present
        if has_repl:
            m = _REPL_PROMPT_RE.match(curr)
            if m:
                indent, code = m.group(1), m.group(2)
                curr = indent + code
            elif curr.strip() in (">>>", "..."):
                curr = ""

        # Strip line numbers if present
        if has_line_nums:
            m = _LINE_NUM_RE.match(curr)
            if m:
                indent, code = m.group(1), m.group(2)
                curr = indent + code

        # Replace tabs with 4 spaces
        curr = curr.replace("\t", "    ")
        cleaned_lines.append(curr)

    # 2. Dedent common indentation if whole block is indented
    non_empty_cleaned = [line for line in cleaned_lines if line.strip()]
    if non_empty_cleaned:
        min_indent = min(len(line) - len(line.lstrip(" ")) for line in non_empty_cleaned)
        if min_indent > 0:
            cleaned_lines = [
                line[min_indent:] if line.strip() else "" for line in cleaned_lines
            ]

    return "\n".join(cleaned_lines)
