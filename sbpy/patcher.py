"""תיקון אוטומטי של קוד - הצעד מ"יועץ" ל"כלי שמתקן".

שני מקורות לתיקון:
* ``Diagnosis`` משגיאת ריצה - יש בו ``meta`` מדויק (``bad`` -> ``good``).
* ``Finding`` מניתוח סטטי - יש בו חוק, שורה ועמודה.

שלוש הגנות:
1. כל תיקון נבנה מהשורה עצמה, לא מניחוש.
2. אחרי החלת התיקונים הקובץ עובר ``ast.parse``; אם הוא נשבר - ביטול מלא.
3. גיבוי ``.sbpy.bak`` לפני כתיבה (אפשר לכבות).
"""

from __future__ import annotations

import ast
import difflib
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .results import Diagnosis, Finding, Report, ScanResult

BACKUP_SUFFIX = ".sbpy.bak"


@dataclass
class Edit:
    """שינוי בשורה אחת. ``new_lines`` ריק פירושו מחיקת השורה."""

    file: str
    line: int
    old_line: str
    new_lines: list[str]
    rule: str
    description: str = ""

    @property
    def is_delete(self) -> bool:
        return not self.new_lines


@dataclass
class Patch:
    edits: list[Edit] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(חוק, סיבה) - ממצאים שלא ניתן לתקן אוטומטית."""

    def __bool__(self) -> bool:
        return bool(self.edits)

    def __len__(self) -> int:
        return len(self.edits)

    def files(self) -> list[str]:
        seen: list[str] = []
        for edit in self.edits:
            if edit.file not in seen:
                seen.append(edit.file)
        return seen

    # ------------------------------------------------------------------
    def _rewrite(self, path: str) -> tuple[list[str], list[str]]:
        """מחזיר (שורות מקוריות, שורות אחרי התיקון) עבור קובץ אחד."""
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            original = handle.read().splitlines()

        by_line: dict[int, Edit] = {}
        for edit in self.edits:
            if os.path.abspath(edit.file) == os.path.abspath(path):
                by_line[edit.line] = edit

        updated: list[str] = []
        for number, text in enumerate(original, start=1):
            edit = by_line.get(number)
            if edit is None:
                updated.append(text)
                continue
            if edit.old_line.strip() and edit.old_line.strip() != text.strip():
                # הקובץ השתנה מאז הסריקה - לא נוגעים
                updated.append(text)
                continue
            updated.extend(edit.new_lines)
        return original, updated

    def diff(self) -> str:
        """diff מאוחד לכל הקבצים שמושפעים."""
        chunks: list[str] = []
        for path in self.files():
            try:
                original, updated = self._rewrite(path)
            except OSError:
                continue
            name = os.path.basename(path)
            chunks.extend(
                difflib.unified_diff(
                    original, updated, fromfile=f"a/{name}", tofile=f"b/{name}", lineterm="", n=2
                )
            )
        return "\n".join(chunks)

    def apply(self, *, backup: bool = True) -> list[str]:
        """כותב את התיקונים לדיסק. מחזיר את רשימת הקבצים ששונו."""
        changed: list[str] = []
        for path in self.files():
            try:
                original, updated = self._rewrite(path)
            except OSError:
                continue
            if original == updated:
                continue

            source = "\n".join(updated) + "\n"
            try:
                ast.parse(source)
            except SyntaxError:
                # התיקון שבר את הקובץ - מוותרים עליו לגמרי
                continue

            # ``ast.parse`` לבדו לא מספיק: מחיקת שם מ-import עדיין מתפרשת,
            # והכשל מתגלה רק בזמן ריצה. כאן בודקים שאף שם שהוסר אינו
            # עדיין בשימוש בקובץ.
            orphan = _orphaned_name("\n".join(original), source)
            if orphan:
                self.skipped.append(
                    ("apply-guard", f"{os.path.basename(path)}: `{orphan}` עדיין בשימוש")
                )
                continue

            if backup:
                try:
                    from .git_ops import record_backup

                    record_backup(path, "\n".join(original) + "\n")
                except Exception:  # sbpy: ignore=silent-except
                    pass
            try:
                with open(path, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(source)
            except OSError:
                continue
            changed.append(path)
        return changed

    def apply_interactive(self, *, backup: bool = True, color: bool = True) -> list[str]:
        """מצב אינטראקטיבי: מציג diff עבור כל קובץ ומבקש אישור מהמשתמש [y/n/a/q]."""
        changed: list[str] = []
        apply_all = False

        for path in self.files():
            try:
                original, updated = self._rewrite(path)
            except OSError:
                continue
            if original == updated:
                continue

            name = os.path.basename(path)
            file_diff = list(
                difflib.unified_diff(
                    original, updated, fromfile=f"a/{name}", tofile=f"b/{name}", lineterm="", n=2
                )
            )
            if not file_diff:
                continue

            if not apply_all:
                try:
                    from .diff_viewer import render_side_by_side

                    render_side_by_side(path, original, updated)
                except Exception:
                    print(f"\n--- Proposed changes for {path}:")
                    for diff_line in file_diff:
                        if diff_line.startswith("+"):
                            print(f"\033[32m{diff_line}\033[0m" if color else diff_line)
                        elif diff_line.startswith("-"):
                            print(f"\033[31m{diff_line}\033[0m" if color else diff_line)
                        elif diff_line.startswith("@"):
                            print(f"\033[36m{diff_line}\033[0m" if color else diff_line)
                        else:
                            print(diff_line)

                while True:
                    try:
                        choice = input(f"  Apply changes to {name}? [y/n/a/q]: ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        return changed

                    if choice in ("y", "yes", ""):
                        break
                    elif choice in ("n", "no"):
                        file_diff = []
                        break
                    elif choice in ("a", "all"):
                        apply_all = True
                        break
                    elif choice in ("q", "quit"):
                        return changed

            if not file_diff:
                continue

            source = "\n".join(updated) + "\n"
            try:
                ast.parse(source)
            except SyntaxError:
                continue

            if backup:
                try:
                    shutil.copy2(path, path + BACKUP_SUFFIX)
                except OSError:  # sbpy: ignore=silent-except
                    pass
            try:
                with open(path, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(source)
                changed.append(path)
            except OSError:
                continue

        return changed


def _bound_names(source: str) -> set[str]:
    """Every name an import statement brings into the module namespace."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def _loaded_names(source: str) -> set[str]:
    """Every name the module reads, including inside string annotations."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            root: ast.AST = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                names.add(root.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # מחרוזת annotation (``"Config | None"``) היא שימוש לכל דבר
            names.update(re.findall(r"[A-Za-z_]\w*", node.value))
    return names


def _orphaned_name(before: str, after: str) -> str:
    """A name an import used to bind, now unbound, and still read.

    Returns the first such name, or an empty string when the edit is safe.
    This is the guard that stops a fix from silently deleting a live import.
    """
    removed = _bound_names(before) - _bound_names(after)
    if not removed:
        return ""
    still_used = _loaded_names(after)
    for name in sorted(removed):
        if name in still_used:
            return name
    return ""


# ======================================================================
# בוני תיקונים
# ======================================================================
def _word_replace(text: str, bad: str, good: str) -> str:
    """מחליף מופע שלם של שם, בלי לפגוע בשמות שמכילים אותו."""
    pattern = re.compile(rf"(?<![\w.]){re.escape(bad)}(?![\w])")
    return pattern.sub(good, text, count=1)


def _quoted_replace(text: str, bad: str, good: str) -> str:
    """מחליף מחרוזת בין גרשיים - למפתחות מילון ולשמות קבצים."""
    for quote in ("'", '"'):
        needle = f"{quote}{bad}{quote}"
        if needle in text:
            return text.replace(needle, f"{quote}{good}{quote}", 1)
    return _word_replace(text, bad, good)


def _import_insert_line(lines: list[str]) -> int:
    """אחרי איזו שורה להוסיף import חדש (0 = בתחילת הקובץ)."""
    last_import = 0
    in_docstring = False
    delimiter = ""
    for number, text in enumerate(lines, start=1):
        stripped = text.strip()
        if in_docstring:
            if delimiter and delimiter in stripped:
                in_docstring = False
                last_import = max(last_import, number)
            continue
        if number == 1 and stripped.startswith(('"""', "'''")):
            delimiter = stripped[:3]
            if stripped.count(delimiter) < 2:
                in_docstring = True
            last_import = number
            continue
        if stripped.startswith(("import ", "from ")):
            last_import = number
        elif stripped and not stripped.startswith("#"):
            break
    return last_import


# --- תיקונים לפי חוק סטטי -------------------------------------------
def _fix_missing_f(line: str, finding: Finding) -> list[str] | None:
    match = re.search(r"""(?<![\w"'])(['"])""", line[finding.col :] if finding.col else line)
    if finding.col and finding.col < len(line) and line[finding.col] in "\"'":
        return [line[: finding.col] + "f" + line[finding.col :]]
    if match:
        position = (finding.col or 0) + match.start(1)
        return [line[:position] + "f" + line[position:]]
    return None


def _fix_eq_none(line: str, _finding: Finding) -> list[str] | None:
    updated = re.sub(r"\s*!=\s*None\b", " is not None", line)
    updated = re.sub(r"\s*==\s*None\b", " is None", updated)
    return [updated] if updated != line else None


def _fix_is_literal(line: str, _finding: Finding) -> list[str] | None:
    updated = re.sub(r"\bis\s+not\s+(?=['\"\d])", "!= ", line)
    updated = re.sub(r"\bis\s+(?=['\"\d])", "== ", updated)
    return [updated] if updated != line else None


def _fix_bare_except(line: str, _finding: Finding) -> list[str] | None:
    updated = re.sub(r"\bexcept\s*:", "except Exception:", line, count=1)
    return [updated] if updated != line else None


def _fix_keys_membership(line: str, _finding: Finding) -> list[str] | None:
    updated = re.sub(r"\.keys\(\)\s*(?=:|\)|$|\s)", "", line, count=1)
    return [updated] if updated != line else None


def _fix_delete_line(_line: str, _finding: Finding) -> list[str] | None:
    return []


def _fix_unused_import(line: str, finding: Finding) -> list[str] | None:
    """Removes one unused name from an import - never the whole statement.

    ``from x import A, B`` with only ``B`` unused must become
    ``from x import A``. Deleting the line would silently take ``A`` too,
    and the file would still parse - the failure only shows up at runtime.
    """
    name = finding.symbol
    if not name:
        # Findings from older runs or external tools carry the name only in
        # the message. Recover it rather than refusing to help.
        quoted = re.findall(r"`([A-Za-z_][\w.]*)`", finding.message)
        name = quoted[0] if quoted else ""

    stripped = line.strip()
    if not stripped.startswith(("import ", "from ")):
        return None

    try:
        parsed = ast.parse(stripped)
    except SyntaxError:
        return None
    if not parsed.body or not isinstance(parsed.body[0], (ast.Import, ast.ImportFrom)):
        return None

    statement = parsed.body[0]
    if not name:
        # Still unknown: only safe when the statement binds a single name.
        return [] if len(statement.names) == 1 else None

    kept = [
        alias for alias in statement.names if (alias.asname or alias.name.split(".")[0]) != name
    ]
    if len(kept) == len(statement.names):
        return None
    if not kept:
        return []  # that name was the only one - the line goes

    indent = line[: len(line) - len(line.lstrip())]
    rendered = ", ".join(
        alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in kept
    )
    if isinstance(statement, ast.ImportFrom):
        module = "." * (statement.level or 0) + (statement.module or "")
        return [f"{indent}from {module} import {rendered}"]
    return [f"{indent}import {rendered}"]


def _fix_len_zero(line: str, _finding: Finding) -> list[str] | None:
    updated = re.sub(r"\blen\(([^()]+)\)\s*==\s*0\b", r"not \1", line)
    updated = re.sub(r"\blen\(([^()]+)\)\s*!=\s*0\b", r"\1", updated)
    updated = re.sub(r"\blen\(([^()]+)\)\s*>\s*0\b", r"\1", updated)
    return [updated] if updated != line else None


def _fix_eq_bool(line: str, _finding: Finding) -> list[str] | None:
    updated = re.sub(r"\s*==\s*True\b", "", line)
    updated = re.sub(r"\s*!=\s*False\b", "", updated)
    return [updated] if updated != line else None


STATIC_FIXERS: dict[str, Callable[[str, Finding], list[str] | None]] = {
    "missing-f-prefix": _fix_missing_f,
    "compare-none-with-eq": _fix_eq_none,
    "is-with-literal": _fix_is_literal,
    "bare-except": _fix_bare_except,
    "keys-membership": _fix_keys_membership,
    "unused-import": _fix_unused_import,
    "len-compare-zero": _fix_len_zero,
    "compare-bool-with-eq": _fix_eq_bool,
}

FIXABLE_RULES = frozenset(STATIC_FIXERS)

# תיקונים שנובעים משגיאת ריצה, לפי meta["kind"]
RUNTIME_KINDS = frozenset(
    {
        "name_typo",
        "attr_typo",
        "kwarg_typo",
        "key_typo",
        "key_case",
        "file_typo",
        "module_name_typo",
        "missing_import",
        "import_name_typo",
        "module_typo",
        "project_import",
    }
)


# ======================================================================
def _read_lines(path: str) -> list[str] | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return None


def build_from_findings(findings: Iterable[Finding]) -> Patch:
    """בונה תיקונים מממצאי ניתוח סטטי."""
    patch = Patch()
    cache: dict[str, list[str] | None] = {}

    for finding in findings:
        fixer = STATIC_FIXERS.get(finding.rule)
        if fixer is None:
            patch.skipped.append((finding.rule, "אין תיקון אוטומטי בטוח"))
            continue
        if not finding.file or not os.path.isfile(finding.file):
            patch.skipped.append((finding.rule, "אין קובץ"))
            continue

        if finding.file not in cache:
            cache[finding.file] = _read_lines(finding.file)
        lines = cache[finding.file]
        if lines is None or not (1 <= finding.line <= len(lines)):
            patch.skipped.append((finding.rule, "שורה לא נמצאה"))
            continue

        original = lines[finding.line - 1]
        updated = fixer(original, finding)
        if updated is None or updated == [original]:
            patch.skipped.append((finding.rule, "השורה לא השתנתה"))
            continue

        patch.edits.append(
            Edit(
                file=finding.file,
                line=finding.line,
                old_line=original,
                new_lines=updated,
                rule=finding.rule,
                description=finding.message,
            )
        )
    return patch


def build_from_diagnosis(diagnosis: Diagnosis, path: str, line: int) -> Patch:
    """בונה תיקון משגיאת ריצה שאובחנה מקומית."""
    patch = Patch()
    kind = str(diagnosis.meta.get("kind", ""))
    if kind not in RUNTIME_KINDS:
        patch.skipped.append((diagnosis.rule, "אין תיקון אוטומטי בטוח"))
        return patch
    if not path or not os.path.isfile(path):
        patch.skipped.append((diagnosis.rule, "אין קובץ"))
        return patch

    lines = _read_lines(path)
    if lines is None:
        patch.skipped.append((diagnosis.rule, "לא ניתן לקרוא את הקובץ"))
        return patch

    # הוספת שורת import חסרה
    statement = ""
    if kind == "project_import":
        statement = str(diagnosis.meta.get("statement") or "")
    elif kind in {"missing_import", "module_name_typo"}:
        module = str(diagnosis.meta.get("good") or diagnosis.meta.get("module") or "")
        statement = f"import {module}" if module else ""

    if statement:
        insert_after = _import_insert_line(lines)
        anchor = insert_after if insert_after else 1
        anchor_line = lines[anchor - 1] if 1 <= anchor <= len(lines) else ""
        new_block = [anchor_line, statement] if insert_after else [statement, anchor_line]
        patch.edits.append(
            Edit(
                file=path,
                line=anchor,
                old_line=anchor_line,
                new_lines=new_block,
                rule=diagnosis.rule,
                description=statement,
            )
        )
        if kind in {"missing_import", "project_import"}:
            return patch

    bad = str(diagnosis.meta.get("bad") or "")
    good = str(diagnosis.meta.get("good") or "")
    if not bad or not good or not (1 <= line <= len(lines)):
        return patch

    original = lines[line - 1]
    if kind in {"key_typo", "key_case", "file_typo"}:
        good_value = os.path.basename(good) if kind == "file_typo" else good
        bad_value = os.path.basename(bad) if kind == "file_typo" else bad
        updated = _quoted_replace(original, bad_value, good_value)
    else:
        updated = _word_replace(original, bad, good)

    if updated == original:
        patch.skipped.append((diagnosis.rule, "לא נמצא מה להחליף בשורה"))
        return patch

    patch.edits.append(
        Edit(
            file=path,
            line=line,
            old_line=original,
            new_lines=[updated],
            rule=diagnosis.rule,
            description=f"{bad} -> {good}",
        )
    )
    return patch


def build_from_report(report: Report) -> Patch:
    """בונה תיקון מדוח שגיאה (האבחנה הטובה ביותר)."""
    best = report.best
    if best is None:
        return Patch()
    return build_from_diagnosis(best, report.file, report.snippet_mark)


def build_from_scan(result: ScanResult) -> Patch:
    return build_from_findings(result.findings)
