"""חיבור SBpy לזרימת השגיאות של פייתון.

שלוש דרכים לצרוך את זה:
    sbpy.install()          - כל שגיאה לא מטופלת בתוכנית עוברת אבחון
    @sbpy.smart             - עוטף פונקציה אחת, ויכול גם לתקן ולהריץ מחדש
    with sbpy.watch():      - בלוק ממוקד
"""

from __future__ import annotations

import functools
import sys
import threading
from types import TracebackType
from typing import Any, Callable

from .config import Config, configure, get_config
from .i18n import t
from .ladder import diagnose
from .render import render_report
from .results import Report

_original_excepthook: Callable[..., Any] | None = None
_original_threadhook: Callable[..., Any] | None = None
_installed = False
_ipython_registered = False

_last_error: BaseException | None = None
_last_report: Report | None = None

# תיקונים שמותר להריץ מחדש אוטומטית - רק כאלה שהם דטרמיניסטיים ובטוחים
RETRYABLE_KINDS = {"kwarg_typo"}


def _safe_report(exc: BaseException, tb: TracebackType | None, config: Config) -> Report | None:
    global _last_error, _last_report
    _last_error = exc
    try:
        report = diagnose(exc, tb, config=config)
    except Exception:  # pragma: no cover - אבחון לעולם לא מפיל את התוכנית
        return None
    _last_report = report
    return report


def last_error() -> BaseException | None:
    """החריגה האחרונה ש-SBpy ראה. שימושי במיוחד ב-`sbpy shell`."""
    return _last_error


def last_report() -> Report | None:
    """הדוח האחרון שנוצר."""
    return _last_report


def _handle(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    config = get_config()
    if not config.enabled:
        return
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        return
    report = _safe_report(exc, tb, config)
    if report is not None:
        try:
            render_report(report, config=config)
        except Exception:  # pragma: no cover  # sbpy: ignore=silent-except
            pass


def _excepthook(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
    if _original_excepthook is not None:
        _original_excepthook(exc_type, exc, tb)
    _handle(exc_type, exc, tb)


def _threadhook(args) -> None:  # type: ignore[no-untyped-def]
    if _original_threadhook is not None:
        _original_threadhook(args)
    if args.exc_type is not None:
        _handle(args.exc_type, args.exc_value, args.exc_traceback)


def _install_ipython() -> bool:
    """אם רצים ב-IPython/Jupyter, מתחברים דרך set_custom_exc."""
    global _ipython_registered
    try:
        shell = get_ipython()  # type: ignore[name-defined]  # noqa: F821
    except NameError:
        return False
    if shell is None:
        return False

    def handler(shell_self, exc_type, exc, tb, tb_offset=None):  # type: ignore[no-untyped-def]
        shell_self.showtraceback((exc_type, exc, tb), tb_offset=tb_offset)
        _handle(exc_type, exc, tb)
        return None

    try:
        shell.set_custom_exc((BaseException,), handler)
    except Exception:  # pragma: no cover
        return False
    _ipython_registered = True
    return True


def install(**overrides: Any) -> Config:
    """מפעיל את SBpy על כל שגיאה לא מטופלת. אפשר להעביר גם הגדרות."""
    global _original_excepthook, _original_threadhook, _installed

    config = configure(**overrides) if overrides else get_config()
    if _installed:
        return config

    if _install_ipython():
        _installed = True
        return config

    _original_excepthook = sys.excepthook
    sys.excepthook = _excepthook
    _original_threadhook = threading.excepthook
    threading.excepthook = _threadhook  # type: ignore[assignment]
    _installed = True
    return config


def uninstall() -> None:
    """מחזיר את פייתון להתנהגות המקורית."""
    global _original_excepthook, _original_threadhook, _installed
    if not _installed:
        return
    if _original_excepthook is not None:
        sys.excepthook = _original_excepthook
        _original_excepthook = None
    if _original_threadhook is not None:
        threading.excepthook = _original_threadhook  # type: ignore[assignment]
        _original_threadhook = None
    _installed = False


def is_installed() -> bool:
    return _installed


# ----------------------------------------------------------------------
def _auto_retry(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    report: Report,
    config: Config,
    show: bool = True,
) -> tuple[bool, Any]:
    """מנסה תיקון בטוח והרצה חוזרת. מחזיר (הצליח, תוצאה)."""
    best = report.best
    if best is None or best.source != "local":
        return False, None
    kind = str(best.meta.get("kind", ""))
    if kind not in RETRYABLE_KINDS:
        return False, None

    bad, good = best.meta.get("bad"), best.meta.get("good")
    if not bad or not good or bad not in kwargs or good in kwargs:
        return False, None

    patched = dict(kwargs)
    patched[str(good)] = patched.pop(str(bad))
    try:
        value = func(*args, **patched)
    except Exception:
        return False, None

    if show:
        from .console import get_console

        console = get_console(config.color)
        console.write(
            console.paint(
                t("ui.retry.success", config.language, what=f"{bad} -> {good}"),
                "green",
                bold=True,
            )
        )
    return True, value


def smart(
    func: Callable[..., Any] | None = None,
    *,
    retry: bool | None = None,
    show: bool = True,
    reraise: bool = True,
    default: Any = None,
) -> Any:
    """דקורטור שמאבחן שגיאות בפונקציה, ואם אפשר גם מתקן ומריץ מחדש.

    ``@smart`` או ``@smart(retry=True, reraise=False, default=[])``.
    """

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return target(*args, **kwargs)
            except Exception as exc:
                config = get_config()
                if not config.enabled:
                    raise
                report = _safe_report(exc, exc.__traceback__, config)
                if report is not None:
                    allow_retry = config.auto_retry if retry is None else retry
                    if allow_retry:
                        fixed, value = _auto_retry(target, args, kwargs, report, config, show)
                        if fixed:
                            return value
                    if show:
                        try:
                            render_report(report, config=config)
                        except Exception:  # pragma: no cover  # sbpy: ignore=silent-except
                            pass
                if reraise:
                    raise
                return default

        wrapper.sbpy_smart = True  # type: ignore[attr-defined]
        return wrapper

    if func is not None:
        return decorate(func)
    return decorate


class watch:
    """מנהל הקשר: מאבחן כל שגיאה שנזרקת בתוך הבלוק.

        with sbpy.watch(reraise=False):
            risky()
    """

    def __init__(self, *, show: bool = True, reraise: bool = True) -> None:
        self.show = show
        self.reraise = reraise
        self.report: Report | None = None

    def __enter__(self) -> "watch":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        if exc is None:
            return False
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            return False
        config = get_config()
        if not config.enabled:
            return not self.reraise
        self.report = _safe_report(exc, tb, config)
        if self.report is not None and self.show:
            try:
                render_report(self.report, config=config)
            except Exception:  # pragma: no cover  # sbpy: ignore=silent-except
                pass
        return not self.reraise


def explain(exc: BaseException | None = None, *, show: bool = True) -> Report:
    """אבחון ידני של חריגה (ברירת מחדל: האחרונה שנתפסה)."""
    if exc is None:
        exc = sys.exc_info()[1]
    if exc is None:
        raise ValueError("אין חריגה פעילה לאבחון. העבר אחת במפורש.")
    config = get_config()
    report = diagnose(exc, exc.__traceback__, config=config)
    if show:
        render_report(report, config=config)
    return report
