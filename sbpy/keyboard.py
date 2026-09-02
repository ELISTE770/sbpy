"""Keyboard layout transliteration (Hebrew QWERTY mapping) and interactive terminal arrow picker."""

from __future__ import annotations

import os
import sys
from typing import Any

HEBREW_TO_ENGLISH_MAP = {
    "/": "q",
    "'": "w",
    "ק": "e",
    "ר": "r",
    "א": "t",
    "ט": "y",
    "ו": "u",
    "ן": "i",
    "ם": "o",
    "פ": "p",
    "]": "[",
    "[": "]",
    "ש": "a",
    "ד": "s",
    "ג": "d",
    "כ": "f",
    "ע": "g",
    "י": "h",
    "ח": "j",
    "ל": "k",
    "ך": "l",
    "ף": ";",
    ",": "'",
    "ז": "z",
    "ס": "x",
    "ב": "c",
    "ה": "v",
    "נ": "b",
    "מ": "n",
    "צ": "m",
    "ת": ",",
    "ץ": ".",
    ".": "/",
}

CYRILLIC_TO_ENGLISH_MAP = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y", "г": "u", "ш": "i", "щ": "o", "з": "p", "х": "[", "ъ": "]",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h", "о": "j", "л": "k", "д": "l", "ж": ";", "э": "'",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n", "ь": "m", "б": ",", "ю": ".",
    "Й": "Q", "Ц": "W", "У": "E", "К": "R", "Е": "T", "Н": "Y", "Г": "U", "Ш": "I", "Щ": "O", "З": "P", "Х": "{", "Ъ": "}",
    "Ф": "A", "Ы": "S", "В": "D", "А": "F", "П": "G", "Р": "H", "О": "J", "Л": "K", "Д": "L", "Ж": ":", "Э": '"',
    "Я": "Z", "Ч": "X", "С": "C", "М": "V", "И": "B", "Т": "N", "Ь": "M", "Б": "<", "Ю": ">",
}

ARABIC_TO_ENGLISH_MAP = {
    "ض": "q", "ص": "w", "ث": "e", "ق": "r", "ف": "t", "غ": "y", "ع": "u", "ه": "i", "خ": "o", "ح": "p", "ج": "[", "د": "]",
    "ش": "a", "س": "s", "ي": "d", "ب": "f", "ل": "g", "ا": "h", "ت": "j", "ن": "k", "م": "l", "ك": ";", "ط": "'",
    "ئ": "z", "ء": "x", "ؤ": "c", "ر": "v", "لا": "b", "ى": "n", "ة": "m", "و": ",", "ز": ".", "ظ": "/",
}

GREEK_TO_ENGLISH_MAP = {
    ";": "q", "ς": "w", "ε": "e", "ρ": "r", "τ": "t", "υ": "y", "θ": "u", "ι": "i", "ο": "o", "π": "p",
    "α": "a", "σ": "s", "δ": "d", "φ": "f", "γ": "g", "η": "h", "ξ": "j", "κ": "k", "λ": "l",
    "ζ": "z", "χ": "x", "ψ": "c", "ω": "v", "β": "b", "ν": "n", "μ": "m",
}

HEBREW_SEMANTIC_MAP = {
    "הדפס": "print",
    "הדפסה": "print",
    "החזר": "return",
    "החזרה": "return",
    "אם": "if",
    "אחרת": "else",
    "עבור": "for",
    "לכל": "for",
    "כל_עוד": "while",
    "בעוד": "while",
    "הגדר": "def",
    "פונקציה": "def",
    "מחלקה": "class",
    "נכון": "True",
    "אמת": "True",
    "לא_נכון": "False",
    "שקר": "False",
    "כלום": "None",
    "ריק": "None",
    "ייבא": "import",
    "נסה": "try",
    "תפוס": "except",
    "אורך": "len",
    "טווח": "range",
    "קלט": "input",
}


def is_hebrew_text(text: str) -> bool:
    """Checks if text contains Hebrew characters."""
    return any("\u0590" <= ch <= "\u05ff" for ch in text)


def is_cyrillic_text(text: str) -> bool:
    """Checks if text contains Cyrillic characters."""
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


def is_arabic_text(text: str) -> bool:
    """Checks if text contains Arabic characters."""
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def is_greek_text(text: str) -> bool:
    """Checks if text contains Greek characters."""
    return any("\u0370" <= ch <= "\u03ff" for ch in text)


def detect_foreign_script(text: str) -> str:
    """Detects which non-English script is present."""
    if is_hebrew_text(text):
        return "hebrew"
    if is_cyrillic_text(text):
        return "cyrillic"
    if is_arabic_text(text):
        return "arabic"
    if is_greek_text(text):
        return "greek"
    return ""


def transliterate_keyboard(text: str) -> str:
    """Translates text typed in foreign keyboard layout back to English QWERTY."""
    script = detect_foreign_script(text)
    mapping = HEBREW_TO_ENGLISH_MAP
    if script == "cyrillic":
        mapping = CYRILLIC_TO_ENGLISH_MAP
    elif script == "arabic":
        mapping = ARABIC_TO_ENGLISH_MAP
    elif script == "greek":
        mapping = GREEK_TO_ENGLISH_MAP

    result: list[str] = []
    for ch in text:
        result.append(mapping.get(ch, ch))
    return "".join(result)


def transliterate_line(line: str) -> str:
    """Translates an entire line of code from foreign keyboard or semantic pseudo-code to valid Python."""
    if not line.strip():
        return line

    # 1. Semantic keyword substitutions (e.g. הדפס("שלום") -> print("שלום"))
    import re
    res_line = line
    for heb_kw, py_kw in HEBREW_SEMANTIC_MAP.items():
        pattern = r"(?<!\w)" + re.escape(heb_kw) + r"(?!\w)"
        res_line = re.sub(pattern, py_kw, res_line)

    # 2. Physical keyboard transliteration if non-ASCII remaining
    if detect_foreign_script(res_line):
        res_line = transliterate_keyboard(res_line)

    return res_line


def normalize_input_command(line: str) -> str:
    """Normalizes commands, translating accidental foreign layout typing to English."""
    raw = line.strip()
    if not raw:
        return line

    head, sep, rest = raw.partition(" ")

    # Normalize only the command/head part
    if head.startswith(".") and is_hebrew_text(head):
        norm_head = "/" + transliterate_keyboard(head[1:])
    elif head.startswith("/") and is_hebrew_text(head):
        norm_head = "/" + transliterate_keyboard(head[1:].replace("/", "q"))
    elif is_hebrew_text(head):
        norm_head = transliterate_keyboard(head)
    else:
        norm_head = head

    # Handle common phonetic/typing substitutions like וי -> ui
    if norm_head.lower() == "/uh":
        norm_head = "/ui"
    elif norm_head.lower() == "uh":
        norm_head = "ui"

    return f"{norm_head}{sep}{rest}" if sep else norm_head


def read_single_keypress() -> str:
    """Reads a single keypress cross-platform with arrow keys support."""
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            sub = msvcrt.getch()
            if sub == b"H":
                return "UP"
            if sub == b"P":
                return "DOWN"
            if sub == b"K":
                return "LEFT"
            if sub == b"M":
                return "RIGHT"
            return "SPECIAL"
        if ch in (b"\r", b"\n"):
            return "ENTER"
        if ch == b"\x1b":
            return "ESC"
        if ch == b"\x08":
            return "BACKSPACE"
        if ch == b"\t":
            return "TAB"
        try:
            return ch.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    return "UP"
                if seq == "[B":
                    return "DOWN"
                if seq == "[C":
                    return "RIGHT"
                if seq == "[D":
                    return "LEFT"
                return "ESC"
            if ch in ("\r", "\n"):
                return "ENTER"
            if ch == "\t":
                return "TAB"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return "ENTER"


def run_interactive_arrow_picker(
    items: list[tuple[str, str, str]],
    title: str = "SBpy Interactive Command Picker",
    console: Any = None,
) -> tuple[str, str] | None:
    """Runs interactive arrow-key selector. Returns (code, desc) or None if cancelled."""
    if not items:
        return None

    if not getattr(sys.stdin, "isatty", lambda: False)():
        return None

    current_idx = 0
    total = len(items)

    def render_menu() -> None:
        paint = console.paint if console else lambda t, *_, **__: t
        output_lines: list[str] = []
        output_lines.append("\n")
        output_lines.append(paint(f"  ┌── 🛠️ {title} (Use ↑/↓ Arrows & Enter) ──────────┐\n", "cyan", bold=True))

        for i, (idx_str, code, desc) in enumerate(items):
            act_str = f"({desc})"
            if len(act_str) > 42:
                act_str = act_str[:39] + "...)"

            if i == current_idx:
                pointer = paint("►", "bright_green", bold=True)
                idx_badge = paint(f"[{idx_str:>2}]", "bright_yellow", bold=True)
                cmd_badge = paint(f"/{code:<8}", "bright_green", bold=True)
                desc_text = paint(f"{act_str:<44}", "white", bold=True)
                output_lines.append(f"  │ {pointer} {idx_badge} {cmd_badge} {desc_text} │\n")
            else:
                pointer = " "
                idx_badge = paint(f"[{idx_str:>2}]", "grey")
                cmd_badge = paint(f"/{code:<8}", "bright_cyan")
                desc_text = paint(f"{act_str:<44}", "grey")
                output_lines.append(f"  │ {pointer} {idx_badge} {cmd_badge} {desc_text} │\n")

        output_lines.append(paint("  └────────────────────────────────────────────────────────────────────────┘\n", "cyan", bold=True))
        output_lines.append(paint("  ⌨️  [↑/↓ Arrows]: Navigate · [Enter]: Select · [1-9]: Direct Jump · [ESC/q]: Exit\n\n", "grey", dim=True))

        sys.stdout.write("\033[2J\033[H")
        sys.stdout.write("".join(output_lines))
        sys.stdout.flush()

    num_buffer = ""
    while True:
        render_menu()
        key = read_single_keypress()

        if key == "UP":
            current_idx = (current_idx - 1) % total
            num_buffer = ""
        elif key == "DOWN":
            current_idx = (current_idx + 1) % total
            num_buffer = ""
        elif key == "ENTER":
            return (items[current_idx][1], items[current_idx][2])
        elif key in ("ESC", "q", "Q"):
            return None
        elif key.isdigit():
            num_buffer += key
            val = int(num_buffer)
            if 1 <= val <= total:
                current_idx = val - 1
            if val * 10 > total:
                num_buffer = ""
