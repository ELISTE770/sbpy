"""הסלמה מרוכזת - N פריטים בקריאה אחת במקום N קריאות.

בסריקה של 20 קבצים, המצב הישן היה 20 קריאות ל-Gemini. כאן זו קריאה אחת
(או שתיים). זה החיסכון הגדול ביותר בכל הפרויקט, והוא גם מהיר יותר.

הכל עדיין עובר את סולם ההסלמה: לבאטץ' נכנסים רק פריטים שהשכבות
המקומיות לא הצליחו לפתור.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from . import budget
from .cache import Cache, fingerprint
from .config import TIER_AUTO, TIER_COMMAND, Config, get_config
from .gemini import get_engine
from .prompts import (
    BATCH_DIAGNOSIS_SCHEMA,
    BATCH_FINDINGS_SCHEMA,
    SYSTEM_DIAGNOSE,
    SYSTEM_REVIEW,
    batch_diagnose_prompt,
    batch_review_prompt,
    numbered,
)
from .redact import redact
from .results import Diagnosis, Finding, Report

MAX_ITEMS_PER_CALL = 8
MAX_FILES_PER_CALL = 6


@dataclass
class BatchOutcome:
    """מה יצא מקריאה מרוכזת אחת."""

    calls: int = 0
    tokens: int = 0
    answered: int = 0
    skipped_reason: str = ""
    notes: list[str] = field(default_factory=list)


def _chunks(items: Sequence[Any], size: int) -> list[list[Any]]:
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def _apply_answer(
    answer: dict[str, Any],
    report: Report,
    response: Any,
    cache: Cache,
    answer_count: int,
) -> bool:
    """Attaches one batched answer to its report. Returns whether it landed."""
    title = str(answer.get("title") or "").strip()
    if not title:
        return False

    diagnosis = Diagnosis(
        title=title,
        detail=str(answer.get("cause") or "").strip(),
        suggestion=str(answer.get("fix") or "").strip(),
        confidence=_as_confidence(answer.get("confidence"), 0.6),
        source="gemini",
        rule="gemini.batch",
        meta={"model": response.model, "batch": True},
    )
    report.add(diagnosis)
    report.escalated = True
    report.escalation_reason = "batch"
    report.tokens = response.tokens // max(1, answer_count)

    cache.set(
        report.fingerprint,
        {
            "title": diagnosis.title,
            "cause": diagnosis.detail,
            "fix": diagnosis.suggestion,
            "confidence": diagnosis.confidence,
            "model": response.model,
        },
    )
    return True


# ======================================================================
# שגיאות
# ======================================================================
def diagnose_many(
    reports: Sequence[Report],
    *,
    config: Config | None = None,
    tier: str = TIER_AUTO,
) -> BatchOutcome:
    """משלים דוחות שלא נפתרו מקומית - בקריאה אחת לכל קבוצה.

    מעדכן את הדוחות במקום (מוסיף ``Diagnosis`` בעל ``source="gemini"``).
    """
    config = config or get_config()
    outcome = BatchOutcome()

    pending = [
        report
        for report in reports
        if report.top_confidence < config.escalate_threshold and not report.escalated
    ]
    if not pending:
        outcome.skipped_reason = "nothing-to-escalate"
        return outcome

    engine = get_engine(config)
    cache = Cache(config)

    for group in _chunks(pending, MAX_ITEMS_PER_CALL):
        allowed, reason = budget.check("batch-diagnose", config)
        if not allowed:
            budget.note_blocked()
            outcome.skipped_reason = reason
            break
        _diagnose_group(group, engine, cache, config, tier, outcome)

    return outcome


def _diagnose_items(group: Sequence[Report], config: Config) -> list[dict[str, Any]]:
    """The payload for one batched call - redacted, numbered, minimal."""
    items: list[dict[str, Any]] = []
    for index, report in enumerate(group, start=1):
        code = "\n".join(text for _, text in report.snippet_lines)
        items.append(
            {
                "index": index,
                "exc_type": report.exc_type,
                "message": redact(report.exc_message) if config.redact else report.exc_message,
                "where": report.where,
                "code": redact(code) if config.redact else code,
            }
        )
    return items


def _diagnose_group(
    group: Sequence[Report],
    engine: Any,
    cache: Cache,
    config: Config,
    tier: str,
    outcome: BatchOutcome,
) -> None:
    """One call covering one group of unresolved errors."""
    prompt = batch_diagnose_prompt(_diagnose_items(group, config), config.language)
    response = engine.generate(
        prompt, system=SYSTEM_DIAGNOSE, schema=BATCH_DIAGNOSIS_SCHEMA, tier=tier
    )
    outcome.calls += 1
    outcome.tokens += response.tokens
    budget.record(
        "batch-diagnose",
        response.model,
        response.tokens,
        tier=response.tier,
        ok=response.ok,
        config=config,
    )

    if not response.ok:
        outcome.notes.append(f"Gemini נכשל: {response.error}")
        return

    answers = (response.data or {}).get("answers")
    if not isinstance(answers, list):
        outcome.notes.append("תשובה לא בפורמט הצפוי")
        return

    for answer in answers:
        if not isinstance(answer, dict):
            continue
        index = _as_int(answer.get("index"))
        if not (1 <= index <= len(group)):
            continue
        if _apply_answer(answer, group[index - 1], response, cache, len(answers)):
            outcome.answered += 1


# ======================================================================
# סקירת קבצים
# ======================================================================
def review_many(
    code: str,
    targets: Sequence[tuple[str, str]],
    *,
    focus: str,
    config: Config | None = None,
    tier: str = TIER_COMMAND,
) -> tuple[list[Finding], BatchOutcome]:
    """סוקר כמה קבצים בקריאה אחת. ``targets`` הם זוגות (שם, קוד)."""
    config = config or get_config()
    outcome = BatchOutcome()
    findings: list[Finding] = []
    if not targets:
        outcome.skipped_reason = "no-targets"
        return findings, outcome

    engine = get_engine(config)
    cache = Cache(config)
    by_name = {name: source for name, source in targets}

    for group in _chunks(list(targets), MAX_FILES_PER_CALL):
        payload = [
            {
                "name": name,
                "code": numbered(redact(source) if config.redact else source),
            }
            for name, source in group
        ]
        cache_key = fingerprint("batch", code, tier, *(f"{n}:{len(s)}" for n, s in group))
        cached = cache.get(cache_key)
        if cached:
            findings.extend(_findings_from_batch(cached, by_name, "cache"))
            budget.record(f"batch@{code}", str(cached.get("model", "")), 0, tier=tier, cached=True, config=config)
            continue

        allowed, reason = budget.check(f"batch@{code}", config)
        if not allowed:
            budget.note_blocked()
            outcome.skipped_reason = reason
            break

        prompt = batch_review_prompt(payload, focus, config.language)
        response = engine.generate(
            prompt, system=SYSTEM_REVIEW, schema=BATCH_FINDINGS_SCHEMA, tier=tier
        )
        outcome.calls += 1
        outcome.tokens += response.tokens
        budget.record(
            f"batch@{code}", response.model, response.tokens, tier=response.tier,
            ok=response.ok, config=config,
        )

        if not response.ok:
            outcome.notes.append(f"Gemini נכשל: {response.error}")
            continue

        data = dict(response.data or {})
        data["model"] = response.model
        cache.set(cache_key, data)
        found = _findings_from_batch(data, by_name, "gemini")
        findings.extend(found)
        outcome.answered += len(found)

    return findings, outcome


VALID_SEVERITIES = {"info", "warn", "error", "critical"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_confidence(value: Any, default: float = 0.7) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _match_file(name: str, sources: dict[str, str]) -> str:
    """Maps the file the model named onto one we actually sent.

    Models sometimes answer with a full path where we gave a basename.
    """
    name = name.strip()
    if name in sources:
        return name
    for key in sources:
        if key.endswith(name) or name.endswith(key):
            return key
    return ""


def _finding_from_row(row: dict[str, Any], sources: dict[str, str], source_tag: str) -> Finding | None:
    name = _match_file(str(row.get("file") or ""), sources)
    if not name:
        return None

    line = _as_int(row.get("line"))
    severity = str(row.get("severity") or "warn")
    if severity not in VALID_SEVERITIES:
        severity = "warn"

    lines = sources[name].splitlines()
    snippet = lines[line - 1].strip() if 1 <= line <= len(lines) else ""
    return Finding(
        rule="gemini",
        message=str(row.get("title") or "").strip() or "-",
        line=line,
        severity=severity,  # type: ignore[arg-type]
        file=name,
        hint=str(row.get("fix") or "").strip(),
        snippet=snippet or str(row.get("why") or "").strip(),
        source=source_tag,  # type: ignore[arg-type]
        confidence=_as_confidence(row.get("confidence")),
    )


def _findings_from_batch(
    payload: dict[str, Any], sources: dict[str, str], source_tag: str
) -> list[Finding]:
    rows = payload.get("findings")
    if not isinstance(rows, list):
        return []
    found = (
        _finding_from_row(row, sources, source_tag) for row in rows if isinstance(row, dict)
    )
    return [finding for finding in found if finding is not None]
