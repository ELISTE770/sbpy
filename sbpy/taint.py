"""ניתוח זרימת מידע סטטי ואבטחה עמוקה (Static Taint Analysis).

עוקב אחר זרימת קלט ממקורות לא אמינים (Taint Sources) דרך השמות ומשתני ביניים
אל תוך יעדים רגישים ומסוכנים (Dangerous Sinks) כגון שאילתות SQL, פקודות מעטפת, וקבצים.
"""

from __future__ import annotations

import ast

from .static.checks import Finding, SourceUnit, _dotted


TAINT_SOURCES = {
    "input",
    "os.environ.get",
    "os.getenv",
    "sys.argv",
    "request.args.get",
    "request.json.get",
    "request.form.get",
    "request.get_json",
    "request.data",
}

TAINT_SINKS = {
    "eval": "הזרקת קוד",
    "exec": "הזרקת קוד",
    "os.system": "הזרקת פקודות מעטפת",
    "os.popen": "הזרקת פקודות מעטפת",
    "sqlite3.execute": "הזרקת SQL",
    "cursor.execute": "הזרקת SQL",
    "cur.execute": "הזרקת SQL",
    "db.execute": "הזרקת SQL",
    "open": "גישה לא מאומתת לקבצים",
}


def _is_source_call(node: ast.AST) -> bool:
    """בודק האם ביטוי הוא קריאה למקור קלט (Taint Source)."""
    if isinstance(node, ast.Call):
        name = _dotted(node.func)
        short = name.split(".")[-1]
        if name in TAINT_SOURCES or short in TAINT_SOURCES:
            return True
        if "request." in name or "args.get" in name:
            return True
    elif isinstance(node, ast.Subscript):
        name = _dotted(node.value)
        if "sys.argv" in name or "os.environ" in name or "request." in name:
            return True
    return False


def _contains_taint(node: ast.AST, tainted: set[str]) -> str | None:
    """בודק האם ביטוי מכיל משתנה מוכתם כלשהו."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in tainted:
            return sub.id
    return None


def scan_function_taint(fn_node: ast.FunctionDef | ast.AsyncFunctionDef, filename: str) -> list[Finding]:
    """מבצע ניתוח Taint Data-Flow בתוך גוף פונקציה בודדת."""
    tainted_vars: set[str] = set()
    findings: list[Finding] = []

    for stmt in fn_node.body:
        # 1. מעקב אחר השמות (Assign / AnnAssign)
        if isinstance(stmt, ast.Assign):
            is_src = _is_source_call(stmt.value)
            tainted_origin = _contains_taint(stmt.value, tainted_vars)

            if is_src or tainted_origin:
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        tainted_vars.add(target.id)

        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            is_src = _is_source_call(stmt.value)
            tainted_origin = _contains_taint(stmt.value, tainted_vars)

            if (is_src or tainted_origin) and isinstance(stmt.target, ast.Name):
                tainted_vars.add(stmt.target.id)

        # 2. בדיקת קריאות ל-Sinks מסוכנים
        for call_node in ast.walk(stmt):
            if isinstance(call_node, ast.Call):
                name = _dotted(call_node.func)
                short = name.split(".")[-1]

                sink_desc = TAINT_SINKS.get(name) or TAINT_SINKS.get(short)
                if sink_desc:
                    # בודקים האם אחד הארגומנטים מוכתם
                    for arg in call_node.args:
                        taint_name = _contains_taint(arg, tainted_vars)
                        if taint_name:
                            findings.append(
                                Finding(
                                    file=filename,
                                    line=call_node.lineno,
                                    col=call_node.col_offset,
                                    rule="taint-vulnerability",
                                    message=f"קלט לא מסונן מהמשתנה `{taint_name}` זורם ישירות אל `{name}()` ({sink_desc})",
                                    severity="critical",
                                    hint=f"סנן ואמת את הערך לפני העברתו לפונקציה `{name}`.",
                                )
                            )
                            break

    return findings


def scan_taint(unit: SourceUnit) -> list[Finding]:
    """סורק את הקובץ לאיתור חולשות זרימת מידע (Taint Analysis)."""
    if unit.tree is None:
        return []

    findings: list[Finding] = []
    for node in ast.walk(unit.tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(scan_function_taint(node, unit.filename))

    return findings
