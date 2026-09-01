"""חילוץ הקשר מהשגיאה: פריים, שורת מקור, ואובייקטים - בלי להריץ קוד של המשתמש."""

from __future__ import annotations

import ast
import builtins
import linecache
import os
import sys
import sysconfig
import textwrap
from dataclasses import dataclass, field
from types import FrameType, TracebackType
from typing import Any

_MISSING = object()

_STDLIB_PATHS = tuple(
    os.path.normcase(os.path.abspath(path))
    for path in {
        sysconfig.get_paths().get("stdlib", ""),
        sysconfig.get_paths().get("platstdlib", ""),
    }
    if path
)

_SBPY_ROOT = os.path.normcase(os.path.abspath(os.path.dirname(__file__)))


def is_library_file(filename: str) -> bool:
    """האם הקובץ שייך לספרייה/סטנדרט ולא לקוד של המשתמש."""
    if not filename or filename.startswith("<"):
        return True
    path = os.path.normcase(os.path.abspath(filename))
    if "site-packages" in path or "dist-packages" in path:
        return True
    if path.startswith(_SBPY_ROOT):
        return True
    return any(path.startswith(root) for root in _STDLIB_PATHS)


@dataclass
class FrameContext:
    """כל מה שידוע על פריים אחד בשרשרת השגיאה."""

    filename: str = ""
    lineno: int = 0
    function: str = ""
    line: str = ""
    frame: FrameType | None = field(default=None, repr=False)
    is_library: bool = False

    @property
    def locals(self) -> dict[str, Any]:
        return dict(self.frame.f_locals) if self.frame is not None else {}

    @property
    def globals(self) -> dict[str, Any]:
        return dict(self.frame.f_globals) if self.frame is not None else {}

    def where(self) -> str:
        base = os.path.basename(self.filename) or "<unknown>"
        if self.function and self.function != "<module>":
            return f"{base}:{self.lineno} · {self.function}()"
        return f"{base}:{self.lineno}"

    def source_window(self, radius: int = 4) -> list[tuple[int, str]]:
        """שורות מסביב לשורת השגיאה, כזוגות (מספר שורה, טקסט)."""
        if not self.filename or self.lineno <= 0:
            return []
        start = max(1, self.lineno - radius)
        end = self.lineno + radius
        out: list[tuple[int, str]] = []
        for number in range(start, end + 1):
            text = linecache.getline(self.filename, number)
            if not text:
                continue
            out.append((number, text.rstrip("\n")))
        return out

    def statement(self) -> str:
        """המשפט המלא שבו קרתה השגיאה (מאחד שורות המשך)."""
        if not self.filename or self.lineno <= 0:
            return self.line
        lines = []
        for number in range(self.lineno, self.lineno + 12):
            text = linecache.getline(self.filename, number)
            if not text:
                break
            lines.append(text.rstrip("\n"))
            candidate = textwrap.dedent("\n".join(lines))
            try:
                ast.parse(candidate)
            except SyntaxError:
                continue
            return candidate
        return self.line

    def parse_statement(self) -> ast.AST | None:
        source = self.statement() or self.line
        if not source.strip():
            return None
        try:
            return ast.parse(textwrap.dedent(source))
        except SyntaxError:
            return None

    # ------------------------------------------------------------------
    def lookup(self, name: str, default: Any = _MISSING) -> Any:
        """חיפוש שם בפריים - מקומי, גלובלי, ואז builtins."""
        if self.frame is None:
            return None if default is _MISSING else default
        if name in self.frame.f_locals:
            return self.frame.f_locals[name]
        if name in self.frame.f_globals:
            return self.frame.f_globals[name]
        if hasattr(builtins, name):
            return getattr(builtins, name)
        return None if default is _MISSING else default

    def has_name(self, name: str) -> bool:
        return self.lookup(name, _MISSING) is not _MISSING

    def scope_names(self) -> list[str]:
        """השמות שהמשתמש עצמו הגדיר - מקומיים וגלובליים, בלי builtins."""
        names: list[str] = []
        if self.frame is not None:
            names.extend(self.frame.f_locals)
            names.extend(self.frame.f_globals)
        return names

    def visible_names(self) -> list[str]:
        """כל השמות שנראים מהפריים הזה, כולל builtins."""
        return self.scope_names() + dir(builtins)

    def resolve(self, node: ast.AST | None, depth: int = 0) -> Any:
        """הערכה בטוחה של ביטוי פשוט: שם, קבוע, או שרשרת תכונות.

        לעולם לא קורא לפונקציות ולא מבצע ``[]`` - רק חיפוש שמות.
        """
        if node is None or depth > 3 or self.frame is None:
            return _MISSING
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.lookup(node.id, _MISSING)
        if isinstance(node, ast.Attribute):
            owner = self.resolve(node.value, depth + 1)
            if owner is _MISSING:
                return _MISSING
            try:
                return getattr(owner, node.attr)
            except Exception:
                return _MISSING
        return _MISSING


def _iter_tracebacks(tb: TracebackType | None):
    while tb is not None:
        yield tb
        tb = tb.tb_next


def build_contexts(tb: TracebackType | None) -> tuple[FrameContext | None, FrameContext | None]:
    """מחזיר (הפריים העמוק ביותר, הפריים העמוק ביותר בקוד של המשתמש)."""
    deepest: FrameContext | None = None
    user: FrameContext | None = None

    for entry in _iter_tracebacks(tb):
        frame = entry.tb_frame
        filename = frame.f_code.co_filename
        lineno = entry.tb_lineno
        context = FrameContext(
            filename=filename,
            lineno=lineno,
            function=frame.f_code.co_name,
            line=linecache.getline(filename, lineno).strip(),
            frame=frame,
            is_library=is_library_file(filename),
        )
        deepest = context
        if not context.is_library:
            user = context

    return deepest, user


def module_names(filename: str) -> list[str]:
    """כל השמות שמוגדרים ברמת המודול בקובץ (לפי ניתוח סטטי)."""
    try:
        with open(filename, "r", encoding="utf-8", errors="replace") as handle:
            tree = ast.parse(handle.read(), filename=filename)
    except (OSError, SyntaxError, ValueError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.append(node.id)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.alias):
            names.append((node.asname or node.name).split(".")[0])
    return names


def definition_line(filename: str, name: str) -> int | None:
    """באיזו שורה מוגדר שם מסוים בקובץ (אם בכלל)."""
    try:
        with open(filename, "r", encoding="utf-8", errors="replace") as handle:
            tree = ast.parse(handle.read(), filename=filename)
    except (OSError, SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node.lineno
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name:
            return node.lineno
    return None


def find_nodes(tree: ast.AST | None, node_type: type) -> list[ast.AST]:
    if tree is None:
        return []
    return [node for node in ast.walk(tree) if isinstance(node, node_type)]


def find_attribute_owner(tree: ast.AST | None, attr: str) -> ast.expr | None:
    """מוצא את הביטוי שעליו מבוצעת הגישה ``.attr``."""
    for node in find_nodes(tree, ast.Attribute):
        if node.attr == attr:  # type: ignore[attr-defined]
            return node.value  # type: ignore[attr-defined]
    return None


def find_subscript_owner(tree: ast.AST | None, key: Any = _MISSING) -> ast.expr | None:
    """מוצא את האובייקט שעליו בוצע ``[...]`` (אפשר לסנן לפי מפתח קבוע)."""
    for node in find_nodes(tree, ast.Subscript):
        slice_node = node.slice  # type: ignore[attr-defined]
        if key is _MISSING:
            return node.value  # type: ignore[attr-defined]
        if isinstance(slice_node, ast.Constant) and slice_node.value == key:
            return node.value  # type: ignore[attr-defined]
    subscripts = find_nodes(tree, ast.Subscript)
    return subscripts[0].value if subscripts else None  # type: ignore[attr-defined]


def find_call_with_keyword(tree: ast.AST | None, keyword: str) -> ast.Call | None:
    for node in find_nodes(tree, ast.Call):
        for kw in node.keywords:  # type: ignore[attr-defined]
            if kw.arg == keyword:
                return node  # type: ignore[return-value]
    return None


def call_name(node: ast.Call | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node.func)
    except Exception:  # pragma: no cover
        return ""


def python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
