"""בניית ההקשר שנשלח ל-Gemini - חכם במקום ארוך.

חלון של ±8 שורות הוא בזבוז: לרוב הוא מכיל שורות ריקות ולא מכיל את
מה שבאמת צריך - את החתימה של הפונקציה, את ה-imports, ואת ההגדרה של
האובייקט שנכשל. המודול הזה בונה חבילת הקשר באותו תקציב טוקנים בערך,
אבל עם התוכן הנכון.
"""

from __future__ import annotations

import ast
import linecache
from dataclasses import dataclass, field

from .context import FrameContext

MAX_IMPORTS = 12
MAX_DEFINITION_LINES = 25
MAX_TOTAL_LINES = 90


@dataclass
class ContextPack:
    """הקשר מורכב, מסודר לפי חשיבות."""

    imports: list[str] = field(default_factory=list)
    enclosing: list[tuple[int, str]] = field(default_factory=list)
    definitions: list[tuple[str, list[tuple[int, str]]]] = field(default_factory=list)
    failing_line: int = 0
    filename: str = ""

    def render(self) -> str:
        """טקסט מוכן לשליחה, עם מספרי שורות אמיתיים וסימון שורת השגיאה."""
        parts: list[str] = []

        if self.imports:
            parts.append("# imports:")
            parts.extend(self.imports)
            parts.append("")

        if self.enclosing:
            parts.append("# הקוד שנכשל:")
            for number, text in self.enclosing:
                marker = ">>" if number == self.failing_line else "  "
                parts.append(f"{marker} {number:>4} | {text}")

        for name, lines in self.definitions:
            if not lines:
                continue
            parts.append("")
            parts.append(f"# ההגדרה של `{name}`:")
            for number, text in lines:
                parts.append(f"   {number:>4} | {text}")

        return "\n".join(parts[:MAX_TOTAL_LINES])

    def __bool__(self) -> bool:
        return bool(self.enclosing or self.imports or self.definitions)


def _source_lines(path: str) -> list[str]:
    lines = linecache.getlines(path)
    if lines:
        return [line.rstrip("\n") for line in lines]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return []


def _parse(path: str, lines: list[str]) -> ast.AST | None:
    try:
        return ast.parse("\n".join(lines), filename=path)
    except (SyntaxError, ValueError):
        return None


def _import_lines(tree: ast.AST | None, lines: list[str]) -> list[str]:
    if tree is None:
        return []
    found: list[str] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            found.extend(text.strip() for text in lines[start:end] if text.strip())
        if len(found) >= MAX_IMPORTS:
            break
    return found[:MAX_IMPORTS]


def _enclosing_block(tree: ast.AST | None, lines: list[str], lineno: int, radius: int) -> list[tuple[int, str]]:
    """הפונקציה/מחלקה שמכילה את השורה, או חלון סביבה אם אין כזו."""
    best: tuple[int, int] | None = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            if node.lineno <= lineno <= end:
                if best is None or (end - node.lineno) < (best[1] - best[0]):
                    best = (node.lineno, end)

    if best is not None and (best[1] - best[0]) <= MAX_DEFINITION_LINES * 2:
        start, end = best
    else:
        start = max(1, lineno - radius)
        end = min(len(lines), lineno + radius)

    return [(number, lines[number - 1]) for number in range(start, end + 1) if 1 <= number <= len(lines)]


def _names_on_line(lines: list[str], lineno: int) -> list[str]:
    """השמות שמופיעים בשורה שנכשלה."""
    if not (1 <= lineno <= len(lines)):
        return []
    try:
        tree = ast.parse(lines[lineno - 1].strip())
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in found:
            found.append(node.id)
        elif isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value  # type: ignore[assignment]
            if isinstance(root, ast.Name) and root.id not in found:
                found.append(root.id)
    return found


def _definition_of(tree: ast.AST | None, lines: list[str], name: str) -> list[tuple[int, str]]:
    """ההגדרה של שם בקובץ - חתימה בלבד לפונקציות ארוכות."""
    if tree is None:
        return []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            if end - node.lineno > MAX_DEFINITION_LINES:
                end = node.lineno + 2  # חתימה + docstring
            return [
                (number, lines[number - 1])
                for number in range(node.lineno, min(end, len(lines)) + 1)
                if 1 <= number <= len(lines)
            ]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return [(node.lineno, lines[node.lineno - 1])]
    return []


def build(
    ctx: FrameContext | None,
    *,
    radius: int = 6,
    max_definitions: int = 2,
) -> ContextPack:
    """בונה חבילת הקשר לפריים שנכשל."""
    pack = ContextPack()
    if ctx is None or not ctx.filename or ctx.filename.startswith("<"):
        if ctx is not None and ctx.line:
            pack.enclosing = [(ctx.lineno, ctx.line)]
            pack.failing_line = ctx.lineno
        return pack

    lines = _source_lines(ctx.filename)
    if not lines:
        return pack

    tree = _parse(ctx.filename, lines)
    pack.filename = ctx.filename
    pack.failing_line = ctx.lineno
    pack.imports = _import_lines(tree, lines)
    pack.enclosing = _enclosing_block(tree, lines, ctx.lineno, radius)

    shown = {number for number, _ in pack.enclosing}
    for name in _names_on_line(lines, ctx.lineno):
        if len(pack.definitions) >= max_definitions:
            break
        definition = _definition_of(tree, lines, name)
        if definition and not shown.issuperset({number for number, _ in definition}):
            pack.definitions.append((name, definition))
            shown.update(number for number, _ in definition)

    return pack
