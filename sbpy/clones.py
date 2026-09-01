"""איתור קוד משוכפל וכפילויות מבניות (AST Clone Detection).

מזהה פונקציות ובלוקים של קוד כמעט-זהים בפרויקט (גם עם שמות משתנים שונים)
ומציע לאחד אותם לפונקציה משותפת כדי לשמור על עקרון DRY.
"""

from __future__ import annotations

import ast
import hashlib
import os
from dataclasses import dataclass, field

from .index import iter_project_files
from .static.checks import Finding


@dataclass
class FunctionSnippet:
    file: str
    line: int
    end_line: int
    name: str
    statements_count: int
    structure_hash: str


@dataclass
class CloneGroup:
    structure_hash: str
    instances: list[FunctionSnippet] = field(default_factory=list)


class ASTNormalizer(ast.NodeTransformer):
    """מנרמל עץ AST לצורך השוואת מבנה: מוחק שמות משתנים וערכים קבועים."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.Name(id="_var_", ctx=node.ctx)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.Constant(value="_val_")

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.arg(arg="_arg_", annotation=None)


def _compute_function_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """מייצר hash מבני של גוף הפונקציה ללא שמות משתנים ספציפיים."""
    normalizer = ASTNormalizer()
    normalized_body = [normalizer.visit(ast.fix_missing_locations(stmt)) for stmt in node.body]
    # מייצרים dump של המבנה
    dump_parts = [ast.dump(s) for s in normalized_body]
    raw_str = "".join(dump_parts)
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]


def extract_functions(file_path: str, min_statements: int = 3) -> list[FunctionSnippet]:
    """מחלץ את כל הפונקציות מקובץ ומחשב להן חתימה מבנית."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            tree = ast.parse(handle.read(), filename=file_path)
    except (OSError, SyntaxError):
        return []

    snippets: list[FunctionSnippet] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(node.body) >= min_statements and not node.name.startswith("test_"):
                end_lineno = getattr(node, "end_lineno", node.lineno + len(node.body))
                h = _compute_function_hash(node)
                snippets.append(
                    FunctionSnippet(
                        file=file_path,
                        line=node.lineno,
                        end_line=end_lineno,
                        name=node.name,
                        statements_count=len(node.body),
                        structure_hash=h,
                    )
                )
    return snippets


def find_code_clones(root_path: str = ".", min_statements: int = 3) -> list[CloneGroup]:
    """סורק את הפרויקט ומאתר קבוצות של פונקציות משוכפלות."""
    groups: dict[str, list[FunctionSnippet]] = {}

    for file_path in iter_project_files(root_path):
        snippets = extract_functions(file_path, min_statements=min_statements)
        for s in snippets:
            groups.setdefault(s.structure_hash, []).append(s)

    clones: list[CloneGroup] = []
    for h, instances in groups.items():
        if len(instances) >= 2:
            clones.append(CloneGroup(structure_hash=h, instances=instances))

    return clones


def scan_clones(root_path: str = ".", min_statements: int = 3) -> list[Finding]:
    """מפיק ממצאי Finding עבור כל כפילות קוד שנמצאה."""
    clone_groups = find_code_clones(root_path, min_statements=min_statements)
    findings: list[Finding] = []

    for grp in clone_groups:
        first = grp.instances[0]
        for duplicate in grp.instances[1:]:
            first_loc = f"{os.path.basename(first.file)}:{first.line}"
            findings.append(
                Finding(
                    file=duplicate.file,
                    line=duplicate.line,
                    col=0,
                    rule="code-clone",
                    message=f"פונקציה `{duplicate.name}` זהה מבנית לפונקציה `{first.name}` ב-{first_loc}",
                    severity="info",
                    hint="שקול לחלץ לפונקציה משותפת כדי למנוע שכפול קוד (DRY).",
                )
            )

    return findings
