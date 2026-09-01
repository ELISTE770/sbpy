"""הצגת דוחות ותוצאות סריקה בטרמינל."""

from __future__ import annotations

import os

from .config import Config, get_config
from .console import Console, SEVERITY_COLOR, SEVERITY_ICON, SOURCE_BADGE, get_console
from .i18n import t
from .results import Diagnosis, Finding, Report, ScanResult

SEVERITY_ORDER = {"critical": 0, "error": 1, "warn": 2, "info": 3}


def _confidence_bar(value: float) -> str:
    return f"{int(round(value * 100)):>3}%"


def _footer_text(report: Report, lang: str) -> tuple[str, str]:
    """מחזיר (טקסט, צבע) לשורת הסיכום התחתונה."""
    if report.skipped_reason == "local-confident":
        return t("ui.local_only", lang), "green"
    if report.skipped_reason == "cache-hit":
        return t("ui.cache_hit", lang), "cyan"
    if report.escalated and report.diagnoses and report.best and report.best.source == "gemini":
        suffix = f" · {report.tokens} tokens" if report.tokens else ""
        return t("ui.escalated", lang, reason=report.escalation_reason) + suffix, "magenta"
    if report.skipped_reason == "offline":
        return t("ui.offline", lang), "grey"
    if report.skipped_reason == "no-api-key":
        return t("ui.no_key", lang), "grey"
    if report.skipped_reason == "no-sdk":
        return t("ui.no_sdk", lang), "grey"
    if report.skipped_reason:
        return report.skipped_reason, "grey"
    return "", "grey"


def render_diagnosis(diagnosis: Diagnosis, console: Console, lang: str) -> None:
    label, color = SOURCE_BADGE.get(diagnosis.source, ("?", "grey"))
    head = (
        f"  {console.badge(label, color)} "
        f"{console.paint(_confidence_bar(diagnosis.confidence), 'grey')} "
        f"{console.paint(diagnosis.title, 'white', bold=True)}"
    )
    console.write(head)
    if diagnosis.detail:
        console.write(f"      {console.paint(diagnosis.detail, 'grey')}")
    if diagnosis.suggestion:
        console.write(
            f"      {console.paint(t('ui.suggestion_label', lang) + ':', 'green', bold=True)} "
            f"{diagnosis.suggestion}"
        )
    if diagnosis.patch:
        console.write(f"      {console.paint(t('ui.patch_label', lang) + ':', 'cyan')}")
        console.code(diagnosis.patch, indent="        ")


def render_report(
    report: Report,
    *,
    config: Config | None = None,
    console: Console | None = None,
    show_snippet: bool = True,
    limit: int = 3,
) -> None:
    """מדפיס דוח אבחון מלא."""
    config = config or get_config()
    console = console or get_console(config.color)
    lang = config.language

    console.write()
    console.rule(t("ui.header", lang), "magenta")
    console.write(
        f"  {console.paint(report.exc_type, 'bright_red', bold=True)}: "
        f"{console.paint(report.exc_message, 'white')}"
    )
    if report.where:
        console.write(f"  {console.paint(report.where, 'grey')}")

    if show_snippet and report.snippet_lines:
        console.write()
        console.snippet(report.snippet_lines, report.snippet_mark)

    diagnoses = report.sorted_diagnoses()[:limit]
    if diagnoses:
        console.write()
        for i, diagnosis in enumerate(diagnoses, 1):
            render_diagnosis(diagnosis, console, lang)
    else:
        console.write()
        console.write(f"  {console.paint(t('ui.no_diagnosis', lang), 'grey')}")

    from .suggestions import register_options_from_report

    options = register_options_from_report(report)
    if options:
        console.write()
        console.write(f"  {console.paint('Quick Actions / Suggested Fixes:', 'cyan', bold=True)}")
        for opt in options:
            console.write(f"    {console.paint(f'[{opt.index}]', 'bright_yellow', bold=True)} {opt.title}")
        console.write(f"    {console.paint('💡 Type 1 or /1 to execute immediately', 'grey', dim=True)}")

    text, color = _footer_text(report, lang)
    if text:
        console.write()
        console.rule(text, color)
    console.write()


def render_finding(finding: Finding, console: Console, root: str = "") -> None:
    color = SEVERITY_COLOR.get(finding.severity, "yellow")
    icon = SEVERITY_ICON.get(finding.severity, "*")
    path = finding.file
    if root and path not in ("", "<code>"):
        try:
            relative = os.path.relpath(path, root)
            if not relative.startswith(".."):
                path = relative
        except ValueError:  # כוננים שונים ב-Windows  # sbpy: ignore=silent-except
            pass
    location = f"{path}:{finding.line}"
    console.write(
        f"  {console.paint(icon, color, bold=True)} "
        f"{console.paint(location, 'cyan')} "
        f"{console.paint(finding.rule, 'grey')}"
    )
    console.write(f"      {console.paint(finding.message, 'white')}")
    if finding.snippet:
        console.write(f"      {console.paint('| ' + finding.snippet, 'grey', dim=True)}")
    if finding.hint:
        console.write(f"      {console.paint('→ ' + finding.hint, 'green')}")


def render_scan(
    result: ScanResult,
    *,
    config: Config | None = None,
    console: Console | None = None,
    root: str = "",
    limit: int = 0,
) -> None:
    """מדפיס תוצאות של קיצור-דרך (@SFB וכו')."""
    config = config or get_config()
    console = console or get_console(config.color)
    lang = config.language

    title = f"SBpy @{result.shortcut} · {result.target}"
    console.write()
    console.rule(title, "cyan")

    if result.text:
        console.write()
        for line in result.text.splitlines():
            console.write(f"  {line}")

    findings = sorted(
        result.findings,
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.file, f.line),
    )
    if limit:
        findings = findings[:limit]

    if findings:
        console.write()
        for finding in findings:
            render_finding(finding, console, root)
    elif not result.text:
        console.write()
        console.write(f"  {console.paint(t('ui.no_findings', lang), 'green')}")

    counts: dict[str, int] = {}
    for finding in result.findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    parts = [
        console.paint(f"{count} {severity}", SEVERITY_COLOR.get(severity, "grey"))
        for severity, count in sorted(counts.items(), key=lambda item: SEVERITY_ORDER.get(item[0], 9))
    ]
    summary = " · ".join(parts) if parts else ""
    if result.escalated:
        extra = f"gemini ({result.escalation_reason})"
        extra += f" · {result.tokens} tokens" if result.tokens else ""
        summary = f"{summary} · {console.paint(extra, 'magenta')}" if summary else extra
    elif result.findings or result.text:
        summary = f"{summary} · {console.paint('local', 'green')}" if summary else "local"

    from .suggestions import register_options_from_scan

    options = register_options_from_scan(result)
    if options:
        console.write()
        console.write(f"  {console.paint('Quick Actions / Suggested Fixes:', 'cyan', bold=True)}")
        for opt in options:
            console.write(f"    {console.paint(f'[{opt.index}]', 'bright_yellow', bold=True)} {opt.title}")
        console.write(f"    {console.paint('💡 Type 1 or /1 to execute immediately', 'grey', dim=True)}")

    console.write()
    console.rule(summary, "grey")
    console.write()


def render_compact(report: Report, config: Config | None = None) -> str:
    """שורה אחת - שימושי ללוגים ולסביבות בלי טרמינל."""
    config = config or get_config()
    best = report.best
    if best is None:
        return f"SBpy: {report.exc_type}: {report.exc_message} ({report.skipped_reason})"
    return (
        f"SBpy [{best.source} {int(best.confidence * 100)}%] "
        f"{best.title}"
        + (f" | {best.suggestion}" if best.suggestion else "")
    )
