"""גרף קריאות פרויקטלי וזיהוי קוד מת (Dead Code Detection).

סורק את כל קובצי הפרויקט, בונה גרף של הגדרות סמלים וקריאות להם,
ומאתר פונקציות, מחלקות ומשתנים שלעולם לא נקראים בשום מקום בפרויקט.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field

from .index import iter_project_files
from .static.checks import Finding


@dataclass
class SymbolDef:
    name: str
    kind: str  # "function", "class", "variable"
    file: str
    line: int
    col: int = 0
    in_script: bool = False
    """Defined in a module that runs as a script - reachable by a person."""

    decorated: bool = False
    """A decorated definition is registered somewhere (route, fixture, plugin).

    Nothing calls it by name, yet it is very much alive - so it must never
    be reported as dead.
    """


@dataclass
class ProjectGraph:
    definitions: dict[str, list[SymbolDef]] = field(default_factory=dict)
    references: set[str] = field(default_factory=set)
    files_scanned: int = 0


def _exported_names(tree: ast.AST) -> set[str]:
    """The strings listed in ``__all__`` - the module's public contract."""
    exported: set[str] = set()
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AugAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        for element in ast.walk(node.value) if node.value is not None else []:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                exported.add(element.value)
    return exported


def entry_point_names(root_path: str) -> set[str]:
    """Callables wired up in ``pyproject.toml`` - reachable from outside the code."""
    names: set[str] = set()
    path = os.path.join(root_path, "pyproject.toml")
    if not os.path.isfile(path):
        return names
    try:
        import tomllib

        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except Exception:
        return names

    project = data.get("project", {}) if isinstance(data, dict) else {}
    for section in ("scripts", "gui-scripts", "entry-points"):
        block = project.get(section)
        if isinstance(block, dict):
            for value in block.values():
                if isinstance(value, str) and ":" in value:
                    names.add(value.split(":", 1)[1].strip())
                elif isinstance(value, dict):
                    for nested in value.values():
                        if isinstance(nested, str) and ":" in nested:
                            names.add(nested.split(":", 1)[1].strip())
    return names


def is_script_module(tree: ast.AST) -> bool:
    """Does the module run as a script (``if __name__ == "__main__":``).

    Such a module is an entry point: its top-level names are reached by a
    person running it, not by another module importing them.
    """
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or not isinstance(test.left, ast.Name):
            continue
        if test.left.id == "__name__":
            return True
    return False


def _extract_file_symbols(path: str) -> tuple[list[SymbolDef], set[str]]:
    """מחלץ את כל ההגדרות וההפניות מקובץ פייתון בודד."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError):
        return [], set()

    defs: list[SymbolDef] = []
    refs: set[str] = set()
    script = is_script_module(tree)

    # חילוץ הגדרות ברמה עליונה
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append(
                SymbolDef(
                    name=node.name,
                    kind="function",
                    file=path,
                    line=node.lineno,
                    col=node.col_offset,
                    in_script=script,
                    decorated=bool(node.decorator_list),
                )
            )
        elif isinstance(node, ast.ClassDef):
            defs.append(
                SymbolDef(
                    name=node.name,
                    kind="class",
                    file=path,
                    line=node.lineno,
                    col=node.col_offset,
                    in_script=script,
                    decorated=bool(node.decorator_list),
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defs.append(
                        SymbolDef(
                            name=target.id,
                            kind="variable",
                            file=path,
                            line=target.lineno,
                            col=target.col_offset,
                            in_script=script,
                        )
                    )

    # `__all__` הוא שימוש לכל דבר: מה שמיוצא במפורש אינו קוד מת.
    refs.update(_exported_names(tree))

    # חילוץ כל ההפניות והקריאות
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                refs.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                refs.add(alias.asname or alias.name)

    return defs, refs


def build_project_graph(root_path: str = ".") -> ProjectGraph:
    """בונה את גרף ההגדרות והקריאות של כל הפרויקט."""
    graph = ProjectGraph()
    count = 0

    for path in iter_project_files(root_path):
        count += 1
        defs, refs = _extract_file_symbols(path)
        for d in defs:
            graph.definitions.setdefault(d.name, []).append(d)
        graph.references.update(refs)

    graph.files_scanned = count
    return graph


# סמלים שלגיטימי שלא יקראו להם ישירות (frameworks, magic methods, tests, scripts)
_EXEMPT_PREFIXES = ("test_", "Test", "setUp", "tearDown", "cli_", "cmd_", "main", "pytest_")
_EXEMPT_NAMES = {
    "main", "app", "router", "handler", "plugin", "setup",
    "urlpatterns", "INSTALLED_APPS", "MIDDLEWARE",
    # Protocols called by name from outside the project
    "load_ipython_extension", "unload_ipython_extension",
    "setup_module", "teardown_module", "conftest",
    "__getattr__", "__all__",
}


def find_dead_code(root_path: str = ".", graph: ProjectGraph | None = None) -> list[Finding]:
    """מאתר סמלים שמוגדרים אך לא בשימוש באף קובץ בפרויקט."""
    graph = graph or build_project_graph(root_path)
    findings: list[Finding] = []

    # Entry points ב-pyproject נקראים מבחוץ ולא יופיעו כהפניה בקוד.
    reachable = set(graph.references) | entry_point_names(root_path)
    graph = ProjectGraph(
        definitions=graph.definitions, references=reachable, files_scanned=graph.files_scanned
    )

    for name, def_list in graph.definitions.items():
        # סינון חריגים לגיטימיים
        if name.startswith("__") and name.endswith("__"):
            continue
        if name in _EXEMPT_NAMES:
            continue
        if any(name.startswith(p) for p in _EXEMPT_PREFIXES):
            continue

        # בדיקה האם השם מופיע בהפניות
        # אם יש יותר מהגדרה אחת, או שיש הפניה - זה בשימוש
        is_used = name in graph.references

        if not is_used:
            for d in def_list:
                # קבצי בדיקות או סקריפטים ראשיים פטורים
                base = os.path.basename(d.file)
                if base.startswith("test_") or base == "__main__.py" or base == "conftest.py":
                    continue
                # דקורטור = רישום. Flask route, pytest fixture, plugin -
                # אף אחד לא קורא להם בשם, והם בהחלט בשימוש.
                if d.decorated:
                    continue
                # מודול שרץ כסקריפט חושף את השמות שלו למי שמריץ אותו
                if d.in_script:
                    continue

                kind_he = "הפונקציה" if d.kind == "function" else ("המחלקה" if d.kind == "class" else "המשתנה")
                findings.append(
                    Finding(
                        file=d.file,
                        line=d.line,
                        col=d.col,
                        rule="dead-code",
                        message=f"{kind_he} `{d.name}` מוגדרת אך אינה בשימוש בפרויקט",
                        severity="warn",
                        hint="אם הסמל אינו מיועד לייצוא חיצוני, שקול למחוק אותו כדי לפשט את הקוד.",
                    )
                )

    return sorted(findings, key=lambda f: (f.file, f.line))


def build_file_dependency_graph(root_path: str = ".") -> dict[str, Any]:
    """Extracts files, imports between files, and basic health metrics for visualization."""
    files = [f for f in iter_project_files(root_path) if f.endswith(".py")]
    nodes = []
    edges = []
    module_to_file: dict[str, str] = {}
    for f in files:
        rel = os.path.relpath(f, root_path).replace("\\", "/")
        mod_name = os.path.splitext(rel)[0].replace("/", ".")
        module_to_file[mod_name] = rel
        module_to_file[os.path.basename(rel)] = rel

    for f in files:
        rel = os.path.relpath(f, root_path).replace("\\", "/")
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                tree = ast.parse(fh.read(), filename=f)
        except Exception:
            nodes.append({"id": rel, "name": os.path.basename(rel), "status": "error", "imports": []})
            continue

        imported_files: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    tgt = module_to_file.get(alias.name) or module_to_file.get(alias.name.split(".")[0])
                    if tgt and tgt != rel and tgt not in imported_files:
                        imported_files.append(tgt)
                        edges.append({"source": rel, "target": tgt})
            elif isinstance(node, ast.ImportFrom) and node.module:
                tgt = module_to_file.get(node.module) or module_to_file.get(node.module.split(".")[0])
                if tgt and tgt != rel and tgt not in imported_files:
                    imported_files.append(tgt)
                    edges.append({"source": rel, "target": tgt})

        nodes.append({
            "id": rel,
            "name": os.path.basename(rel),
            "status": "clean",
            "imports": imported_files,
        })

    return {"nodes": nodes, "edges": edges}
