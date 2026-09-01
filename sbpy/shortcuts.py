"""קיצורי הדרך החכמים: /SFB, /SEC, /OPT ...

לכל קיצור יש שתי שכבות: מעבר מקומי (AST) שרץ תמיד, והסלמה ל-Gemini
שרצה רק כשהמעבר המקומי לא הספיק - או כשמבקשים ``deep=True`` במפורש.
"""

from __future__ import annotations

import ast
import inspect
import io
import os
import sys
import tokenize
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable

from . import budget
from .cache import Cache, fingerprint
from .config import TIER_COMMAND, TIER_PRO, Config, get_config
from .gemini import get_engine
from .prompts import (
    FINDINGS_SCHEMA,
    SYSTEM_EXPLAIN,
    SYSTEM_REVIEW,
    SYSTEM_WRITE,
    explain_prompt,
    numbered,
    review_prompt,
    write_prompt,
)
from .redact import redact
from .results import Finding, ScanResult
from .static.checks import (
    CATEGORY_BUG,
    CATEGORY_COMPLEXITY,
    CATEGORY_DOC,
    CATEGORY_OPT,
    CATEGORY_SEC,
    CATEGORY_STYLE,
    CATEGORY_TODO,
    CATEGORY_TYPE,
    CATEGORY_MOD,
    SourceUnit,
    analyze,
)

MODE_REVIEW = "review"
MODE_WRITE = "write"
MODE_EXPLAIN = "explain"

ESCALATE_AUTO = "auto"
ESCALATE_ALWAYS = "always"
ESCALATE_NEVER = "never"


@dataclass(frozen=True)
class Shortcut:
    """הגדרה של קיצור-דרך אחד."""

    code: str
    title_he: str
    title_en: str
    categories: tuple[str, ...] = ()
    mode: str = MODE_REVIEW
    escalate: str = ESCALATE_AUTO
    tier: str = TIER_COMMAND
    focus: str = ""
    instruction: str = ""
    takes_question: bool = False

    project_wide: bool = False
    """The analysis covers the whole project, not one file.

    Such a shortcut must run **once** per root. Running it per file would
    repeat the same global findings once for every file scanned.
    """

    def title(self, lang: str = "he") -> str:
        return self.title_he if lang == "he" else self.title_en


SHORTCUTS: dict[str, Shortcut] = {}


def register(shortcut: Shortcut) -> Shortcut:
    SHORTCUTS[shortcut.code.upper()] = shortcut
    return shortcut


ESCALATION_LABEL = {
    "he": {
        ESCALATE_NEVER: "אף פעם",
        ESCALATE_AUTO: "רק אם המקומי לא מצא",
        ESCALATE_ALWAYS: "תמיד",
    },
    "en": {
        ESCALATE_NEVER: "never",
        ESCALATE_AUTO: "only if the local pass found nothing",
        ESCALATE_ALWAYS: "always",
    },
}


def markdown_table(lang: str = "he") -> str:
    """The shortcut table, generated from the registry.

    The README embeds this between markers, and a test fails when the two
    drift apart - so the documentation cannot quietly fall behind the code.
    """
    header = (
        "| קיצור | מה זה עושה | שכבה מקומית | פונה ל-Gemini |\n|---|---|---|---|"
        if lang == "he"
        else "| Shortcut | What it does | Local pass | Calls Gemini |\n|---|---|---|---|"
    )
    labels = ESCALATION_LABEL.get(lang, ESCALATION_LABEL["en"])
    rows = [header]
    for code in sorted(SHORTCUTS):
        shortcut = SHORTCUTS[code]
        if shortcut.project_wide:
            local = "כל הפרויקט" if lang == "he" else "whole project"
        elif shortcut.categories:
            local = ", ".join(shortcut.categories)
        else:
            local = "—"
        escalation = labels.get(shortcut.escalate, shortcut.escalate)
        rows.append(f"| `/{code}` | {shortcut.title(lang)} | {local} | {escalation} |")
    return "\n".join(rows)


# ----------------------------------------------------------------------
register(
    Shortcut(
        code="SFB",
        title_he="חיפוש באגים",
        title_en="Search For Bugs",
        categories=(CATEGORY_BUG, CATEGORY_STYLE),
        mode=MODE_REVIEW,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Logical bugs, edge cases, and invalid input assumptions",
    )
)
register(
    Shortcut(
        code="SEC",
        title_he="סריקת אבטחה",
        title_en="Security scan",
        categories=(CATEGORY_SEC,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Security holes: injections, unvalidated input, secrets, permissions",
    )
)
register(
    Shortcut(
        code="OPT",
        title_he="שיפור ביצועים",
        title_en="Optimize",
        categories=(CATEGORY_OPT,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Unnecessary complexity, redundant calculations, and expensive loop operations",
    )
)
register(
    Shortcut(
        code="CMP",
        title_he="מדד מורכבות",
        title_en="Complexity report",
        categories=(CATEGORY_COMPLEXITY,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        focus="Cyclomatic complexity and nesting depth",
    )
)
register(
    Shortcut(
        code="TODO",
        title_he="רשימת משימות בקוד",
        title_en="TODO inventory",
        categories=(CATEGORY_TODO,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        focus="TODO / FIXME tags left in the code",
    )
)
register(
    Shortcut(
        code="DOC",
        title_he="כתיבת תיעוד",
        title_en="Docstrings",
        categories=(CATEGORY_DOC,),
        mode=MODE_WRITE,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        instruction="כתוב docstring קצר לכל פונקציה ציבורית שחסר לה אחד. החזר רק את הפונקציות ששונו.",
    )
)
register(
    Shortcut(
        code="TYP",
        title_he="הוספת רמזי טיפוס",
        title_en="Type hints",
        categories=(CATEGORY_TYPE,),
        mode=MODE_WRITE,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        instruction="הוסף type hints מדויקים. החזר רק את החתימות ששונו.",
    )
)
register(
    Shortcut(
        code="MOD",
        title_he="שדרוג לתחביר פייתון מודרני",
        title_en="Modernize Python syntax",
        categories=(CATEGORY_MOD,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        focus="Modern syntax: pathlib, type annotations, match-case",
    )
)
register(
    Shortcut(
        code="DEAD",
        project_wide=True,
        title_he="איתור קוד מת",
        title_en="Dead code detection",
        categories=(CATEGORY_STYLE,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        focus="Detect functions, classes, and variables that are never used in the project",
    )
)
register(
    Shortcut(
        code="ARCH",
        project_wide=True,
        title_he="אכיפת ארכיטקטורה ומעגלי ייבוא",
        title_en="Architecture & circular imports",
        categories=(CATEGORY_BUG, CATEGORY_STYLE),
        mode=MODE_REVIEW,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        focus="Detect circular dependencies and architectural layer violations",
    )
)
register(
    Shortcut(
        code="CLONE",
        project_wide=True,
        title_he="איתור קוד משוכפל",
        title_en="Code clone detection",
        categories=(CATEGORY_STYLE,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_NEVER,
        tier=TIER_COMMAND,
        focus="Detect nearly identical functions and blocks for unification (DRY)",
    )
)
register(
    Shortcut(
        code="TAINT",
        title_he="ניתוח זרימת מידע ואבטחה",
        title_en="Taint data-flow analysis",
        categories=(CATEGORY_SEC,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Track unsanitized input flowing to dangerous sinks (SQL, shell commands)",
    )
)
register(
    Shortcut(
        code="DEBUG",
        title_he="הוספת לוגים והדפסות דיבאג",
        title_en="Inject debug logs",
        categories=(CATEGORY_BUG,),
        mode=MODE_WRITE,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Inject detailed logging commands to monitor variable values and function entry",
    )
)
register(
    Shortcut(
        code="SQL",
        title_he="בדיקת שאילתות SQL ואבטחה",
        title_en="SQL Query Analysis",
        categories=(CATEGORY_SEC, CATEGORY_OPT),
        mode=MODE_REVIEW,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Detect SQL Injection, missing indexes, and improve query performance",
    )
)
register(
    Shortcut(
        code="API",
        title_he="יצירת Endpoints (FastAPI / Flask)",
        title_en="Generate API Endpoints",
        categories=(CATEGORY_STYLE,),
        mode=MODE_WRITE,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Build secure API endpoints including Pydantic-based validation",
    )
)
register(
    Shortcut(
        code="REVIEW",
        title_he="סקירת קוד מלאה",
        title_en="Full Code Review",
        categories=(CATEGORY_BUG, CATEGORY_SEC, CATEGORY_OPT, CATEGORY_STYLE),
        mode=MODE_REVIEW,
        escalate=ESCALATE_ALWAYS,
        tier=TIER_PRO,
        focus="In-depth code review including readability, maintainability, logic bugs, and security",
    )
)
register(
    Shortcut(
        code="SOLID",
        title_he="אכיפת עקרונות SOLID",
        title_en="SOLID Principles Check",
        categories=(CATEGORY_STYLE,),
        mode=MODE_REVIEW,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Check adherence to SOLID principles in classes and interfaces",
    )
)
register(
    Shortcut(
        code="ASYNC",
        title_he="המרה לקוד אסינכרוני",
        title_en="Convert to Async",
        categories=(CATEGORY_OPT,),
        mode=MODE_WRITE,
        escalate=ESCALATE_AUTO,
        tier=TIER_PRO,
        focus="Convert synchronous functions to asyncio-based code (with async/await)",
    )
)
register(
    Shortcut(
        code="CLEAN",
        title_he="ניקוי קוד (Cleanup)",
        title_en="Code Cleanup",
        categories=(CATEGORY_STYLE,),
        mode=MODE_WRITE,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Remove unnecessary comments, unused imports, temporary prints, and dead code",
    )
)
register(
    Shortcut(
        code="MOCK",
        title_he="יצירת Mocks לטסטים",
        title_en="Generate Test Mocks",
        categories=(CATEGORY_BUG,),
        mode=MODE_WRITE,
        escalate=ESCALATE_AUTO,
        tier=TIER_COMMAND,
        focus="Generate accurate mock objects for unit tests using unittest.mock or pytest-mock",
    )
)
register(
    Shortcut(
        code="EXP",
        title_he="הסבר קוד",
        title_en="Explain",
        mode=MODE_EXPLAIN,
        escalate=ESCALATE_ALWAYS,
        tier=TIER_COMMAND,
    )
)
register(
    Shortcut(
        code="TST",
        title_he="כתיבת בדיקות",
        title_en="Write tests",
        mode=MODE_WRITE,
        escalate=ESCALATE_ALWAYS,
        tier=TIER_COMMAND,
        instruction="כתוב בדיקות pytest ממוקדות, כולל מקרי קצה. בלי mock מיותר.",
    )
)
register(
    Shortcut(
        code="REF",
        title_he="הצעת ריפקטור",
        title_en="Refactor",
        mode=MODE_WRITE,
        escalate=ESCALATE_ALWAYS,
        tier=TIER_COMMAND,
        instruction="שכתב את הקוד כך שיהיה קריא יותר בלי לשנות התנהגות. הסבר בשורה אחת מה שינית.",
    )
)
register(
    Shortcut(
        code="NAM",
        title_he="שיפור שמות",
        title_en="Naming",
        mode=MODE_EXPLAIN,
        escalate=ESCALATE_ALWAYS,
        tier=TIER_COMMAND,
        instruction="הצע שמות טובים יותר למשתנים ולפונקציות. טבלה קצרה: שם נוכחי -> שם מוצע -> למה.",
    )
)
register(
    Shortcut(
        code="ASK",
        title_he="שאלה חופשית",
        title_en="Ask",
        mode=MODE_EXPLAIN,
        escalate=ESCALATE_ALWAYS,
        tier=TIER_COMMAND,
        takes_question=True,
    )
)


# ----------------------------------------------------------------------
@dataclass
class Target:
    """מקור הקוד שעליו פועל הקיצור."""

    source: str
    filename: str = "<code>"
    label: str = "<code>"
    start_line: int = 1


def _caller_file(depth: int = 3) -> str:
    frame = sys._getframe(depth)
    while frame is not None:
        filename = frame.f_code.co_filename
        if not filename.startswith("<") and "sbpy" not in os.path.normcase(filename):
            return filename
        frame = frame.f_back
    return ""


def resolve_target(target: Any = None, *, depth: int = 4) -> Target:
    """הופך פונקציה / מודול / נתיב / מחרוזת קוד ל-``Target``."""
    if target is None:
        path = _caller_file(depth)
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return Target(handle.read(), path, os.path.basename(path))
        raise ValueError("לא הצלחתי לזהות את הקובץ הקורא. העבר נתיב או פונקציה במפורש.")

    if isinstance(target, str):
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8", errors="replace") as handle:
                return Target(handle.read(), target, os.path.basename(target))
        if os.path.isdir(target):
            # Project-wide shortcuts (@DEAD / @ARCH / @CLONE) take a root,
            # not a single file. They read the tree themselves.
            label = os.path.basename(os.path.abspath(target)) or target
            return Target("", target, label)
        if "\n" in target or target.strip().startswith(("def ", "class ", "import ", "from ")):
            return Target(target, "<code>", "<code>")
        raise FileNotFoundError(f"לא נמצא קובץ: {target}")

    if isinstance(target, ModuleType):
        path = getattr(target, "__file__", "") or ""
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return Target(handle.read(), path, target.__name__)
        raise ValueError(f"אין קוד מקור למודול {target!r}")

    try:
        source, start = inspect.getsourcelines(target)
    except (OSError, TypeError) as exc:
        raise ValueError(f"אין קוד מקור עבור {target!r}") from exc

    filename = ""
    try:
        filename = inspect.getsourcefile(target) or ""
    except TypeError:
        filename = ""
    name = getattr(target, "__qualname__", getattr(target, "__name__", "<object>"))
    return Target("".join(source), filename or "<code>", str(name), max(1, start))


# ----------------------------------------------------------------------
def _dedent_for_parse(source: str) -> str:
    """פונקציה שנחתכה מתוך מחלקה מגיעה עם הזחה - צריך להסיר אותה כדי ל-parse."""
    lines = source.splitlines()
    if not lines:
        return source
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    shift = min(indents) if indents else 0
    if not shift:
        return source
    return "\n".join(line[shift:] if len(line) >= shift else line for line in lines)


def _local_pass(target: Target, shortcut: Shortcut) -> list[Finding]:
    if shortcut.code == "DEAD":
        from .graph import find_dead_code

        root = target.filename if os.path.isdir(target.filename) else (os.path.dirname(os.path.abspath(target.filename)) or ".")
        return find_dead_code(root)
    if shortcut.code == "ARCH":
        from .arch import scan_architecture

        root = target.filename if os.path.isdir(target.filename) else (os.path.dirname(os.path.abspath(target.filename)) or ".")
        return scan_architecture(root)
    if shortcut.code == "CLONE":
        from .clones import scan_clones

        root = target.filename if os.path.isdir(target.filename) else (os.path.dirname(os.path.abspath(target.filename)) or ".")
        return scan_clones(root)

    if not shortcut.categories:
        return []

    # A whole, unchanged file can be answered from the scan cache. A slice
    # (one function pulled out of a module) never can - it is not the file.
    whole_file = target.start_line == 1 and os.path.isfile(target.filename)
    if whole_file:
        from .scancache import cached_analyze

        findings = cached_analyze(target.filename, shortcut.categories)
        if shortcut.code == "TAINT":
            from .taint import scan_taint

            unit = SourceUnit.from_source(target.source, target.filename)
            if unit.tree is not None:
                findings = list(findings) + scan_taint(unit)
        return findings

    unit = SourceUnit.from_source(_dedent_for_parse(target.source), target.filename)
    if unit.tree is None:
        return []
    findings = analyze(unit, shortcut.categories)
    if shortcut.code == "TAINT":
        from .taint import scan_taint

        findings.extend(scan_taint(unit))
    if target.start_line > 1:
        for finding in findings:
            finding.line += target.start_line - 1
    return findings


def _findings_from_payload(payload: dict[str, Any], target: Target, source_tag: str) -> list[Finding]:
    rows = payload.get("findings")
    if not isinstance(rows, list):
        return []
    out: list[Finding] = []
    lines = target.source.splitlines()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            line = int(row.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        severity = str(row.get("severity") or "warn")
        if severity not in {"info", "warn", "error", "critical"}:
            severity = "warn"
        index = line - target.start_line
        snippet = lines[index].strip() if 0 <= index < len(lines) else ""
        try:
            confidence = float(row.get("confidence") or 0.7)
        except (TypeError, ValueError):
            confidence = 0.7
        out.append(
            Finding(
                rule="gemini",
                message=str(row.get("title") or "").strip() or "-",
                line=line,
                severity=severity,  # type: ignore[arg-type]
                file=target.filename,
                hint=str(row.get("fix") or "").strip(),
                snippet=snippet or str(row.get("why") or "").strip(),
                source=source_tag,  # type: ignore[arg-type]
                confidence=max(0.0, min(1.0, confidence)),
            )
        )
    return out


def _should_escalate(shortcut: Shortcut, local: list[Finding], deep: bool) -> tuple[bool, str]:
    if deep:
        return True, "deep"
    if shortcut.escalate == ESCALATE_ALWAYS:
        return True, "always"
    if shortcut.escalate == ESCALATE_NEVER:
        return False, ""
    if not local:
        return True, "no-local-findings"
    return False, ""


def run(
    code: str,
    target: Any = None,
    *,
    question: str = "",
    deep: bool = False,
    pro: bool = False,
    local_only: bool = False,
    config: Config | None = None,
    _depth: int = 5,
) -> ScanResult:
    """מריץ קיצור-דרך יחיד ומחזיר ``ScanResult``."""
    config = config or get_config()
    key = code.upper().lstrip("/")
    shortcut = SHORTCUTS.get(key)
    if shortcut is None:
        raise KeyError(f"קיצור לא מוכר: /{key}. ראה sbpy.list_shortcuts()")

    resolved = resolve_target(target, depth=_depth)
    result = ScanResult(shortcut=key, target=resolved.label)

    local = _local_pass(resolved, shortcut)
    result.findings.extend(local)

    escalate, reason = _should_escalate(shortcut, local, deep)
    if local_only:
        # מצב באטץ': המעבר המקומי בלבד, ההסלמה תיעשה במרוכז מאוחר יותר
        result.escalation_reason = reason if escalate else ""
        return result
    if not escalate:
        return result

    allowed, blocked_reason = budget.check(f"/{key}", config)
    if not allowed:
        budget.note_blocked()
        result.notes.append(f"Gemini לא נקרא: {blocked_reason}")
        return result

    payload_source = redact(resolved.source) if config.redact else resolved.source
    if len(payload_source) > config.max_context_chars:
        payload_source = payload_source[: config.max_context_chars] + "\n# ...[נחתך]"

    # הדרגה נכנסת למפתח המטמון: תשובה של pro לא תוגש כתשובה של flash.
    tier = TIER_PRO if pro else shortcut.tier

    cache = Cache(config)
    cache_key = fingerprint(key, payload_source, question, shortcut.mode, tier)
    cached = cache.get(cache_key)
    if cached:
        result.escalated = True
        result.escalation_reason = "cache"
        result.text = str(cached.get("text") or "")
        result.findings.extend(_findings_from_payload(cached, resolved, "cache"))
        budget.record(
            f"/{key}", str(cached.get("model", "")), 0, tier=tier, cached=True, config=config
        )
        return result

    known = "; ".join(f"{f.line}: {f.rule}" for f in local[:12])

    if shortcut.mode == MODE_REVIEW:
        prompt = review_prompt(
            code=numbered(payload_source, resolved.start_line),
            filename=resolved.label,
            focus=shortcut.focus or shortcut.title(config.language),
            known=known,
            lang=config.language,
        )
        system, schema = SYSTEM_REVIEW, FINDINGS_SCHEMA
    elif shortcut.mode == MODE_WRITE:
        prompt = write_prompt(
            task=shortcut.instruction,
            code=payload_source,
            filename=resolved.label,
            lang=config.language,
        )
        system, schema = SYSTEM_WRITE, None
    else:
        prompt = explain_prompt(
            code=payload_source,
            question=question or shortcut.instruction,
            lang=config.language,
        )
        system, schema = SYSTEM_EXPLAIN, None

    engine = get_engine(config)
    response = engine.generate(prompt, system=system, schema=schema, tier=tier)
    budget.record(
        f"/{key}", response.model, response.tokens, tier=response.tier, ok=response.ok, config=config
    )

    result.escalated = True
    result.escalation_reason = reason
    result.tokens = response.tokens
    if response.downgraded_from:
        result.notes.append(
            f"{response.downgraded_from} לא היה זמין - ירדנו ל-{response.model}"
        )

    if not response.ok:
        result.notes.append(f"Gemini נכשל: {response.error}")
        return result

    if schema is not None:
        payload = response.data or {}
        result.findings.extend(_findings_from_payload(payload, resolved, "gemini"))
        payload = dict(payload)
    else:
        result.text = response.text.strip()
        payload = {"text": result.text}

    payload["model"] = response.model
    cache.set(cache_key, payload)
    return result


# ----------------------------------------------------------------------
class ShortcutCallable:
    """``sbpy.SFB(target)`` להרצה, ``/sbpy.SFB.on`` כדקורטור."""

    def __init__(self, shortcut: Shortcut) -> None:
        self.shortcut = shortcut
        self.__name__ = shortcut.code
        self.__doc__ = f"{shortcut.title('he')} / {shortcut.title('en')} (/{shortcut.code})"

    def __call__(
        self,
        target: Any = None,
        *,
        question: str = "",
        deep: bool = False,
        pro: bool = False,
        show: bool = True,
        config: Config | None = None,
    ) -> ScanResult:
        result = run(
            self.shortcut.code,
            target,
            question=question,
            deep=deep,
            pro=pro,
            config=config,
            _depth=4,
        )
        if show:
            from .render import render_scan

            render_scan(result, config=config)
        return result

    def on(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """דקורטור: סורק את הפונקציה בזמן ההגדרה ומחזיר אותה כמו שהיא."""
        try:
            self.__call__(func, show=True)
        except Exception:  # pragma: no cover - סריקה לא תשבור ייבוא  # sbpy: ignore=silent-except
            pass
        return func

    def __repr__(self) -> str:  # pragma: no cover
        return f"</{self.shortcut.code} {self.shortcut.title('en')}>"


def build_callables() -> dict[str, ShortcutCallable]:
    return {code: ShortcutCallable(shortcut) for code, shortcut in SHORTCUTS.items()}


# ----------------------------------------------------------------------
# הנחיות בתוך הקוד:  # /SFB
# ----------------------------------------------------------------------
@dataclass
class Directive:
    code: str
    line: int
    scope: str = "<module>"
    question: str = ""


def scan_directives(path: str) -> list[Directive]:
    """מוצא תגובות מסוג ``# /SFB`` בקובץ ומקשר אותן לפונקציה העוטפת."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            source = handle.read()
    except OSError:
        return []

    found: list[Directive] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            text = token.string.lstrip("#").strip()
            if not text.startswith("/"):
                continue
            head, _, rest = text[1:].partition(" ")
            code = head.strip().upper()
            if code in SHORTCUTS:
                found.append(Directive(code=code, line=token.start[0], question=rest.strip()))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return found

    # קישור להיקף (פונקציה/מחלקה) שמכיל את השורה
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return found

    scopes: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            scopes.append((node.lineno, end, node.name))
    for directive in found:
        best: tuple[int, int, str] | None = None
        for start, end, name in scopes:
            if start - 2 <= directive.line <= end:
                if best is None or (end - start) < (best[1] - best[0]):
                    best = (start, end, name)
        if best is not None:
            directive.scope = best[2]
    return found


def list_shortcuts(lang: str = "he") -> list[tuple[str, str, str]]:
    """(קוד, כותרת, מדיניות הסלמה) לכל הקיצורים."""
    rows = []
    for code, shortcut in sorted(SHORTCUTS.items()):
        rows.append((code, shortcut.title(lang), shortcut.escalate))
    return rows
