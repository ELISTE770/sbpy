"""סולם ההסלמה - הליבה של SBpy.

    שכבה 1    תיקון מקומי    חינם   difflib · inspect · AST · אינדקס פרויקט
    שכבה 2.5  בסיס ידע       חינם   שגיאות פייתון נפוצות עם תשובה קבועה
    שכבה 2.6  כללים שנלמדו   חינם   מה ש-Gemini כבר ענה בעבר, מוכלל
    שכבה 0    מטמון          חינם   אותה שגיאה בדיוק
    שכבה 3    Gemini         כסף    רק אם כל השאר לא הספיק

הכלל היחיד שחשוב: לא פונים החוצה כל עוד אפשר לענות מקומית.
"""

from __future__ import annotations

import time
import traceback
from types import TracebackType

from . import budget, contextpack, knowledge, learn
from .cache import Cache, fingerprint
from .config import TIER_AUTO, TIER_COMMAND, Config, get_config
from .context import build_contexts
from .gemini import get_engine
from .i18n import t
from .local.fixers import ErrorInfo, run_fixers
from .prompts import DIAGNOSIS_SCHEMA, SYSTEM_DIAGNOSE, diagnose_prompt
from .redact import redact
from .results import Diagnosis, Report

MAX_TRACEBACK_LINES = 12


def _traceback_tail(exc: BaseException, limit: int = MAX_TRACEBACK_LINES) -> str:
    try:
        lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    except Exception:  # pragma: no cover
        return ""
    text = "".join(lines).splitlines()
    return "\n".join(text[-limit:])


def _code_window(info: ErrorInfo, radius: int) -> tuple[str, int]:
    """הקשר חכם: imports + הפונקציה העוטפת + הגדרות של השמות בשורה שנכשלה.

    זה מחליף חלון גולמי של ±N שורות, שלרוב מכיל שורות ריקות ולא מכיל
    את מה שבאמת נחוץ כדי לאבחן.
    """
    ctx = info.ctx
    if ctx is None:
        return "", 0
    pack = contextpack.build(ctx, radius=radius)
    text = pack.render()
    if text:
        return text, pack.failing_line
    window = ctx.source_window(radius)
    if not window:
        return ctx.line, ctx.lineno
    return "\n".join(line for _, line in window), window[0][0]


def _diagnosis_from_payload(payload: dict, source: str, model: str = "") -> Diagnosis | None:
    if not payload:
        return None
    title = str(payload.get("title") or "").strip()
    if not title:
        return None
    try:
        confidence = float(payload.get("confidence") or 0.6)
    except (TypeError, ValueError):
        confidence = 0.6
    return Diagnosis(
        title=title,
        detail=str(payload.get("cause") or "").strip(),
        suggestion=str(payload.get("fix") or "").strip(),
        patch=(str(payload.get("patch")).strip() or None) if payload.get("patch") else None,
        confidence=max(0.0, min(1.0, confidence)),
        source=source,  # type: ignore[arg-type]
        rule="gemini.diagnose",
        meta={"model": model or payload.get("model", "")},
    )


def diagnose(
    exc: BaseException,
    tb: TracebackType | None = None,
    *,
    config: Config | None = None,
    force_gemini: bool = False,
    tier: str = TIER_AUTO,
) -> Report:
    """מריץ את כל סולם ההסלמה על שגיאה אחת ומחזיר דוח."""
    config = config or get_config()
    started = time.perf_counter()
    tb = tb or exc.__traceback__

    deep, user = build_contexts(tb)
    info = ErrorInfo(
        exc=exc,
        exc_type=type(exc),
        tb=tb,
        deep=deep,
        user=user,
        lang=config.language,
        message=str(exc),
    )

    report = Report(
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        where=(info.ctx.where() if info.ctx else ""),
    )
    if info.ctx is not None:
        report.snippet_lines = info.ctx.source_window(3)
        report.snippet_mark = info.ctx.lineno
        report.file = info.ctx.filename

    # --- שכבה 1: תיקונים מקומיים ---
    for diagnosis in run_fixers(info):
        report.add(diagnosis)

    key_line = info.ctx.line if info.ctx else ""
    report.fingerprint = fingerprint(
        type(exc).__name__,
        str(exc),
        key_line,
        info.ctx.function if info.ctx else "",
    )

    if not force_gemini and report.top_confidence >= config.escalate_threshold:
        report.skipped_reason = "local-confident"
        report.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return report

    # --- שכבה 2.5: בסיס ידע מקומי ---
    if config.knowledge:
        entry = knowledge.lookup(report.exc_type, report.exc_message, config=config)
        if entry is not None:
            report.add(entry)
            if not force_gemini and report.top_confidence >= config.escalate_threshold:
                report.skipped_reason = "knowledge-base"
                report.elapsed_ms = int((time.perf_counter() - started) * 1000)
                return report

    # --- שכבה 2.6: כללים שנלמדו מתשובות קודמות ---
    if config.learning and not force_gemini:
        remembered = learn.lookup(report.exc_type, report.exc_message, config=config)
        if remembered is not None:
            report.add(remembered)
            if report.top_confidence >= config.escalate_threshold:
                report.skipped_reason = "learned"
                budget.record("diagnose", remembered.meta.get("model", ""), 0, cached=True, config=config)
                report.elapsed_ms = int((time.perf_counter() - started) * 1000)
                return report

    # --- שכבה 0: מטמון ---
    cache = Cache(config)
    cached = cache.get(report.fingerprint)
    if cached and not force_gemini:
        diagnosis = _diagnosis_from_payload(cached, "cache", str(cached.get("model", "")))
        if diagnosis is not None:
            report.add(diagnosis)
            report.skipped_reason = "cache-hit"
            budget.record("diagnose", str(cached.get("model", "")), 0, cached=True, config=config)
            report.elapsed_ms = int((time.perf_counter() - started) * 1000)
            return report

    # --- שכבה 3: Gemini ---
    allowed, reason = budget.check("diagnose", config)
    if not allowed:
        budget.note_blocked()
        report.skipped_reason = reason
        report.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return report

    code, _ = _code_window(info, config.context_lines)
    local_notes = "; ".join(d.title for d in report.sorted_diagnoses()[:2])

    prompt = diagnose_prompt(
        exc_type=type(exc).__name__,
        message=str(exc),
        where=report.where,
        code=redact(code) if config.redact else code,
        traceback_tail=redact(_traceback_tail(exc)) if config.redact else _traceback_tail(exc),
        local_notes=redact(local_notes) if config.redact else local_notes,
        lang=config.language,
    )
    if len(prompt) > config.max_context_chars:
        prompt = prompt[: config.max_context_chars] + "\n...[truncated]"

    engine = get_engine(config)
    result = engine.generate(
        prompt,
        system=SYSTEM_DIAGNOSE,
        schema=DIAGNOSIS_SCHEMA,
        tier=tier,
    )

    report.escalated = True
    report.escalation_reason = (
        "no-local-diagnosis" if not report.diagnoses else f"low-confidence {report.top_confidence:.2f}"
    )

    budget.record("diagnose", result.model, result.tokens, tier=result.tier, ok=result.ok, config=config)

    if not result.ok:
        report.skipped_reason = result.error or "gemini-failed"
        report.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return report

    report.tokens = result.tokens
    diagnosis = _diagnosis_from_payload(result.data or {}, "gemini", result.model)
    if diagnosis is not None:
        report.add(diagnosis)
        payload = dict(result.data or {})
        payload["model"] = result.model
        cache.set(report.fingerprint, payload)
        # מזקקים כלל מקומי, כדי שהשגיאה הזו לא תעלה כסף בפעם הבאה
        learn.learn_from(report, config=config)

    report.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return report


def diagnose_text(
    text: str,
    *,
    config: Config | None = None,
    code: str = "",
    tier: str = TIER_COMMAND,
) -> Report:
    """אבחון של הודעת שגיאה שהודבקה כטקסט (בלי traceback חי)."""
    config = config or get_config()
    started = time.perf_counter()

    report = Report(exc_type="pasted", exc_message=text.strip())
    report.fingerprint = fingerprint("pasted", text, code)

    cache = Cache(config)
    cached = cache.get(report.fingerprint)
    if cached:
        diagnosis = _diagnosis_from_payload(cached, "cache", str(cached.get("model", "")))
        if diagnosis is not None:
            report.add(diagnosis)
            report.skipped_reason = "cache-hit"
            budget.record("explain", str(cached.get("model", "")), 0, cached=True, config=config)
            report.elapsed_ms = int((time.perf_counter() - started) * 1000)
            return report

    allowed, reason = budget.check("explain", config)
    if not allowed:
        budget.note_blocked()
        report.skipped_reason = reason
        report.add(
            Diagnosis(
                title=t("ui.no_diagnosis", config.language),
                detail=t(f"ui.{'offline' if reason == 'offline' else 'no_key'}", config.language)
                if reason in {"offline", "no-api-key"}
                else reason,
                confidence=0.0,
                source="none",
                rule="ladder.blocked",
            )
        )
        return report

    prompt = diagnose_prompt(
        exc_type="",
        message=redact(text) if config.redact else text,
        where="",
        code=redact(code) if config.redact else code,
        lang=config.language,
    )
    engine = get_engine(config)
    result = engine.generate(
        prompt, system=SYSTEM_DIAGNOSE, schema=DIAGNOSIS_SCHEMA, tier=tier
    )
    report.escalated = True
    report.escalation_reason = "manual"
    budget.record("explain", result.model, result.tokens, tier=result.tier, ok=result.ok, config=config)

    if result.ok:
        report.tokens = result.tokens
        diagnosis = _diagnosis_from_payload(result.data or {}, "gemini", result.model)
        if diagnosis is not None:
            report.add(diagnosis)
            payload = dict(result.data or {})
            payload["model"] = result.model
            cache.set(report.fingerprint, payload)
    else:
        report.skipped_reason = result.error or "gemini-failed"

    report.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return report
