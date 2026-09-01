"""מעקב עמוק ושחזור צעדים בזמן אמת (Crash Snapshot & Time-Travel Tracing).

מתעד את ערכי המשתנים וציר הזמן של שורות הקוד שרצו ממש לפני שגיאה,
ומפיק תמונת מצב מפורטת (Crash Dump) לניתוח מהיר של שורש הבעיה.
"""

from __future__ import annotations

import collections
import json
import linecache
import os
import sys
import types
from dataclasses import dataclass, field
from typing import Any


def _safe_repr(val: Any, max_len: int = 60) -> str:
    """ייצוג בטוח של ערך משתנה ללא תופעות לוואי."""
    try:
        r = repr(val)
        if len(r) > max_len:
            return r[: max_len - 3] + "..."
        return r
    except Exception:
        return "<unprintable>"


@dataclass
class FrameSnapshot:
    file: str
    line: int
    func_name: str
    code: str
    locals: dict[str, str] = field(default_factory=dict)


@dataclass
class CrashSnapshot:
    exc_type: str
    exc_value: str
    timeline: list[FrameSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exc_type": self.exc_type,
            "exc_value": self.exc_value,
            "timeline": [
                {
                    "file": s.file,
                    "line": s.line,
                    "func_name": s.func_name,
                    "code": s.code,
                    "locals": s.locals,
                }
                for s in self.timeline
            ],
        }

    def save_json(self, path: str = "crash_dump.json") -> str:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
        return os.path.abspath(path)


class CrashTracer:
    """עוקב קל משקל אחר ציר הזמן של שורות הקוד שרצות."""

    def __init__(self, history_size: int = 15) -> None:
        self.history_size = history_size
        self.history: collections.deque[FrameSnapshot] = collections.deque(maxlen=history_size)
        self._orig_trace: Any = None

    def trace_fn(self, frame: types.FrameType, event: str, arg: Any) -> Any:
        if event == "line":
            filename = frame.f_code.co_filename
            base = os.path.basename(filename)
            if "<" not in filename and "site-packages" not in filename and "Lib" not in filename and base != "trace.py":
                line_no = frame.f_lineno
                func = frame.f_code.co_name
                code_line = linecache.getline(filename, line_no).strip()
                local_vars = {k: _safe_repr(v) for k, v in frame.f_locals.items() if not k.startswith("__")}
                self.history.append(
                    FrameSnapshot(
                        file=filename,
                        line=line_no,
                        func_name=func,
                        code=code_line,
                        locals=local_vars,
                    )
                )
        return self.trace_fn

    def __enter__(self) -> "CrashTracer":
        self._orig_trace = sys.gettrace()
        sys.settrace(self.trace_fn)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        sys.settrace(self._orig_trace)

    def capture_snapshot(self, exc: BaseException) -> CrashSnapshot:
        return CrashSnapshot(
            exc_type=type(exc).__name__,
            exc_value=str(exc),
            timeline=list(self.history),
        )


_LAST_SNAPSHOT: CrashSnapshot | None = None


def get_latest_crash_snapshot() -> CrashSnapshot | None:
    """מחזיר את ה-CrashSnapshot האחרון שנלכד."""
    global _LAST_SNAPSHOT
    return _LAST_SNAPSHOT


def set_latest_crash_snapshot(snapshot: CrashSnapshot | None) -> None:
    """מעדכן את ה-CrashSnapshot האחרון."""
    global _LAST_SNAPSHOT
    _LAST_SNAPSHOT = snapshot


def run_with_trace(script_path: str, script_args: list[str] | None = None) -> tuple[int, CrashSnapshot | None]:
    """מריץ סקריפט עם מעקב צעדים חי. מחזיר קוד יציאה ואת ה-CrashSnapshot במקרה של שגיאה."""
    import runpy

    tracer = CrashTracer()
    sys.argv = [script_path, *(script_args or [])]
    directory = os.path.dirname(os.path.abspath(script_path))
    if directory not in sys.path:
        sys.path.insert(0, directory)

    try:
        with tracer:
            runpy.run_path(script_path, run_name="__main__")
        set_latest_crash_snapshot(None)
        return 0, None
    except SystemExit as exc:
        set_latest_crash_snapshot(None)
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1), None
    except BaseException as exc:
        snapshot = tracer.capture_snapshot(exc)
        set_latest_crash_snapshot(snapshot)
        return 1, snapshot
