"""ניהול חוקים והגדרות מותאמות אישית לפרויקט (.sbpyrules או pyproject.toml).

מאפשר לצוותי פיתוח להגדיר קונבנציות ספציפיות לפרויקט (ספריות אסורות,
פונקציות לא מאושרות, כללי שמות), הנאכפות בחינם בשכבה הסטטית ומנחות את ה-AI.
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .static.checks import Finding, SourceUnit, _dotted


@dataclass
class ProjectRules:
    banned_imports: dict[str, str] = field(default_factory=dict)
    banned_calls: dict[str, str] = field(default_factory=dict)
    class_name_pattern: str = ""
    func_name_pattern: str = ""
    custom_messages: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return (
            not self.banned_imports
            and not self.banned_calls
            and not self.class_name_pattern
            and not self.func_name_pattern
            and not self.custom_messages
        )


def _parse_pyproject_toml_rules(content: str) -> dict[str, Any] | None:
    """פיענוח פשוט של [tool.sbpy.rules] מתוך pyproject.toml ללא תלויות חיצוניות."""
    in_section = False
    data: dict[str, Any] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            in_section = section in ("tool.sbpy.rules", "tool.sbpy")
            continue
        if in_section and "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            data[key] = val
    return data if data else None


def load_rules(start_dir: str | None = None) -> ProjectRules:
    """טוען את חוקי הפרויקט מ-.sbpyrules או pyproject.toml החל מ-start_dir כלפי מעלה."""
    cur = Path(start_dir or os.getcwd()).resolve()

    for directory in [cur, *cur.parents]:
        # 1. בדיקת .sbpyrules (JSON)
        rules_file = directory / ".sbpyrules"
        if rules_file.is_file():
            try:
                with open(rules_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    return ProjectRules(
                        banned_imports=dict(data.get("banned_imports", {})),
                        banned_calls=dict(data.get("banned_calls", {})),
                        class_name_pattern=str(data.get("class_name_pattern", "")),
                        func_name_pattern=str(data.get("func_name_pattern", "")),
                        custom_messages=dict(data.get("custom_messages", {})),
                    )
            except (OSError, ValueError):  # sbpy: ignore=silent-except
                pass

        # 2. בדיקת pyproject.toml
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file():
            try:
                with open(pyproject, "r", encoding="utf-8") as handle:
                    content = handle.read()
                parsed = _parse_pyproject_toml_rules(content)
                if parsed:
                    return ProjectRules(
                        class_name_pattern=str(parsed.get("class_name_pattern", "")),
                        func_name_pattern=str(parsed.get("func_name_pattern", "")),
                    )
            except OSError:  # sbpy: ignore=silent-except
                pass

    return ProjectRules()


def load_directory_rules(start_dir: str | None = None) -> list[Any]:
    """Loads custom AST rule functions from `.sbpy/rules/*.py`."""
    cur = Path(start_dir or os.getcwd()).resolve()
    callables: list[Any] = []
    for directory in [cur, *cur.parents]:
        rules_dir = directory / ".sbpy" / "rules"
        if rules_dir.is_dir():
            for py_file in rules_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                try:
                    import importlib.util

                    spec = importlib.util.spec_from_file_location(f"sbpy_rule_{py_file.stem}", str(py_file))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "check") and callable(mod.check):
                            callables.append(mod.check)
                except Exception:  # sbpy: ignore=silent-except
                    pass
    return callables


def check_project_rules(unit: SourceUnit, rules: ProjectRules | None = None) -> list[Finding]:
    """מריץ בדיקות סטטיות מול חוקי הפרויקט המותאמים אישית (כולל .sbpy/rules/*.py)."""
    findings: list[Finding] = []

    # Run custom Python plugins from .sbpy/rules/
    try:
        for custom_checker in load_directory_rules(os.path.dirname(unit.filename) if unit.filename != "<code>" else None):
            res = custom_checker(unit)
            if isinstance(res, list):
                findings.extend(res)
    except Exception:  # sbpy: ignore=silent-except
        pass

    rules = rules or load_rules(os.path.dirname(unit.filename) if unit.filename != "<code>" else None)
    if rules.is_empty or unit.tree is None:
        return findings

    for node in ast.walk(unit.tree):
        # 1. ספריות אסורות (banned_imports)
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if root_name in rules.banned_imports:
                    reason = rules.banned_imports[root_name]
                    findings.append(
                        Finding(
                            file=unit.filename,
                            line=node.lineno,
                            col=node.col_offset,
                            rule="banned-import",
                            message=f"יבוא של `{root_name}` אסור לפי חוקי הפרויקט",
                            severity="error",
                            hint=reason,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_name = node.module.split(".")[0]
                if root_name in rules.banned_imports:
                    reason = rules.banned_imports[root_name]
                    findings.append(
                        Finding(
                            file=unit.filename,
                            line=node.lineno,
                            col=node.col_offset,
                            rule="banned-import",
                            message=f"יבוא מ-`{root_name}` אסור לפי חוקי הפרויקט",
                            severity="error",
                            hint=reason,
                        )
                    )

        # 2. קריאות לפונקציות אסורות (banned_calls)
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            short = name.split(".")[-1]
            if name in rules.banned_calls or short in rules.banned_calls:
                reason = rules.banned_calls.get(name) or rules.banned_calls.get(short, "")
                findings.append(
                    Finding(
                        file=unit.filename,
                        line=node.lineno,
                        col=node.col_offset,
                        rule="banned-call",
                        message=f"קריאה ל-`{name}` אסורה לפי חוקי הפרויקט",
                        severity="error",
                        hint=reason,
                    )
                )

        # 3. תבניות שמות (naming conventions)
        if rules.class_name_pattern and isinstance(node, ast.ClassDef):
            if not re.match(rules.class_name_pattern, node.name):
                findings.append(
                    Finding(
                        file=unit.filename,
                        line=node.lineno,
                        col=node.col_offset,
                        rule="class-naming",
                        message=f"שם המחלקה `{node.name}` אינו תואם את התבנית `{rules.class_name_pattern}`",
                        severity="warn",
                    )
                )

        if rules.func_name_pattern and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("__") and not re.match(rules.func_name_pattern, node.name):
                findings.append(
                    Finding(
                        file=unit.filename,
                        line=node.lineno,
                        col=node.col_offset,
                        rule="function-naming",
                        message=f"שם הפונקציה `{node.name}` אינו תואם את התבנית `{rules.func_name_pattern}`",
                        severity="warn",
                    )
                )

    return findings


def format_rules_for_prompt(rules: ProjectRules) -> str:
    """מעצב את חוקי הפרויקט כהנחיה עבור מודל ה-AI."""
    if rules.is_empty:
        return ""

    lines = ["חוקי הפרויקט והקונבנציות המקומיות:"]
    for mod, reason in rules.banned_imports.items():
        lines.append(f"- אל תשתמש בספרייה `{mod}`. {reason}")
    for call, reason in rules.banned_calls.items():
        lines.append(f"- אל תקרא ל-`{call}`. {reason}")
    if rules.class_name_pattern:
        lines.append(f"- שמות מחלקות חייבים להתאים לתבנית `{rules.class_name_pattern}`.")
    if rules.func_name_pattern:
        lines.append(f"- שמות פונקציות חייבים להתאים לתבנית `{rules.func_name_pattern}`.")
    return "\n".join(lines)
