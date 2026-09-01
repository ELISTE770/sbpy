"""איתור תלויות מעגליות (Circular Imports) ואכיפת גבולות ארכיטקטורה.

סורק את כל עץ ה-Imports בפרויקט, מאתר מעגלי ייבוא שעלולים לגרום לשגיאות טעינה,
ומאפשר להגדיר שכבות ארכיטקטורה כדי למנוע צימוד לא רצוי.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass

from .index import iter_project_files
from .static.checks import Finding


@dataclass
class ImportEdge:
    source_mod: str
    target_mod: str
    file: str
    line: int


def _module_name_from_path(file_path: str, root_path: str) -> str:
    """ממיר נתיב קובץ לשם מודול (למשל src/app/models.py -> src.app.models)."""
    try:
        rel = os.path.relpath(file_path, root_path)
    except ValueError:
        rel = os.path.basename(file_path)
    rel = os.path.splitext(rel)[0]
    parts = [p for p in rel.replace("\\", "/").split("/") if p and p != "."]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def build_import_graph(root_path: str = ".") -> dict[str, list[ImportEdge]]:
    """בונה את גרף הייבוא של הפרויקט: מודול -> רשימת קשתות למודולים מיובאים."""
    graph: dict[str, list[ImportEdge]] = {}
    root = os.path.abspath(root_path)

    for file_path in iter_project_files(root):
        mod_name = _module_name_from_path(file_path, root)
        if not mod_name:
            continue

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                tree = ast.parse(handle.read(), filename=file_path)
        except (OSError, SyntaxError):
            continue

        edges: list[ImportEdge] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append(
                        ImportEdge(
                            source_mod=mod_name,
                            target_mod=alias.name,
                            file=file_path,
                            line=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # טיפול ביבוא יחסי (. ו-..)
                    target = node.module
                    if node.level > 0:
                        parts = mod_name.split(".")
                        parent_parts = parts[: -node.level] if len(parts) >= node.level else []
                        target = ".".join([*parent_parts, node.module])
                    edges.append(
                        ImportEdge(
                            source_mod=mod_name,
                            target_mod=target,
                            file=file_path,
                            line=node.lineno,
                        )
                    )

        graph[mod_name] = edges

    return graph


def find_circular_imports(root_path: str = ".") -> list[list[str]]:
    """מאתר מעגלי תלויות בגרף הייבוא (DFS cycle detection)."""
    graph = build_import_graph(root_path)
    all_cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: list[str] = []

    def dfs(current: str) -> None:
        visited.add(current)
        rec_stack.append(current)

        for edge in graph.get(current, []):
            target = edge.target_mod
            # מתייחסים רק למודולים שנמצאים בתוך הפרויקט
            # בודקים התאמת תחילית (למשל target="pkg.a.b" מתאים ל-"pkg.a")
            matching_internal = None
            for internal in graph:
                if target == internal or target.startswith(internal + "."):
                    matching_internal = internal
                    break

            if not matching_internal:
                continue

            if matching_internal in rec_stack:
                # מצאנו מעגל!
                idx = rec_stack.index(matching_internal)
                cycle = rec_stack[idx:] + [matching_internal]
                # מניעת כפילויות של אותו מעגל
                cycle_set = set(cycle)
                if not any(set(c) == cycle_set for c in all_cycles):
                    all_cycles.append(cycle)
            elif matching_internal not in visited:
                dfs(matching_internal)

        rec_stack.pop()

    for mod in list(graph.keys()):
        if mod not in visited:
            dfs(mod)

    return all_cycles


def check_layer_boundaries(
    root_path: str = ".",
    layers: list[str] | None = None,
) -> list[Finding]:
    """בודק האם יש חריגות משכבות ארכיטקטורה (שכבה נמוכה מייבאת משכבה גבוהה)."""
    if not layers or len(layers) < 2:
        return []

    layer_order = {layer.lower(): idx for idx, layer in enumerate(layers)}
    graph = build_import_graph(root_path)
    findings: list[Finding] = []

    for mod_name, edges in graph.items():
        # מזהים לאיזו שכבה שייך המודל המייבא
        src_layer_idx = None
        for l_name, idx in layer_order.items():
            if l_name in mod_name.lower().split("."):
                src_layer_idx = idx
                break

        if src_layer_idx is None:
            continue

        for edge in edges:
            # מזהים לאיזו שכבה שייך המודל המיובא
            target_layer_idx = None
            for l_name, idx in layer_order.items():
                if l_name in edge.target_mod.lower().split("."):
                    target_layer_idx = idx
                    break

            if target_layer_idx is not None and target_layer_idx > src_layer_idx:
                src_name = layers[src_layer_idx]
                target_name = layers[target_layer_idx]
                findings.append(
                    Finding(
                        file=edge.file,
                        line=edge.line,
                        col=0,
                        rule="layer-violation",
                        message=f"שכבת `{src_name}` מייבאת מ-`{target_name}` - הפרת כיווניות ארכיטקטורה",
                        severity="error",
                        hint=f"שכבות נמוכות לא יכולות לייבא משכבות גבוהות ({' -> '.join(layers)}).",
                    )
                )

    return findings


def scan_architecture(root_path: str = ".", layers: list[str] | None = None) -> list[Finding]:
    """סריקה מלאה של ארכיטקטורת הפרויקט: מעגלי ייבוא והפרות שכבות."""
    findings: list[Finding] = []

    # 1. תלויות מעגליות
    cycles = find_circular_imports(root_path)
    graph = build_import_graph(root_path)

    for cycle in cycles:
        chain_str = " -> ".join(cycle)
        first_mod = cycle[0]
        # מוצאים את הקובץ והשורה של המודל הראשון
        edges = graph.get(first_mod, [])
        file_path = edges[0].file if edges else root_path
        line_no = edges[0].line if edges else 1

        findings.append(
            Finding(
                file=file_path,
                line=line_no,
                col=0,
                rule="circular-import",
                message=f"נמצא ייבוא מעגלי: {chain_str}",
                severity="error",
                hint="שקול להעביר את ההגדרות המשותפות למודול שלישי או להשתמש ב-typing.TYPE_CHECKING.",
            )
        )

    # 2. חוקי שכבות
    if layers:
        findings.extend(check_layer_boundaries(root_path, layers))

    return findings
