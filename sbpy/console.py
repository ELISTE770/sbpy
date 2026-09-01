"""פלט טרמינל צבעוני, ללא תלויות חיצוניות."""

from __future__ import annotations

import os
import sys
from typing import TextIO

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ITALIC = "\x1b[3m"

COLORS = {
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
    "grey": "\x1b[90m",
    "bright_red": "\x1b[91m",
    "bright_green": "\x1b[92m",
    "bright_yellow": "\x1b[93m",
    "bright_cyan": "\x1b[96m",
    "white": "\x1b[97m",
}

SEVERITY_COLOR = {
    "info": "cyan",
    "warn": "yellow",
    "error": "red",
    "critical": "bright_red",
}

SEVERITY_ICON = {
    "info": "i",
    "warn": "!",
    "error": "x",
    "critical": "X",
}

SOURCE_BADGE = {
    "local": ("local", "green"),
    "static": ("static", "green"),
    "cache": ("cache", "cyan"),
    "gemini": ("gemini", "magenta"),
    "none": ("-", "grey"),
}

_vt_enabled: bool | None = None


def _enable_windows_vt() -> bool:
    """מפעיל ANSI ב-Windows. מחזיר True אם הצליח."""
    global _vt_enabled
    if _vt_enabled is not None:
        return _vt_enabled
    if os.name != "nt":
        _vt_enabled = True
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # 7 = STD_OUTPUT_HANDLE (-11) ; ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            _vt_enabled = False
            return False
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        _vt_enabled = True
    except Exception:  # pragma: no cover - סביבות חריגות
        _vt_enabled = False
    return _vt_enabled


def supports_color(stream: TextIO | None = None) -> bool:
    stream = stream or sys.stderr
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.name == "nt":
        return _enable_windows_vt()
    return os.environ.get("TERM", "") not in ("", "dumb")


class Console:
    """מדפיס פשוט עם צבע אופציונלי."""

    def __init__(self, stream: TextIO | None = None, color: bool | None = None) -> None:
        self.stream = stream if stream is not None else sys.stderr
        # color=False מכבה תמיד; color=True רק *מרשה*, והזיהוי האוטומטי עדיין מכריע.
        detected = supports_color(self.stream)
        self._color = detected if color is None else (bool(color) and detected)
        if self._color:
            _enable_windows_vt()

    # ------------------------------------------------------------------
    @property
    def color(self) -> bool:
        return self._color

    def paint(self, text: str, color: str = "", *, bold: bool = False, dim: bool = False) -> str:
        if not self._color:
            return text
        prefix = ""
        if bold:
            prefix += BOLD
        if dim:
            prefix += DIM
        prefix += COLORS.get(color, "")
        return f"{prefix}{text}{RESET}" if prefix else text

    def write(self, text: str = "") -> None:
        try:
            self.stream.write(text + "\n")
            self.stream.flush()
        except UnicodeEncodeError:
            # קונסולת Windows ישנה לא יודעת עברית - מוטב פלט חלקי מקריסה
            encoding = getattr(self.stream, "encoding", None) or "ascii"
            safe = (text + "\n").encode(encoding, "replace").decode(encoding, "replace")
            try:
                self.stream.write(safe)
                self.stream.flush()
            except (ValueError, OSError):  # pragma: no cover  # sbpy: ignore=silent-except
                pass
        except (ValueError, OSError):  # pragma: no cover - stream סגור  # sbpy: ignore=silent-except
            pass

    # ------------------------------------------------------------------
    def rule(self, title: str = "", color: str = "grey", width: int = 62) -> None:
        if not title:
            self.write(self.paint("-" * width, color, dim=True))
            return
        pad = max(0, width - len(title) - 3)
        line = f"-- {title} " + "-" * pad
        self.write(self.paint(line, color, dim=True))

    def badge(self, label: str, color: str) -> str:
        return self.paint(f"[{label}]", color, bold=True)

    def bullet(self, text: str, color: str = "", icon: str = "*") -> None:
        self.write(f"  {self.paint(icon, color, bold=True)} {text}")

    def kv(self, key: str, value: str, color: str = "grey") -> None:
        self.write(f"  {self.paint(key + ':', color)} {value}")

    def code(self, text: str, indent: str = "    ") -> None:
        for line in text.splitlines():
            self.write(indent + self.paint(line, "bright_cyan"))

    def snippet(self, lines: list[tuple[int, str]], mark_line: int | None = None) -> None:
        """מדפיס קטע קוד עם מספרי שורות, ומדגיש את שורת השגיאה."""
        for number, text in lines:
            marker = ">>" if number == mark_line else "  "
            num = f"{number:>4}"
            if number == mark_line:
                self.write(
                    f"  {self.paint(marker, 'red', bold=True)} "
                    f"{self.paint(num, 'red')} {self.paint('|', 'grey')} "
                    f"{self.paint(text, 'white', bold=True)}"
                )
            else:
                self.write(
                    f"  {marker} {self.paint(num, 'grey')} "
                    f"{self.paint('|', 'grey')} {self.paint(text, 'grey')}"
                )


_console_cache: dict[object, Console] = {}


def get_console(color: bool | None = None) -> Console:
    console = _console_cache.get(color)
    if console is None or console.stream is not sys.stderr:
        console = Console(color=color)
        _console_cache[color] = console
    return console
