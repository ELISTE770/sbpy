"""שכבה 1: תיקונים מקומיים - חינם, מיידיים, בלי רשת.

כל פונקציה כאן מקבלת ``ErrorInfo`` ומחזירה רשימת ``Diagnosis``.
אם אחת מהן מחזירה ביטחון גבוה, הסולם עוצר כאן ולא פונה ל-Gemini.
"""

from __future__ import annotations

import ast
import builtins
import inspect

import os
import re
import sys
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Callable, Mapping, Sequence

from ..context import (
    FrameContext,
    call_name,
    definition_line,
    find_attribute_owner,
    find_call_with_keyword,
    find_subscript_owner,
    module_names,
)
from ..i18n import t
from ..results import Diagnosis
from . import typo

_MISSING = object()

# ----------------------------------------------------------------------
# מיפוי שם-מודול -> שם-חבילה ב-pip (הפער הזה מבלבל כמעט כל מתחיל)
PACKAGE_ALIASES: dict[str, str] = {
    "cv2": "opencv-python",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "serial": "pyserial",
    "Crypto": "pycryptodome",
    "OpenSSL": "pyOpenSSL",
    "fitz": "PyMuPDF",
    "genai": "google-genai",
    "google.genai": "google-genai",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "win32com": "pywin32",
    "win32api": "pywin32",
    "attr": "attrs",
    "dateutil": "python-dateutil",
    "jwt": "PyJWT",
    "magic": "python-magic",
    "psycopg2": "psycopg2-binary",
    "MySQLdb": "mysqlclient",
    "telebot": "pyTelegramBotAPI",
    "discord": "discord.py",
    "usb": "pyusb",
    "gi": "PyGObject",
    "pkg_resources": "setuptools",
    "zoneinfo": "tzdata",
    "requests_html": "requests-html",
    "speech_recognition": "SpeechRecognition",
    "pydub": "pydub",
    "fuzzywuzzy": "fuzzywuzzy",
    "Levenshtein": "python-Levenshtein",
    "nacl": "PyNaCl",
    "ruamel": "ruamel.yaml",
    "tkinterdnd2": "tkinterdnd2",
    "customtkinter": "customtkinter",
}

# מודולים סטנדרטיים שנשכח לייבא אותם הכי הרבה
COMMON_MODULES = (
    "os", "sys", "re", "json", "math", "time", "random", "datetime", "pathlib",
    "collections", "itertools", "functools", "subprocess", "shutil", "typing",
    "logging", "threading", "asyncio", "sqlite3", "csv", "glob", "hashlib",
    "base64", "socket", "struct", "traceback", "textwrap", "argparse", "copy",
    "string", "statistics", "pickle", "tempfile", "uuid", "warnings", "unittest",
)


@dataclass
class ErrorInfo:
    """כל מה שהשכבה המקומית צריכה כדי לאבחן."""

    exc: BaseException
    exc_type: type[BaseException]
    tb: TracebackType | None = None
    deep: FrameContext | None = None
    user: FrameContext | None = None
    lang: str = "he"
    message: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ctx(self) -> FrameContext | None:
        """הפריים המעניין ביותר לאבחון - קוד המשתמש אם יש, אחרת העמוק ביותר."""
        return self.user or self.deep

    def tr(self, key: str, /, **kwargs: object) -> str:
        return t(key, self.lang, **kwargs)


FixerFn = Callable[[ErrorInfo], list[Diagnosis]]
_REGISTRY: list[tuple[tuple[type, ...], FixerFn]] = []


def fixer(*exc_types: type) -> Callable[[FixerFn], FixerFn]:
    def decorator(func: FixerFn) -> FixerFn:
        _REGISTRY.append((exc_types, func))
        return func

    return decorator


def _diag(
    info: ErrorInfo,
    rule: str,
    title_key: str,
    *,
    confidence: float,
    suggestion_key: str = "",
    detail_key: str = "",
    title_args: dict[str, object] | None = None,
    suggestion_args: dict[str, object] | None = None,
    detail_args: dict[str, object] | None = None,
    patch: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Diagnosis:
    return Diagnosis(
        title=info.tr(title_key, **(title_args or {})),
        detail=info.tr(detail_key, **(detail_args or {})) if detail_key else "",
        suggestion=info.tr(suggestion_key, **(suggestion_args or {})) if suggestion_key else "",
        confidence=round(confidence, 4),
        source="local",
        rule=rule,
        patch=patch,
        meta=meta or {},
    )


def _quoted(message: str) -> list[str]:
    """כל המחרוזות בין גרשיים בהודעת השגיאה."""
    return re.findall(r"['\"]([^'\"]+)['\"]", message)


# ======================================================================
# NameError
# ======================================================================
@fixer(NameError)
def fix_name_error(info: ErrorInfo) -> list[Diagnosis]:
    if isinstance(info.exc, UnboundLocalError):
        return []
    match = re.search(r"name ['\"]([^'\"]+)['\"] is not defined", info.message)
    if not match:
        return []
    name = match.group(1)
    ctx = info.ctx
    out: list[Diagnosis] = []

    # 0. זיהוי טעות מקלדת עברית (למשל 'טפנד' / 'דנפט' -> 'sbpy', 'פרורא' -> 'print', 'ישקשך' -> 'heal')
    if any("\u0590" <= c <= "\u05fe" for c in name):
        from ..keyboard import transliterate_keyboard
        from ..shortcuts import SHORTCUTS

        trans = transliterate_keyboard(name).lower()
        rev_trans = transliterate_keyboard(name[::-1]).lower()

        known_targets: dict[str, str] = {
            "sbpy": "sbpy",
            "setup": "setup",
            "models": "models",
            "fullinfo": "fullinfo",
            "undo": "undo",
            "commit": "commit",
            "heal": "heal",
            "agent": "agent",
            "find": "find",
            "gen": "gen",
            "ui": "ui",
            "true": "True",
            "false": "False",
            "none": "None",
            "print": "print",
            "len": "len",
            "range": "range",
            "exit": "exit()",
            "quit": "quit()",
            "help": "help()",
        }
        for code in SHORTCUTS:
            known_targets[code.lower()] = f"/{code}"

        all_scope: list[str] = []
        if ctx is not None:
            all_scope.extend(ctx.scope_names())
            if ctx.filename:
                all_scope.extend(module_names(ctx.filename))
        all_scope.extend(dir(builtins))
        all_scope.extend(COMMON_MODULES)

        for s in all_scope:
            known_targets[s.lower()] = s

        target = None
        if trans in known_targets:
            target = known_targets[trans]
        elif rev_trans in known_targets:
            target = known_targets[rev_trans]
        else:
            candidates_list = list(known_targets.values())
            m1, s1 = typo.best_match(trans, candidates_list, cutoff=0.75)
            m2, s2 = typo.best_match(rev_trans, candidates_list, cutoff=0.75)
            if m1 and s1 >= 0.75:
                target = m1
            elif m2 and s2 >= 0.75:
                target = m2
            else:
                target = trans if trans else rev_trans

        if target:
            is_he = info.lang == "he"
            title = (
                f"טעות במקלדת עברית: השם '{name}' הוקלד בעברית"
                if is_he
                else f"Hebrew keyboard layout typo: '{name}' was typed in Hebrew"
            )
            suggestion = (
                f"האם התכוונת ל-'{target}'? (תרגום מקלדת עברית->אנגלית: '{name}' -> '{target}')"
                if is_he
                else f"Did you mean '{target}'? (transliterated from Hebrew keyboard layout: '{name}' -> '{target}')"
            )
            detail = (
                f"המקלדת הייתה על עברית. תרגום האותיות: '{name}' הופך ל-'{target}'."
                if is_he
                else f"Your keyboard was set to Hebrew layout. '{name}' maps to '{target}' on standard QWERTY."
            )
            return [
                Diagnosis(
                    title=title,
                    detail=detail,
                    suggestion=suggestion,
                    confidence=0.98,
                    source="local",
                    rule="name.hebrew-keyboard",
                    patch=target,
                    meta={"kind": "hebrew_keyboard_typo", "bad": name, "good": target},
                )
            ]

    # 1. מודול מוכר שנשכח לייבא
    if name in COMMON_MODULES or name in PACKAGE_ALIASES:
        return [
            _diag(
                info,
                "name.missing-import",
                "name.import.title",
                suggestion_key="name.import.suggestion",
                title_args={"name": name},
                suggestion_args={"name": name},
                confidence=0.93,
                patch=f"import {name}",
                meta={"kind": "missing_import", "module": name},
            )
        ]

    # 2. טעות כתיב. שמות שהמשתמש הגדיר נבדקים ראשונים ובסף נמוך; ל-builtins
    #    דורשים סף גבוה יותר, אחרת כל שם לא מוכר "מתאים" לאיזה builtin אקראי.
    candidates: list[str] = []
    if ctx is not None:
        candidates.extend(ctx.scope_names())
        if ctx.filename:
            candidates.extend(module_names(ctx.filename))
    best, score = typo.best_match(name, candidates, cutoff=0.62)
    if not best and ctx is not None:
        best, score = typo.best_match(name, dir(builtins), cutoff=0.78)
    candidates.extend(dir(builtins))

    if best:
        out.append(
            _diag(
                info,
                "name.typo",
                "name.typo.title",
                suggestion_key="name.typo.suggestion",
                title_args={"name": name},
                suggestion_args={"best": best},
                confidence=min(0.96, score),
                patch=None,
                meta={"kind": "name_typo", "bad": name, "good": best},
            )
        )

    # 3. השם מוגדר במקום אחר בפרויקט - חסר רק ה-import
    if ctx is not None and ctx.filename and (not best or score < 0.92):
        from .. import index as project_index

        symbol = project_index.suggest_import(name, ctx.filename)
        if symbol is not None:
            statement = symbol.import_statement(project_index.find_project_root(ctx.filename))
            location = f"{os.path.basename(symbol.file)}:{symbol.line}"
            out.insert(
                0,
                _diag(
                    info,
                    "name.project-import",
                    "name.project.title",
                    suggestion_key="name.project.suggestion",
                    detail_key="name.project.detail",
                    title_args={"name": name},
                    suggestion_args={"statement": statement},
                    detail_args={"location": location},
                    confidence=0.91,
                    patch=statement,
                    meta={
                        "kind": "project_import",
                        "name": name,
                        "statement": statement,
                        "file": symbol.file,
                        "line": symbol.line,
                    },
                ),
            )

    # 4. שם שנראה כמו מודול שנכתב לא נכון (maht -> math)
    if not best or score < 0.9:
        modules = list(COMMON_MODULES) + list(PACKAGE_ALIASES) + _stdlib_module_names()
        module_best, module_score = typo.best_match(name, modules, cutoff=0.75)
        if module_best and module_score > score:
            out.insert(
                0,
                _diag(
                    info,
                    "name.module-typo",
                    "name.module.title",
                    suggestion_key="name.module.suggestion",
                    title_args={"name": name},
                    suggestion_args={"best": module_best},
                    confidence=min(0.93, module_score),
                    patch=f"import {module_best}",
                    meta={"kind": "module_name_typo", "bad": name, "good": module_best},
                ),
            )

    # 5. השם מוגדר בקובץ אך מתחת לשורה הנוכחית
    if ctx is not None and ctx.filename and not best:
        line = definition_line(ctx.filename, name)
        if line and line > ctx.lineno:
            out.append(
                _diag(
                    info,
                    "name.defined-later",
                    "name.later.title",
                    suggestion_key="name.later.suggestion",
                    title_args={"name": name},
                    suggestion_args={"line": line},
                    confidence=0.88,
                    meta={"kind": "defined_later", "line": line},
                )
            )

    if not out:
        others = typo.close_names(name, candidates, limit=5)
        out.append(
            _diag(
                info,
                "name.unknown",
                "name.generic.title",
                detail_key="name.generic.detail",
                title_args={"name": name},
                confidence=0.35,
                meta={"kind": "unknown_name", "similar": others},
            )
        )
    return out


@fixer(UnboundLocalError)
def fix_unbound_local(info: ErrorInfo) -> list[Diagnosis]:
    match = re.search(r"['\"]([^'\"]+)['\"]", info.message)
    if not match:
        return []
    name = match.group(1)
    return [
        _diag(
            info,
            "name.unbound-local",
            "unbound.title",
            suggestion_key="unbound.suggestion",
            title_args={"name": name},
            suggestion_args={"name": name},
            confidence=0.90,
            meta={"kind": "unbound_local", "name": name},
        )
    ]


# ======================================================================
# AttributeError
# ======================================================================
@fixer(AttributeError)
def fix_attribute_error(info: ErrorInfo) -> list[Diagnosis]:
    attr = getattr(info.exc, "name", None)
    owner_name = ""
    if not attr:
        match = re.search(r"has no attribute ['\"]([^'\"]+)['\"]", info.message)
        attr = match.group(1) if match else ""
    if not attr:
        return []

    match_owner = re.search(r"^(?:'|\")?([\w.]+)(?:'|\")? object has no attribute", info.message)
    if match_owner:
        owner_name = match_owner.group(1)
    else:
        match_mod = re.search(r"^module ['\"]([^'\"]+)['\"] has no attribute", info.message)
        if match_mod:
            owner_name = match_mod.group(1)

    ctx = info.ctx
    obj = _MISSING
    display_owner = owner_name or "?"

    if ctx is not None:
        tree = ctx.parse_statement()
        node = find_attribute_owner(tree, attr)
        if node is not None:
            try:
                display_owner = ast.unparse(node)
            except Exception:  # sbpy: ignore=silent-except
                pass
            obj = ctx.resolve(node)
        if obj is _MISSING:
            candidate = getattr(info.exc, "obj", _MISSING)
            if candidate is not _MISSING:
                obj = candidate

    # None הוא מקרה נפרד ונפוץ מאוד
    if obj is None or owner_name == "NoneType":
        return [
            _diag(
                info,
                "attr.none",
                "attr.none.title",
                suggestion_key="attr.none.suggestion",
                suggestion_args={"owner": display_owner},
                confidence=0.87,
                meta={"kind": "none_attribute", "attr": attr},
            )
        ]

    candidates: list[str] = []
    if obj is not _MISSING:
        try:
            candidates = [name for name in dir(obj) if not name.startswith("__")]
        except Exception:
            candidates = []

    best, score = typo.best_match(attr, candidates, cutoff=0.62)
    if best:
        return [
            _diag(
                info,
                "attr.typo",
                "attr.typo.title",
                suggestion_key="attr.typo.suggestion",
                detail_key="attr.candidates.detail" if len(candidates) > 1 else "",
                title_args={"owner": display_owner, "attr": attr},
                suggestion_args={"best": best},
                detail_args={"items": typo.preview(typo.close_names(attr, candidates, 6))},
                confidence=min(0.95, score),
                meta={"kind": "attr_typo", "bad": attr, "good": best, "owner": display_owner},
            )
        ]

    similar = typo.close_names(attr, candidates, limit=6)
    return [
        _diag(
            info,
            "attr.unknown",
            "attr.generic.title",
            detail_key="attr.candidates.detail" if similar else "",
            title_args={"owner": owner_name or display_owner, "attr": attr},
            detail_args={"items": typo.preview(similar)},
            confidence=0.45 if similar else 0.30,
            meta={"kind": "unknown_attribute", "attr": attr, "similar": similar},
        )
    ]


# ======================================================================
# ImportError / ModuleNotFoundError
# ======================================================================
def _stdlib_module_names() -> list[str]:
    names = set(getattr(sys, "stdlib_module_names", ()))
    names.update(sys.builtin_module_names)
    names.update(COMMON_MODULES)
    return sorted(name for name in names if not name.startswith("_"))


def _installed_module_names() -> list[str]:
    names: set[str] = set(sys.modules)
    try:
        import pkgutil

        names.update(module.name for module in pkgutil.iter_modules())
    except Exception:  # pragma: no cover  # sbpy: ignore=silent-except
        pass
    return sorted(name for name in names if name and not name.startswith("_"))


@fixer(ModuleNotFoundError)
def fix_module_not_found(info: ErrorInfo) -> list[Diagnosis]:
    module = getattr(info.exc, "name", None) or ""
    if not module:
        match = re.search(r"No module named ['\"]([^'\"]+)['\"]", info.message)
        module = match.group(1) if match else ""
    if not module:
        return []

    root = module.split(".")[0]
    out: list[Diagnosis] = []

    # קובץ מקומי בשם זהה שמסתיר את החבילה האמיתית
    ctx = info.ctx
    if ctx is not None and ctx.filename:
        sibling = os.path.join(os.path.dirname(os.path.abspath(ctx.filename)), f"{root}.py")
        if os.path.exists(sibling) and os.path.abspath(sibling) != os.path.abspath(ctx.filename):
            out.append(
                _diag(
                    info,
                    "import.shadowed",
                    "import.self.title",
                    suggestion_key="import.self.suggestion",
                    title_args={"module": root},
                    suggestion_args={"path": sibling},
                    confidence=0.85,
                    meta={"kind": "shadowed_module", "path": sibling},
                )
            )

    # טעות כתיב במודול סטנדרטי או מותקן
    known = _stdlib_module_names() + _installed_module_names()
    best, score = typo.best_match(root, known, cutoff=0.70)
    if best:
        out.append(
            _diag(
                info,
                "import.typo",
                "import.typo.title",
                suggestion_key="import.typo.suggestion",
                title_args={"module": module},
                suggestion_args={"best": best},
                confidence=min(0.94, score),
                meta={"kind": "module_typo", "bad": root, "good": best},
            )
        )

    from .. import learn

    package = PACKAGE_ALIASES.get(root) or learn.package_for(root) or root
    known_alias = root in PACKAGE_ALIASES or learn.package_for(root) is not None
    out.append(
        _diag(
            info,
            "import.not-installed",
            "import.pip.title",
            suggestion_key="import.pip.suggestion",
            title_args={"module": module},
            suggestion_args={"package": package},
            confidence=0.86 if known_alias else 0.78,
            patch=f"pip install {package}",
            meta={"kind": "missing_package", "module": root, "package": package},
        )
    )
    return out


@fixer(ImportError)
def fix_import_name(info: ErrorInfo) -> list[Diagnosis]:
    if isinstance(info.exc, ModuleNotFoundError):
        return []
    match = re.search(r"cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]", info.message)
    if not match:
        return []
    name, module = match.group(1), match.group(2)

    candidates: list[str] = []
    imported = sys.modules.get(module)
    if imported is not None:
        try:
            candidates = [item for item in dir(imported) if not item.startswith("_")]
        except Exception:
            candidates = []

    best, score = typo.best_match(name, candidates, cutoff=0.62)
    if best:
        return [
            _diag(
                info,
                "import.name-typo",
                "import.name.title",
                suggestion_key="import.typo.suggestion",
                title_args={"name": name, "module": module},
                suggestion_args={"best": best},
                confidence=min(0.93, score),
                meta={"kind": "import_name_typo", "bad": name, "good": best},
            )
        ]
    return [
        _diag(
            info,
            "import.name-missing",
            "import.name.title",
            title_args={"name": name, "module": module},
            confidence=0.50,
            meta={"kind": "import_name_missing"},
        )
    ]


# ======================================================================
# KeyError
# ======================================================================
@fixer(KeyError)
def fix_key_error(info: ErrorInfo) -> list[Diagnosis]:
    key = info.exc.args[0] if info.exc.args else None
    if key is None:
        return []

    ctx = info.ctx
    mapping: Any = _MISSING
    if ctx is not None:
        tree = ctx.parse_statement()
        node = find_subscript_owner(tree, key)
        if node is not None:
            mapping = ctx.resolve(node)

    keys: list[str] = []
    if isinstance(mapping, Mapping):
        try:
            keys = [k for k in mapping.keys() if isinstance(k, str)]
        except Exception:
            keys = []
    elif hasattr(mapping, "columns") and isinstance(key, str):
        try:
            cols = [str(c) for c in mapping.columns]
            best_col, col_score = typo.best_match(key, cols, cutoff=0.6)
            if best_col:
                return [
                    _diag(
                        info,
                        "pandas.column_typo",
                        "pandas.column_typo.title",
                        suggestion_key="pandas.column_typo.suggestion",
                        title_args={"column": key},
                        suggestion_args={"best": best_col, "available": typo.preview(cols)},
                        confidence=min(0.95, col_score),
                        meta={"kind": "pandas_column_typo", "bad": key, "good": best_col},
                    )
                ]
        except Exception:  # sbpy: ignore=silent-except
            pass

    if isinstance(key, str) and keys:
        # התאמה שנבדלת רק באותיות גדולות/קטנות
        lowered = {k.lower(): k for k in keys}
        if key.lower() in lowered and lowered[key.lower()] != key:
            return [
                _diag(
                    info,
                    "key.case",
                    "key.typo.title",
                    suggestion_key="key.casing.suggestion",
                    detail_key="key.keys.detail",
                    title_args={"key": key},
                    suggestion_args={"best": lowered[key.lower()]},
                    detail_args={"items": typo.preview(keys)},
                    confidence=0.95,
                    meta={"kind": "key_case", "bad": key, "good": lowered[key.lower()]},
                )
            ]
        best, score = typo.best_match(key, keys, cutoff=0.62)
        if best:
            return [
                _diag(
                    info,
                    "key.typo",
                    "key.typo.title",
                    suggestion_key="key.typo.suggestion",
                    detail_key="key.keys.detail",
                    title_args={"key": key},
                    suggestion_args={"best": best},
                    detail_args={"items": typo.preview(keys)},
                    confidence=min(0.94, score),
                    meta={"kind": "key_typo", "bad": key, "good": best},
                )
            ]

    detail_args = {"items": typo.preview(keys)} if keys else {}
    return [
        _diag(
            info,
            "key.missing",
            "key.generic.title",
            suggestion_key="key.generic.suggestion",
            detail_key="key.keys.detail" if keys else "",
            title_args={"key": key},
            detail_args=detail_args,
            confidence=0.62 if keys else 0.45,
            meta={"kind": "missing_key", "key": str(key), "keys": keys[:20]},
        )
    ]


# ======================================================================
# IndexError
# ======================================================================
@fixer(IndexError)
def fix_index_error(info: ErrorInfo) -> list[Diagnosis]:
    ctx = info.ctx
    owner_display = "הרצף" if info.lang == "he" else "the sequence"
    length: int | None = None

    if ctx is not None:
        tree = ctx.parse_statement()
        node = find_subscript_owner(tree)
        if node is not None:
            try:
                owner_display = ast.unparse(node)
            except Exception:  # sbpy: ignore=silent-except
                pass
            value = ctx.resolve(node)
            if value is not _MISSING and isinstance(value, Sequence):
                try:
                    length = len(value)
                except Exception:
                    length = None

    if length == 0:
        return [
            _diag(
                info,
                "index.empty",
                "index.title",
                detail_key="index.empty.detail",
                suggestion_key="index.suggestion",
                detail_args={"owner": owner_display},
                confidence=0.90,
                meta={"kind": "empty_sequence", "owner": owner_display},
            )
        ]
    if length:
        return [
            _diag(
                info,
                "index.out-of-range",
                "index.title",
                detail_key="index.detail",
                suggestion_key="index.suggestion",
                detail_args={"owner": owner_display, "length": length, "last": length - 1},
                confidence=0.88,
                meta={"kind": "index_range", "length": length},
            )
        ]
    return [
        _diag(
            info,
            "index.generic",
            "index.title",
            suggestion_key="index.suggestion",
            confidence=0.55,
            meta={"kind": "index_generic"},
        )
    ]


# ======================================================================
# TypeError
# ======================================================================
_CONVERSION_HINTS = {
    ("str", "int"): "str(x) + str(y)",
    ("int", "str"): "str(x) + str(y)",
    ("str", "float"): "str(x) + str(y)",
    ("float", "str"): "str(x) + str(y)",
    ("list", "str"): "list + [item]",
    ("int", "NoneType"): "x + (y or 0)",
    ("NoneType", "int"): "(x or 0) + y",
}


@fixer(TypeError)
def fix_type_error(info: ErrorInfo) -> list[Diagnosis]:
    message = info.message
    ctx = info.ctx

    # --- פרמטר לא קיים ---
    match = re.search(r"([\w.]+)\(\) got an unexpected keyword argument ['\"]([^'\"]+)['\"]", message)
    if match:
        func_name, kwarg = match.group(1), match.group(2)
        params: list[str] = []
        target = _MISSING
        if ctx is not None:
            tree = ctx.parse_statement()
            call = find_call_with_keyword(tree, kwarg)
            if call is not None:
                func_name = call_name(call) or func_name
                target = ctx.resolve(call.func)
        if target is _MISSING and ctx is not None:
            target = ctx.lookup(func_name.split(".")[-1], _MISSING)
        if target is not _MISSING and target is not None:
            try:
                params = [
                    name
                    for name, param in inspect.signature(target).parameters.items()
                    if param.kind
                    not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                    and name != "self"
                ]
            except (TypeError, ValueError):
                params = []

        best, score = typo.best_match(kwarg, params, cutoff=0.58)
        if best:
            return [
                _diag(
                    info,
                    "type.kwarg-typo",
                    "type.kwarg.title",
                    suggestion_key="type.kwarg.suggestion",
                    detail_key="type.params.detail" if params else "",
                    title_args={"kwarg": kwarg, "func": func_name},
                    suggestion_args={"best": best},
                    detail_args={"items": typo.preview(params, 12)},
                    confidence=min(0.95, score),
                    meta={
                        "kind": "kwarg_typo",
                        "bad": kwarg,
                        "good": best,
                        "func": func_name,
                        "retryable": True,
                    },
                )
            ]
        return [
            _diag(
                info,
                "type.kwarg-unknown",
                "type.kwarg.title",
                detail_key="type.params.detail" if params else "",
                title_args={"kwarg": kwarg, "func": func_name},
                detail_args={"items": typo.preview(params, 12)},
                confidence=0.60 if params else 0.40,
                meta={"kind": "kwarg_unknown", "bad": kwarg, "params": params},
            )
        ]

    # --- ארגומנטים חסרים ---
    match = re.search(
        r"([\w.]+)\(\) missing \d+ required (?:positional|keyword-only) arguments?: (.+)",
        message,
    )
    if match:
        func_name, raw = match.group(1), match.group(2)
        missing = _quoted(raw)
        signature = ""
        if ctx is not None:
            target = ctx.lookup(func_name.split(".")[-1], _MISSING)
            if target is not _MISSING and target is not None:
                try:
                    signature = f"{func_name}{inspect.signature(target)}"
                except (TypeError, ValueError):
                    signature = ""
        return [
            _diag(
                info,
                "type.missing-args",
                "type.missing.title",
                detail_key="type.missing.detail" if signature else "",
                title_args={"func": func_name, "items": ", ".join(missing)},
                detail_args={"signature": signature},
                confidence=0.82,
                meta={"kind": "missing_args", "missing": missing, "signature": signature},
            )
        ]

    # --- אופרטור בין טיפוסים לא תואמים ---
    match = re.search(
        r"unsupported operand type\(s\) for ([^:]+): ['\"]([^'\"]+)['\"] and ['\"]([^'\"]+)['\"]",
        message,
    )
    if match:
        op, left, right = match.group(1).strip(), match.group(2), match.group(3)
        hint = _CONVERSION_HINTS.get((left, right), f"{left}(...) / {right}(...)")
        return [
            _diag(
                info,
                "type.operand",
                "type.operand.title",
                suggestion_key="type.operand.suggestion",
                title_args={"op": op, "left": left, "right": right},
                suggestion_args={"hint": hint},
                confidence=0.84,
                meta={"kind": "operand", "left": left, "right": right, "op": op},
            )
        ]

    match = re.search(r"can only concatenate (\w+) \(not [\"']?(\w+)[\"']?\) to (\w+)", message)
    if match:
        return [
            _diag(
                info,
                "type.concat",
                "type.operand.title",
                suggestion_key="type.strint.suggestion",
                title_args={"op": "+", "left": match.group(3), "right": match.group(2)},
                suggestion_args={"hint": 'f"{a}{b}"'},
                confidence=0.86,
                meta={"kind": "concat"},
            )
        ]

    # --- לא ניתן לקריאה / לאינדוקס / לאיטרציה ---
    match = re.search(r"['\"]?(\w+)['\"]? object is not callable", message)
    if match:
        return [
            _diag(
                info,
                "type.not-callable",
                "type.callable.title",
                suggestion_key="type.callable.suggestion",
                title_args={"owner": match.group(1)},
                confidence=0.72,
                meta={"kind": "not_callable", "type": match.group(1)},
            )
        ]

    match = re.search(r"['\"]?(\w+)['\"]? object is not subscriptable", message)
    if match:
        return [
            _diag(
                info,
                "type.not-subscriptable",
                "type.subscript.title",
                suggestion_key="type.subscript.suggestion",
                title_args={"owner": match.group(1)},
                confidence=0.75,
                meta={"kind": "not_subscriptable", "type": match.group(1)},
            )
        ]

    match = re.search(r"['\"]?(\w+)['\"]? object is not iterable", message)
    if match:
        return [
            _diag(
                info,
                "type.not-iterable",
                "type.notiterable.title",
                suggestion_key="type.notiterable.suggestion",
                title_args={"owner": match.group(1)},
                confidence=0.75,
                meta={"kind": "not_iterable", "type": match.group(1)},
            )
        ]

    return []


# ======================================================================
# ValueError (כולל JSON)
# ======================================================================
@fixer(ValueError)
def fix_value_error(info: ErrorInfo) -> list[Diagnosis]:
    message = info.message

    if type(info.exc).__name__ == "JSONDecodeError":
        pos = getattr(info.exc, "pos", None)
        lineno = getattr(info.exc, "lineno", None)
        detail = ""
        if lineno is not None:
            detail = f"line {lineno}, col {getattr(info.exc, 'colno', '?')} (pos {pos})"
        return [
            Diagnosis(
                title=info.tr("json.title"),
                detail=detail,
                suggestion=info.tr("json.suggestion"),
                confidence=0.80,
                source="local",
                rule="value.json",
                meta={"kind": "json_decode"},
            )
        ]

    match = re.search(r"invalid literal for int\(\) with base \d+: ['\"](.*)['\"]", message)
    if match:
        return [
            _diag(
                info,
                "value.int",
                "value.int.title",
                suggestion_key="value.int.suggestion",
                title_args={"raw": match.group(1)},
                confidence=0.88,
                meta={"kind": "int_parse", "raw": match.group(1)},
            )
        ]

    match = re.search(r"not enough values to unpack \(expected (\d+), got (\d+)\)", message)
    if match:
        return [
            _diag(
                info,
                "value.unpack",
                "value.unpack.title",
                suggestion_key="value.unpack.suggestion",
                title_args={"want": match.group(1), "got": match.group(2)},
                confidence=0.85,
                meta={"kind": "unpack", "want": int(match.group(1)), "got": int(match.group(2))},
            )
        ]

    match = re.search(r"too many values to unpack \(expected (\d+)\)", message)
    if match:
        return [
            _diag(
                info,
                "value.unpack",
                "value.unpack.title",
                suggestion_key="value.unpack.suggestion",
                title_args={"want": match.group(1), "got": "יותר" if info.lang == "he" else "more"},
                confidence=0.85,
                meta={"kind": "unpack_many", "want": int(match.group(1))},
            )
        ]
    return []


@fixer(ZeroDivisionError)
def fix_zero_division(info: ErrorInfo) -> list[Diagnosis]:
    return [
        _diag(
            info,
            "zero.division",
            "zero.title",
            suggestion_key="zero.suggestion",
            confidence=0.90,
            meta={"kind": "zero_division"},
        )
    ]


# ======================================================================
# FileNotFoundError וחברים
# ======================================================================
@fixer(FileNotFoundError)
def fix_file_not_found(info: ErrorInfo) -> list[Diagnosis]:
    filename = getattr(info.exc, "filename", None) or ""
    if not filename:
        quoted = _quoted(info.message)
        filename = quoted[-1] if quoted else ""
    if not filename:
        return []

    path = os.path.abspath(filename)
    parent = os.path.dirname(path) or os.getcwd()
    base = os.path.basename(path)

    if not os.path.isdir(parent):
        return [
            _diag(
                info,
                "file.dir-missing",
                "file.generic.title",
                detail_key="file.dirmissing.detail",
                title_args={"name": filename},
                detail_args={"parent": parent},
                confidence=0.86,
                meta={"kind": "missing_dir", "parent": parent},
            )
        ]

    try:
        siblings = os.listdir(parent)
    except OSError:
        siblings = []

    best, score = typo.best_match(base, siblings, cutoff=0.60)
    if best:
        return [
            _diag(
                info,
                "file.typo",
                "file.typo.title",
                suggestion_key="file.typo.suggestion",
                title_args={"name": base},
                suggestion_args={"best": best},
                confidence=min(0.93, score),
                meta={"kind": "file_typo", "bad": base, "good": os.path.join(parent, best)},
            )
        ]

    return [
        _diag(
            info,
            "file.missing",
            "file.generic.title",
            detail_key="file.cwd.detail" if not os.path.isabs(filename) else "",
            title_args={"name": filename},
            detail_args={"cwd": os.getcwd()},
            confidence=0.78 if not os.path.isabs(filename) else 0.60,
            meta={"kind": "file_missing", "path": path},
        )
    ]


@fixer(UnicodeDecodeError, UnicodeEncodeError)
def fix_unicode(info: ErrorInfo) -> list[Diagnosis]:
    encoding = getattr(info.exc, "encoding", "")
    return [
        _diag(
            info,
            "unicode.decode",
            "unicode.title",
            suggestion_key="unicode.suggestion",
            confidence=0.84,
            meta={"kind": "unicode", "encoding": encoding},
        )
    ]


@fixer(RecursionError)
def fix_recursion(info: ErrorInfo) -> list[Diagnosis]:
    return [
        _diag(
            info,
            "recursion.limit",
            "recursion.title",
            suggestion_key="recursion.suggestion",
            confidence=0.85,
            meta={"kind": "recursion"},
        )
    ]


@fixer(AssertionError)
def fix_assertion(info: ErrorInfo) -> list[Diagnosis]:
    return [
        _diag(
            info,
            "assert.failed",
            "assert.title",
            suggestion_key="assert.suggestion",
            confidence=0.55,
            meta={"kind": "assertion"},
        )
    ]


_NETWORK_NAMES = {
    "ConnectionError", "ConnectionRefusedError", "ConnectionResetError",
    "ConnectionAbortedError", "TimeoutError", "URLError", "HTTPError",
    "gaierror", "SSLError", "ReadTimeout", "ConnectTimeout", "NewConnectionError",
    "MaxRetryError", "RemoteDisconnected",
}


@fixer(OSError)
def fix_network(info: ErrorInfo) -> list[Diagnosis]:
    if isinstance(info.exc, FileNotFoundError):
        return []
    names = {cls.__name__ for cls in type(info.exc).__mro__}
    if not (names & _NETWORK_NAMES):
        return []
    return [
        _diag(
            info,
            "network.failure",
            "network.title",
            suggestion_key="network.suggestion",
            confidence=0.78,
            meta={"kind": "network"},
        )
    ]


# ======================================================================
# SyntaxError
# ======================================================================
_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {value: key for key, value in _OPENERS.items()}


def _unbalanced(source: str) -> tuple[str, int] | None:
    """מוצא את הסוגר הפתוח הראשון שלא נסגר. מדלג על מחרוזות ותגובות."""
    stack: list[tuple[str, int]] = []
    in_string: str | None = None
    escaped = False
    line = 1
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\n":
            line += 1
            index += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif source.startswith(in_string, index):
                index += len(in_string) - 1
                in_string = None
            index += 1
            continue
        if char == "#":
            while index < len(source) and source[index] != "\n":
                index += 1
            continue
        if char in "\"'":
            triple = source[index : index + 3]
            in_string = triple if triple in ('"""', "'''") else char
            index += len(in_string)
            continue
        if char in _OPENERS:
            stack.append((char, line))
        elif char in _CLOSERS:
            if stack and stack[-1][0] == _CLOSERS[char]:
                stack.pop()
            else:
                return (char, line)
        index += 1
    if stack:
        opener, opened_line = stack[0]
        return (_OPENERS[opener], opened_line)
    return None


@fixer(SyntaxError)
def fix_syntax(info: ErrorInfo) -> list[Diagnosis]:
    exc = info.exc
    message = (getattr(exc, "msg", "") or info.message).lower()
    text = (getattr(exc, "text", "") or "").rstrip("\n")
    lineno = getattr(exc, "lineno", 0) or 0
    out: list[Diagnosis] = []
    # 0. זיהוי שורת קוד שהוקלדה במקלדת זרה (עברית, רוסית, ערבית, יוונית או פקודות בשפה טבעית)
    if text and any(ord(c) > 127 for c in text):
        from ..keyboard import transliterate_line

        translated = transliterate_line(text)
        if translated != text:
            is_valid = False
            try:
                ast.parse(translated)
                is_valid = True
            except SyntaxError:  # sbpy: ignore=silent-except
                try:
                    ast.parse(translated + "\n    pass")
                    is_valid = True
                except SyntaxError:  # sbpy: ignore=silent-except
                    pass

            is_he = info.lang == "he"
            title = (
                "טעות פריסת מקלדת: שורת הקוד נכתבה במקלדת לא-אנגלית"
                if is_he
                else "Foreign keyboard layout: Code line was typed in non-English keyboard"
            )
            detail = (
                f"שורת הקוד תורגמה לפייתון תקין: {translated}"
                if is_he
                else f"Line transliterated to valid Python: {translated}"
            )
            suggestion = (
                f"החלף את השורה בקוד המתוקן: {translated}"
                if is_he
                else f"Replace line with corrected Python code: {translated}"
            )
            out.append(
                Diagnosis(
                    title=title,
                    detail=detail,
                    suggestion=suggestion,
                    confidence=0.98 if is_valid else 0.88,
                    source="local",
                    rule="syntax.keyboard-layout",
                    patch=translated,
                    meta={"kind": "keyboard_layout_syntax", "bad": text, "good": translated},
                )
            )

    if "missing parentheses in call to" in message:
        out.append(
            _diag(
                info,
                "syntax.python2",
                "syntax.print2.title",
                suggestion_key="syntax.print2.suggestion",
                confidence=0.95,
                meta={"kind": "python2"},
            )
        )
    if "expected ':'" in message or "expected an indented block" in message:
        out.append(
            _diag(
                info,
                "syntax.colon",
                "syntax.colon.title",
                suggestion_key="syntax.colon.suggestion",
                confidence=0.92,
                patch=(text.rstrip() + ":") if text and not text.rstrip().endswith(":") else None,
                meta={"kind": "missing_colon"},
            )
        )
    if "was never closed" in message or "unexpected eof" in message or "invalid syntax" in message:
        source = ""
        filename = getattr(exc, "filename", "") or ""
        if filename and os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8", errors="replace") as handle:
                    source = handle.read()
            except OSError:
                source = ""
        problem = _unbalanced(source) if source else None
        if problem:
            out.append(
                _diag(
                    info,
                    "syntax.brackets",
                    "syntax.paren.title",
                    suggestion_key="syntax.paren.suggestion",
                    suggestion_args={"missing": problem[0], "line": problem[1]},
                    confidence=0.90,
                    meta={"kind": "unbalanced", "missing": problem[0], "line": problem[1]},
                )
            )
    if "cannot assign to" in message or re.search(r"\bif\b.*[^=!<>]=[^=]", text or ""):
        if text and re.search(r"^\s*(if|while|elif)\b.*[^=!<>+\-*/]=[^=]", text):
            out.append(
                _diag(
                    info,
                    "syntax.assign-in-condition",
                    "syntax.assign.title",
                    confidence=0.88,
                    patch=re.sub(r"([^=!<>])=([^=])", r"\1==\2", text, count=1) if text else None,
                    meta={"kind": "assign_in_condition", "line": lineno},
                )
            )
    return out


# ======================================================================
# Asyncio / Concurrency
# ======================================================================
@fixer(RuntimeError, TypeError)
def fix_asyncio_errors(info: ErrorInfo) -> list[Diagnosis]:
    msg = (info.message or "").lower()
    if "this event loop is already running" in msg or "event loop is already running" in msg:
        return [
            _diag(
                info,
                "async.loop_running",
                "async.loop_running.title",
                suggestion_key="async.loop_running.suggestion",
                confidence=0.94,
                meta={"kind": "async_loop_running"},
            )
        ]
    if "can't be used in 'await' expression" in msg or "cannot be used in 'await' expression" in msg or "object is not awaitable" in msg:
        return [
            _diag(
                info,
                "async.not_awaitable",
                "async.not_awaitable.title",
                suggestion_key="async.not_awaitable.suggestion",
                confidence=0.92,
                meta={"kind": "not_awaitable"},
            )
        ]
    return []


# ======================================================================
# Database / SQLite
# ======================================================================
@fixer(Exception)
def fix_database_errors(info: ErrorInfo) -> list[Diagnosis]:
    exc_type_name = info.exc_type.__name__
    if not ("OperationalError" in exc_type_name or "DatabaseError" in exc_type_name or "sqlite" in exc_type_name.lower()):
        return []
    msg = info.message or ""
    match_table = re.search(r"no such table:\s*([\w.]+)", msg, re.IGNORECASE)
    if match_table:
        table = match_table.group(1)
        return [
            _diag(
                info,
                "db.no_table",
                "db.no_table.title",
                suggestion_key="db.no_table.suggestion",
                title_args={"table": table},
                confidence=0.93,
                meta={"kind": "db_no_table", "table": table},
            )
        ]
    match_col = re.search(r"no such column:\s*([\w.]+)", msg, re.IGNORECASE)
    if match_col:
        col = match_col.group(1)
        return [
            _diag(
                info,
                "db.no_column",
                "db.no_column.title",
                suggestion_key="db.no_column.suggestion",
                title_args={"column": col},
                confidence=0.93,
                meta={"kind": "db_no_column", "column": col},
            )
        ]
    if "database is locked" in msg.lower() or "database locked" in msg.lower():
        return [
            _diag(
                info,
                "db.locked",
                "db.locked.title",
                suggestion_key="db.locked.suggestion",
                confidence=0.92,
                meta={"kind": "db_locked"},
            )
        ]
    return []


# ======================================================================
# Pydantic
# ======================================================================
@fixer(ValueError, Exception)
def fix_pydantic_errors(info: ErrorInfo) -> list[Diagnosis]:
    exc_type_name = info.exc_type.__name__
    if "ValidationError" not in exc_type_name and "pydantic" not in str(type(info.exc)).lower():
        return []
    msg = (info.message or "").split("\n")[0]
    return [
        _diag(
            info,
            "pydantic.validation",
            "pydantic.validation.title",
            suggestion_key="pydantic.validation.suggestion",
            title_args={"message": msg[:80]},
            confidence=0.90,
            meta={"kind": "pydantic_validation", "message": msg},
        )
    ]


# ======================================================================
# הרצה
# ======================================================================
def run_fixers(info: ErrorInfo) -> list[Diagnosis]:
    """מריץ את כל התיקונים המקומיים המתאימים ומחזיר אבחנות ממוינות."""
    results: list[Diagnosis] = []
    for exc_types, func in _REGISTRY:
        if not isinstance(info.exc, exc_types):
            continue
        try:
            results.extend(func(info) or [])
        except Exception:  # pragma: no cover - fixer לעולם לא יפיל את התוכנית
            if os.environ.get("SBPY_DEBUG"):
                raise
            continue
    results.sort(key=lambda d: -d.confidence)
    return results


def registered_rules() -> list[str]:
    return sorted({func.__name__ for _, func in _REGISTRY})
