"""מעקב אחרי שינויים בקבצים - ``sbpy dev``.

בלי תלויות: סקירת ``mtime`` בלולאה. בפרויקט טיפוסי זה זול בהרבה מהסריקה
עצמה, ולא דורש להתקין watchdog.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

DEFAULT_INTERVAL = 0.7

SKIP_DIRECTORIES = {
    "__pycache__", ".git", ".hg", ".svn", ".venv", "venv", "env",
    "node_modules", ".mypy_cache", ".pytest_cache", ".tox", "build", "dist",
    ".idea", ".vscode", "site-packages",
}


def _snapshot(paths: Iterable[str], suffix: str = ".py") -> dict[str, float]:
    found: dict[str, float] = {}
    for path in paths:
        if os.path.isfile(path):
            try:
                found[os.path.abspath(path)] = os.path.getmtime(path)
            except OSError:
                continue
            continue
        for directory, subdirectories, filenames in os.walk(path):
            subdirectories[:] = [
                name
                for name in subdirectories
                if name not in SKIP_DIRECTORIES and not name.startswith(".")
            ]
            for filename in filenames:
                if not filename.endswith(suffix):
                    continue
                full = os.path.join(directory, filename)
                try:
                    found[os.path.abspath(full)] = os.path.getmtime(full)
                except OSError:
                    continue
    return found


@dataclass
class Change:
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.added or self.modified or self.removed)

    def touched(self) -> list[str]:
        return sorted(set(self.added + self.modified))


def diff_snapshots(before: dict[str, float], after: dict[str, float]) -> Change:
    change = Change()
    for path, mtime in after.items():
        if path not in before:
            change.added.append(path)
        elif abs(before[path] - mtime) > 1e-6:
            change.modified.append(path)
    for path in before:
        if path not in after:
            change.removed.append(path)
    return change


def watch(
    paths: Iterable[str],
    on_change: Callable[[Change], None],
    *,
    interval: float = DEFAULT_INTERVAL,
    run_immediately: bool = True,
    max_iterations: int | None = None,
) -> int:
    """לולאת מעקב. חוזרת כשמפסיקים עם Ctrl+C. מחזירה כמה סבבים רצו.

    ``max_iterations`` קיים לבדיקות - בשימוש רגיל משאירים None.
    """
    paths = [os.path.abspath(path) for path in paths]
    previous = _snapshot(paths)
    iterations = 0

    if run_immediately:
        on_change(Change(added=sorted(previous)))

    try:
        while max_iterations is None or iterations < max_iterations:
            time.sleep(interval)
            iterations += 1
            current = _snapshot(paths)
            change = diff_snapshots(previous, current)
            previous = current
            if change:
                on_change(change)
    except KeyboardInterrupt:  # sbpy: ignore=silent-except
        pass
    return iterations
