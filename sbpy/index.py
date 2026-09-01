"""אינדקס סמלים לכל הפרויקט - מרחיב את השכבה החינמית.

בלי זה, ``NameError`` יכול לחפש רק בקובץ הנוכחי. עם זה:

    NameError: name 'parse_config' is not defined
    -> `parse_config` מוגדר ב-utils.py:12. הוסף: from utils import parse_config

הכל מקומי: ``ast`` בלבד, בלי לייבא את הקוד של המשתמש ובלי רשת.
האינדקס נשמר ב-``~/.sbpy/index/`` ומתעדכן רק לקבצים שהשתנו (לפי mtime).
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Config, get_config

SKIP_DIRECTORIES = {
    "__pycache__", ".git", ".hg", ".svn", ".venv", "venv", "env", ".env",
    "node_modules", ".mypy_cache", ".pytest_cache", ".tox", "build", "dist",
    ".idea", ".vscode", "site-packages", ".eggs", "htmlcov",
}

MAX_FILES = 2000
MAX_FILE_BYTES = 400_000


@dataclass
class Symbol:
    """סמל אחד שהוגדר איפשהו בפרויקט."""

    name: str
    file: str
    line: int
    kind: str = "function"
    """function | class | variable | module"""

    is_public: bool = True

    def module_path(self, root: str) -> str:
        """`utils/text.py` -> `utils.text` (לבניית ה-import)."""
        try:
            relative = os.path.relpath(self.file, root)
        except ValueError:
            relative = os.path.basename(self.file)
        relative = os.path.splitext(relative)[0]
        parts = [part for part in relative.replace("\\", "/").split("/") if part not in (".", "")]
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def import_statement(self, root: str) -> str:
        module = self.module_path(root)
        if not module:
            return f"import {self.name}"
        if self.kind == "module":
            return f"import {module}"
        return f"from {module} import {self.name}"


@dataclass
class ProjectIndex:
    root: str = ""
    symbols: dict[str, list[Symbol]] = field(default_factory=dict)
    files: dict[str, float] = field(default_factory=dict)
    """נתיב -> mtime, כדי לדעת מה צריך לסרוק מחדש."""

    built_at: float = 0.0

    def __len__(self) -> int:
        return len(self.symbols)

    def names(self) -> list[str]:
        return list(self.symbols)

    def lookup(self, name: str) -> list[Symbol]:
        return self.symbols.get(name, [])

    def add(self, symbol: Symbol) -> None:
        self.symbols.setdefault(symbol.name, []).append(symbol)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "built_at": self.built_at,
            "files": self.files,
            "symbols": {
                name: [
                    {"file": s.file, "line": s.line, "kind": s.kind, "public": s.is_public}
                    for s in items
                ]
                for name, items in self.symbols.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectIndex":
        index = cls(root=str(data.get("root", "")), built_at=float(data.get("built_at") or 0))
        files = data.get("files")
        if isinstance(files, dict):
            index.files = {str(k): float(v) for k, v in files.items()}
        raw = data.get("symbols")
        if isinstance(raw, dict):
            for name, items in raw.items():
                for item in items or []:
                    index.add(
                        Symbol(
                            name=str(name),
                            file=str(item.get("file", "")),
                            line=int(item.get("line") or 0),
                            kind=str(item.get("kind", "function")),
                            is_public=bool(item.get("public", True)),
                        )
                    )
        return index


# ----------------------------------------------------------------------
def iter_project_files(root: str, limit: int = MAX_FILES) -> list[str]:
    found: list[str] = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [
            name for name in subdirectories if name not in SKIP_DIRECTORIES and not name.startswith(".")
        ]
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(directory, filename)
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            found.append(path)
            if len(found) >= limit:
                return found
    return found


def symbols_in_file(path: str) -> list[Symbol]:
    """כל הסמלים ברמת המודול בקובץ אחד."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            tree = ast.parse(handle.read(), filename=path)
    except (OSError, SyntaxError, ValueError):
        return []

    found: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(Symbol(node.name, path, node.lineno, "function", not node.name.startswith("_")))
        elif isinstance(node, ast.ClassDef):
            found.append(Symbol(node.name, path, node.lineno, "class", not node.name.startswith("_")))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    found.append(
                        Symbol(target.id, path, target.lineno, "variable", not target.id.startswith("_"))
                    )
    # שם המודול עצמו, כדי לאפשר `import utils`
    module_name = os.path.splitext(os.path.basename(path))[0]
    if module_name != "__init__":
        found.append(Symbol(module_name, path, 1, "module", not module_name.startswith("_")))
    return found


def find_project_root(start: str) -> str:
    """מטפס למעלה עד לסימן של שורש פרויקט."""
    markers = ("pyproject.toml", "setup.py", "setup.cfg", ".git", "requirements.txt")
    current = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start))
    last = None
    while current and current != last:
        for marker in markers:
            if os.path.exists(os.path.join(current, marker)):
                return current
        last, current = current, os.path.dirname(current)
    return os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start))


def _cache_path(root: str, config: Config) -> str:
    digest = hashlib.sha256(os.path.abspath(root).encode("utf-8", "replace")).hexdigest()[:16]
    directory = config.home / "index"
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{digest}.json")


def build(root: str, *, config: Config | None = None, use_cache: bool = True) -> ProjectIndex:
    """בונה (או מעדכן) אינדקס לפרויקט. סורק מחדש רק קבצים שהשתנו."""
    config = config or get_config()
    root = os.path.abspath(root)
    path = _cache_path(root, config)

    previous = ProjectIndex(root=root)
    if use_cache:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    previous = ProjectIndex.from_dict(json.load(handle))
        except (OSError, ValueError):
            previous = ProjectIndex(root=root)

    index = ProjectIndex(root=root, built_at=time.time())
    by_file: dict[str, list[Symbol]] = {}
    for items in previous.symbols.values():
        for symbol in items:
            by_file.setdefault(symbol.file, []).append(symbol)

    for file_path in iter_project_files(root):
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            continue
        cached_mtime = previous.files.get(file_path)
        if use_cache and cached_mtime is not None and abs(cached_mtime - mtime) < 1e-6:
            found = by_file.get(file_path, [])
        else:
            found = symbols_in_file(file_path)
        index.files[file_path] = mtime
        for symbol in found:
            index.add(symbol)

    if use_cache:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(index.to_dict(), handle, ensure_ascii=False)
        except (OSError, TypeError, ValueError):  # sbpy: ignore=silent-except
            pass
    return index


_loaded: dict[str, ProjectIndex] = {}


def for_file(path: str, *, config: Config | None = None) -> ProjectIndex | None:
    """אינדקס הפרויקט שאליו שייך קובץ מסוים, עם מטמון בזיכרון."""
    config = config or get_config()
    if not config.project_index or not path or path.startswith("<"):
        return None
    root = find_project_root(path)
    if root not in _loaded:
        try:
            _loaded[root] = build(root, config=config)
        except Exception:  # pragma: no cover - אינדקס לעולם לא מפיל אבחון
            return None
    return _loaded[root]


def reset() -> None:
    _loaded.clear()


def suggest_import(name: str, path: str, *, config: Config | None = None) -> Symbol | None:
    """מוצא היכן ``name`` מוגדר בפרויקט - להצעת ה-import החסר."""
    index = for_file(path, config=config)
    if index is None:
        return None
    matches = [s for s in index.lookup(name) if os.path.abspath(s.file) != os.path.abspath(path)]
    if not matches:
        return None
    order = {"function": 0, "class": 1, "variable": 2, "module": 3}
    matches.sort(key=lambda s: (not s.is_public, order.get(s.kind, 9), len(s.file)))
    return matches[0]


def close_names(name: str, path: str, *, limit: int = 5, config: Config | None = None) -> list[str]:
    """שמות דומים מכל הפרויקט - למנוע ההתאמה."""
    index = for_file(path, config=config)
    if index is None:
        return []
    from .local import typo

    return typo.close_names(name, index.names(), limit=limit)


def stats(root: str = ".", *, config: Config | None = None) -> dict[str, Any]:
    index = build(root, config=config)
    kinds: dict[str, int] = {}
    for items in index.symbols.values():
        for symbol in items:
            kinds[symbol.kind] = kinds.get(symbol.kind, 0) + 1
    return {
        "root": index.root,
        "files": len(index.files),
        "names": len(index.symbols),
        "by_kind": kinds,
    }
