"""הפקת דיאגרמות ארכיטקטורה ו-Mermaid חיות מקוד המקור (Living Diagram Generator).

מייצר דיאגרמות מחלקות (Class Diagrams) ותרשימי זרימת מודולים (Module Graphs)
בפורמט Mermaid תקני עבור קובצי Markdown ותיעוד פרויקט.
"""

from __future__ import annotations

import ast
import os

from .arch import build_import_graph
from .index import iter_project_files


def generate_class_diagram(root_path: str = ".") -> str:
    """מפיק דיאגרמת מחלקות בפורמט Mermaid מכל קובצי הפרויקט."""
    lines = ["classDiagram"]
    inheritance_edges: list[str] = []

    for file_path in iter_project_files(root_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                tree = ast.parse(handle.read(), filename=file_path)
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cls_name = node.name
                lines.append(f"    class {cls_name} {{")

                # שדות ומשתנים
                fields: set[str] = set()
                methods: list[str] = []

                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.add(f"+{item.target.id}")
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        arg_names = [a.arg for a in item.args.args if a.arg != "self"]
                        methods.append(f"+{item.name}({', '.join(arg_names)})")

                for f in sorted(fields):
                    lines.append(f"        {f}")
                for m in methods[:8]:  # מגבילים ל-8 מתודות עיקריות לקריאות
                    lines.append(f"        {m}")

                lines.append("    }")

                # יחסי ירושה
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        inheritance_edges.append(f"    {base.id} <|-- {cls_name}")

    if inheritance_edges:
        lines.extend(inheritance_edges)

    return "\n".join(lines)


def generate_flow_diagram(root_path: str = ".") -> str:
    """מפיק תרשים זרימת תלויות בין מודולים בפורמט Mermaid."""
    graph = build_import_graph(root_path)
    lines = ["graph TD"]
    seen_edges: set[tuple[str, str]] = set()

    for mod, edges in graph.items():
        src_id = mod.replace(".", "_")
        for e in edges:
            target = e.target_mod
            # מציגים רק קשרים למודולים שקיימים בפרויקט
            if target in graph or any(target.startswith(k + ".") for k in graph):
                target_id = target.replace(".", "_")
                if (src_id, target_id) not in seen_edges and src_id != target_id:
                    seen_edges.add((src_id, target_id))
                    lines.append(f"    {src_id} --> {target_id}")

    if len(lines) == 1:
        lines.append("    NoDependencies[אין תלויות פנימיות בין מודולים]")

    return "\n".join(lines)


def save_diagram(text: str, output_path: str = "diagram.md") -> str:
    """שומר את הדיאגרמה לקובץ Markdown עטוף בבלוק mermaid."""
    content = f"```mermaid\n{text}\n```\n"
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return os.path.abspath(output_path)
