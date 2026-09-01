"""Side-by-Side Visual Diff Viewer for SBpy in terminal."""

from __future__ import annotations

import difflib
import os
import shutil
from typing import Any

from .console import get_console


def _truncate_pad(text: str, width: int) -> str:
    if len(text) > width:
        return text[: width - 1] + "…"
    return text.ljust(width)


def render_side_by_side(
    path: str,
    original: list[str],
    updated: list[str],
    width: int | None = None,
    console: Any = None,
) -> None:
    """Renders a 2-column side-by-side diff in the terminal."""
    console = console or get_console()
    total_width = width or shutil.get_terminal_size((100, 24)).columns
    total_width = max(80, min(total_width, 140))

    col_width = (total_width - 9) // 2
    filename = os.path.basename(path)

    console.write()
    console.write(console.paint(f"  ┌── Side-by-Side Diff: {filename} " + ("─" * max(0, total_width - len(filename) - 28)) + "┐", "cyan", bold=True))
    header_orig = _truncate_pad(" ORIGINAL", col_width)
    header_mod = _truncate_pad(" PROPOSED FIX", col_width)
    console.write(console.paint(f"  │ {header_orig} │ {header_mod} │", "grey", bold=True))
    console.write(console.paint(f"  ├──" + ("─" * col_width) + "─┼─" + ("─" * col_width) + "──┤", "cyan"))

    matcher = difflib.SequenceMatcher(None, original, updated)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Show up to 2 context lines before and after if long
            orig_slice = original[i1:i2]
            mod_slice = updated[j1:j2]
            count = len(orig_slice)
            if count > 4:
                # show first 2
                for k in range(2):
                    l_num = str(i1 + k + 1).rjust(3)
                    r_num = str(j1 + k + 1).rjust(3)
                    l_text = _truncate_pad(f"{l_num} | {orig_slice[k]}", col_width)
                    r_text = _truncate_pad(f"{r_num} | {mod_slice[k]}", col_width)
                    console.write(f"  │ {console.paint(l_text, 'grey')} │ {console.paint(r_text, 'grey')} │")
                console.write(f"  │ {console.paint(_truncate_pad(f'    ... ({count - 4} unchanged lines) ...', col_width), 'grey', dim=True)} │ {console.paint(_truncate_pad('', col_width), 'grey')} │")
                # show last 2
                for k in range(count - 2, count):
                    l_num = str(i1 + k + 1).rjust(3)
                    r_num = str(j1 + k + 1).rjust(3)
                    l_text = _truncate_pad(f"{l_num} | {orig_slice[k]}", col_width)
                    r_text = _truncate_pad(f"{r_num} | {mod_slice[k]}", col_width)
                    console.write(f"  │ {console.paint(l_text, 'grey')} │ {console.paint(r_text, 'grey')} │")
            else:
                for k in range(count):
                    l_num = str(i1 + k + 1).rjust(3)
                    r_num = str(j1 + k + 1).rjust(3)
                    l_text = _truncate_pad(f"{l_num} | {orig_slice[k]}", col_width)
                    r_text = _truncate_pad(f"{r_num} | {mod_slice[k]}", col_width)
                    console.write(f"  │ {console.paint(l_text, 'grey')} │ {console.paint(r_text, 'grey')} │")

        elif tag == "replace":
            lines_count = max(i2 - i1, j2 - j1)
            for k in range(lines_count):
                if i1 + k < i2:
                    l_num = str(i1 + k + 1).rjust(3)
                    l_text = _truncate_pad(f"{l_num} - {original[i1 + k]}", col_width)
                    l_styled = console.paint(l_text, "red", bold=True)
                else:
                    l_styled = console.paint(_truncate_pad("", col_width), "grey")

                if j1 + k < j2:
                    r_num = str(j1 + k + 1).rjust(3)
                    r_text = _truncate_pad(f"{r_num} + {updated[j1 + k]}", col_width)
                    r_styled = console.paint(r_text, "green", bold=True)
                else:
                    r_styled = console.paint(_truncate_pad("", col_width), "grey")

                console.write(f"  │ {l_styled} │ {r_styled} │")

        elif tag == "delete":
            for k in range(i1, i2):
                l_num = str(k + 1).rjust(3)
                l_text = _truncate_pad(f"{l_num} - {original[k]}", col_width)
                l_styled = console.paint(l_text, "red", bold=True)
                r_styled = console.paint(_truncate_pad("", col_width), "grey")
                console.write(f"  │ {l_styled} │ {r_styled} │")

        elif tag == "insert":
            for k in range(j1, j2):
                l_styled = console.paint(_truncate_pad("", col_width), "grey")
                r_num = str(k + 1).rjust(3)
                r_text = _truncate_pad(f"{r_num} + {updated[k]}", col_width)
                r_styled = console.paint(r_text, "green", bold=True)
                console.write(f"  │ {l_styled} │ {r_styled} │")

    console.write(console.paint("  └─" + ("─" * col_width) + "─┴─" + ("─" * col_width) + "──┘", "cyan", bold=True))
    console.write()
