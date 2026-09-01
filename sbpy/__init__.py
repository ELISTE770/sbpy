"""SBpy - Gemini בתוך פייתון, אבל רק כשבאמת צריך.

    import sbpy
    sbpy.install()          # כל שגיאה עוברת קודם תיקון מקומי, ורק אז ל-Gemini
    sbpy.SFB("app.py")      # @SFB = Search For Bugs

עקרון העבודה הוא סולם הסלמה: מטמון -> תיקון מקומי -> ניתוח סטטי -> Gemini.
רוב השגיאות היומיומיות (טעות כתיב, import חסר, מפתח לא קיים) נעצרות
בשלב המקומי ולא עולות אגורה.
"""

from __future__ import annotations

from typing import Any

from . import budget, index, knowledge, learn, pricing, static
from .cache import Cache
from .config import Config, configure, get_config, reset_config
from .gemini import get_engine, sdk_available
from .hooks import explain, install, is_installed, smart, uninstall, watch
from .ladder import diagnose, diagnose_text
from .patcher import Patch, build_from_findings, build_from_report, build_from_scan
from .render import render_compact, render_report, render_scan
from .results import Diagnosis, Finding, Report, ScanResult
from .shortcuts import (
    SHORTCUTS,
    Directive,
    ShortcutCallable,
    build_callables,
    list_shortcuts,
    scan_directives,
)
from .shortcuts import run as run_shortcut
from .suggestions import execute_option, get_options

__version__ = "0.1.0"

# יצירת הקיצורים כפונקציות ברמת המודול: sbpy.SFB, sbpy.SEC, ...
_CALLABLES = build_callables()
globals().update(_CALLABLES)


def shortcut(code: str, target: Any = None, **kwargs: Any) -> ScanResult:
    """הרצת קיצור לפי קוד: ``sbpy.shortcut("SFB", "app.py")``."""
    callable_ = _CALLABLES.get(code.upper().lstrip("@"))
    if callable_ is None:
        raise KeyError(f"קיצור לא מוכר: @{code}")
    return callable_(target, **kwargs)


def ask(question: str, target: Any = None, **kwargs: Any) -> ScanResult:
    """שאלה חופשית על קוד: ``sbpy.ask('למה זה איטי?', my_func)``."""
    return _CALLABLES["ASK"](target, question=question, **kwargs)


def reset_state() -> None:
    """מנקה את כל המטמונים שבזיכרון: אינדקס, כללים שנלמדו, מחירון, מנוע.

    שימושי אחרי שינוי ``SBPY_HOME`` או תצורה, ובבדיקות.
    """
    from . import gemini as _gemini
    from . import index as _index
    from . import knowledge as _knowledge
    from . import learn as _learn
    from . import pricing as _pricing

    _index.reset()
    _learn.reset_memory()
    _pricing._cache = None
    _knowledge._extra_loaded = False
    _gemini.reset_engine()
    budget.reset_run()


def status() -> dict[str, Any]:
    """מצב נוכחי: תצורה, זמינות Gemini, ותקציב."""
    config = get_config()
    return {
        "version": __version__,
        "installed": is_installed(),
        "language": config.language,
        "offline": config.offline,
        "gemini": get_engine(config).status(),
        "models": {
            "auto": config.model_auto,
            "command": config.model_command,
            "pro": config.model_pro,
        },
        "threshold": config.escalate_threshold,
        "budget": budget.summary(config),
        "cache": Cache(config).stats(),
        "knowledge": knowledge.describe(config),
        "learned": learn.stats(config),
        "shortcuts": [code for code, _, _ in list_shortcuts()],
    }


def apply_report(report: Report, *, backup: bool = True) -> list[str]:
    """מחיל את התיקון האוטומטי של דוח שגיאה. מחזיר את הקבצים ששונו."""
    return build_from_report(report).apply(backup=backup)


def apply_scan(result: ScanResult, *, backup: bool = True) -> list[str]:
    """מחיל את התיקונים של סריקת קיצור. מחזיר את הקבצים ששונו."""
    return build_from_scan(result).apply(backup=backup)


def heal(cmd: str | None = None, max_iterations: int = 3, **kwargs: Any) -> Any:
    """מריץ מערכת ריפוי עצמי של בדיקות."""
    from .agent import run_self_healing_tests

    return run_self_healing_tests(test_cmd=cmd, max_iterations=max_iterations, **kwargs)


def agent(goal: str, **kwargs: Any) -> Any:
    """מריץ סוכן אוטונומי למשימות תכנות."""
    from .agent import run_autonomous_agent

    return run_autonomous_agent(goal=goal, **kwargs)


def find(query: str, **kwargs: Any) -> Any:
    """מבצע חיפוש סמנטי בקוד הפרויקט."""
    from .search import semantic_code_search

    return semantic_code_search(query, **kwargs)


def gen(prompt: str, **kwargs: Any) -> Any:
    """מייצר ארכיטקטורה וקוד לפי תיאור שפה טבעית."""
    from .scaffold import generate_scaffold

    return generate_scaffold(prompt, **kwargs)


__all__ = [
    "__version__",
    "Patch",
    "apply_report",
    "apply_scan",
    "build_from_findings",
    "build_from_report",
    "build_from_scan",
    "index",
    "knowledge",
    "learn",
    "pricing",
    "reset_state",
    "Cache",
    "Config",
    "Diagnosis",
    "Directive",
    "Finding",
    "Report",
    "ScanResult",
    "ShortcutCallable",
    "SHORTCUTS",
    "ask",
    "budget",
    "configure",
    "diagnose",
    "diagnose_text",
    "explain",
    "get_config",
    "get_engine",
    "install",
    "is_installed",
    "list_shortcuts",
    "render_compact",
    "render_report",
    "render_scan",
    "reset_config",
    "run_shortcut",
    "scan_directives",
    "sdk_available",
    "shortcut",
    "smart",
    "static",
    "status",
    "heal",
    "agent",
    "find",
    "gen",
    "uninstall",
    "watch",
    *sorted(_CALLABLES),
]
