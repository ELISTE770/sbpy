"""חיבור לכלים שמסביב: git, CI, ועורכי קוד.

* ``changed_files`` - רק מה שהשתנה, ל-pre-commit ולבדיקות מהירות
* ``to_sarif`` - פורמט שגיטהאב, VS Code וכלי CI יודעים לקרוא
* ``to_github_annotations`` - שורות ``::error file=...`` ל-GitHub Actions
* ``editor_lines`` - ``file:line:col: message`` שכל עורך יודע לקפוץ אליו
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Iterable, Sequence

from .results import Finding, ScanResult
from .static.checks import RULE_CATEGORY

SEVERITY_TO_SARIF = {
    "critical": "error",
    "error": "error",
    "warn": "warning",
    "info": "note",
}

SEVERITY_TO_GITHUB = {
    "critical": "error",
    "error": "error",
    "warn": "warning",
    "info": "notice",
}


# ======================================================================
# git
# ======================================================================
def _git(arguments: Sequence[str], cwd: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_git_repo(path: str = ".") -> bool:
    return bool(_git(["rev-parse", "--is-inside-work-tree"], path))


def changed_files(
    path: str = ".",
    *,
    base: str = "",
    include_untracked: bool = True,
    python_only: bool = True,
) -> list[str]:
    """קבצים שהשתנו. בלי ``base`` - מול ה-index וה-HEAD (מה שלא נשמר עדיין)."""
    root = os.path.abspath(path if os.path.isdir(path) else os.path.dirname(path) or ".")
    if not is_git_repo(root):
        return []

    names: list[str] = []
    if base:
        names.extend(_git(["diff", "--name-only", f"{base}...HEAD"], root))
        names.extend(_git(["diff", "--name-only", base], root))
    else:
        names.extend(_git(["diff", "--name-only", "HEAD"], root))
        names.extend(_git(["diff", "--name-only", "--cached"], root))
    if include_untracked:
        names.extend(_git(["ls-files", "--others", "--exclude-standard"], root))

    top = _git(["rev-parse", "--show-toplevel"], root)
    base_dir = top[0] if top else root

    seen: list[str] = []
    for name in names:
        full = os.path.normpath(os.path.join(base_dir, name))
        if python_only and not full.endswith(".py"):
            continue
        if not os.path.isfile(full):
            continue
        if full not in seen:
            seen.append(full)
    return sorted(seen)


# ======================================================================
# פורמטים לייצוא
# ======================================================================
def _all_findings(results: Iterable[ScanResult]) -> list[Finding]:
    found: list[Finding] = []
    for result in results:
        found.extend(result.findings)
    return found


def to_sarif(results: Iterable[ScanResult], *, root: str = "") -> dict[str, Any]:
    """SARIF 2.1.0 - נקרא על ידי GitHub code scanning ו-VS Code."""
    findings = _all_findings(results)
    root = root or os.getcwd()

    rules: dict[str, dict[str, Any]] = {}
    sarif_results: list[dict[str, Any]] = []

    for finding in findings:
        rule_id = finding.rule or "sbpy"
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": rule_id},
                "properties": {"category": RULE_CATEGORY.get(rule_id, "bug")},
            }
        try:
            relative = os.path.relpath(finding.file, root).replace("\\", "/")
        except ValueError:
            relative = finding.file.replace("\\", "/")

        sarif_results.append(
            {
                "ruleId": rule_id,
                "level": SEVERITY_TO_SARIF.get(finding.severity, "warning"),
                "message": {"text": finding.message + (f" — {finding.hint}" if finding.hint else "")},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": relative},
                            "region": {
                                "startLine": max(1, finding.line),
                                "startColumn": max(1, finding.col + 1),
                            },
                        }
                    }
                ],
                "properties": {"source": finding.source, "confidence": finding.confidence},
            }
        )

    from . import __version__

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "SBpy",
                        "version": __version__,
                        "informationUri": "https://github.com/eli/sbpy",
                        "rules": list(rules.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def to_github_annotations(results: Iterable[ScanResult], *, root: str = "") -> list[str]:
    """שורות שגיטהאב אקשנס מציג כהערות על ה-diff."""
    root = root or os.getcwd()
    lines: list[str] = []
    for finding in _all_findings(results):
        level = SEVERITY_TO_GITHUB.get(finding.severity, "warning")
        try:
            relative = os.path.relpath(finding.file, root).replace("\\", "/")
        except ValueError:
            relative = finding.file.replace("\\", "/")
        message = finding.message.replace("\n", " ")
        if finding.hint:
            message += f" | {finding.hint}"
        lines.append(
            f"::{level} file={relative},line={max(1, finding.line)},"
            f"col={max(1, finding.col + 1)},title=SBpy {finding.rule}::{message}"
        )
    return lines


def editor_lines(results: Iterable[ScanResult], *, root: str = "") -> list[str]:
    """``file:line:col: severity: message`` - כל עורך יודע לקפוץ לזה."""
    root = root or os.getcwd()
    lines: list[str] = []
    for finding in _all_findings(results):
        try:
            relative = os.path.relpath(finding.file, root)
        except ValueError:
            relative = finding.file
        lines.append(
            f"{relative}:{max(1, finding.line)}:{max(1, finding.col + 1)}: "
            f"{finding.severity}: {finding.message} [{finding.rule}]"
        )
    return lines


FORMATS = {
    "sarif": lambda results, root: json.dumps(to_sarif(results, root=root), ensure_ascii=False, indent=2),
    "github": lambda results, root: "\n".join(to_github_annotations(results, root=root)),
    "editor": lambda results, root: "\n".join(editor_lines(results, root=root)),
    "json": lambda results, root: json.dumps(
        [r.to_dict() for r in results], ensure_ascii=False, indent=2
    ),
}


def render_format(name: str, results: Iterable[ScanResult], *, root: str = "") -> str:
    formatter = FORMATS.get(name)
    if formatter is None:
        raise KeyError(f"פורמט לא מוכר: {name}. אפשרויות: {', '.join(sorted(FORMATS))}")
    return formatter(list(results), root or os.getcwd())
