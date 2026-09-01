"""שכבה 2: ניתוח סטטי מקומי (AST) - הבסיס של @SFB, @SEC, @OPT, @CMP.

הכל רץ מקומית ובחינם. Gemini נקרא רק על מה שהניתוח הזה לא הצליח להכריע.
"""

from __future__ import annotations

import ast
import builtins
import io
import os
import re
import tokenize
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from ..results import Finding
from ..redact import scan_secrets

# ----------------------------------------------------------------------
# קטגוריות: כל חוק שייך לקטגוריה אחת, וכל קיצור-דרך שואב קטגוריות
CATEGORY_BUG = "bug"
CATEGORY_SEC = "sec"
CATEGORY_OPT = "opt"
CATEGORY_DOC = "doc"
CATEGORY_TYPE = "type"
CATEGORY_TODO = "todo"
CATEGORY_COMPLEXITY = "complexity"
CATEGORY_STYLE = "style"
CATEGORY_MOD = "mod"

RULE_CATEGORY: dict[str, str] = {}
RULE_HELP: dict[str, str] = {}

_BUILTIN_NAMES = frozenset(dir(builtins))
_SHADOWABLE = frozenset(
    {
        "list", "dict", "set", "str", "int", "float", "bool", "tuple", "bytes",
        "id", "type", "input", "sum", "max", "min", "filter", "map", "next",
        "object", "range", "len", "open", "format", "hash", "iter", "vars",
        "print", "all", "any", "abs", "round", "sorted", "zip", "file",
    }
)

_INSECURE_HASHES = {"md5", "sha1"}


def _register(rule: str, category: str, help_text: str = "") -> str:
    RULE_CATEGORY[rule] = category
    if help_text:
        RULE_HELP[rule] = help_text
    return rule


# ----------------------------------------------------------------------
@dataclass
class SourceUnit:
    """קובץ או קטע קוד שעבר פענוח פעם אחת ומשותף לכל הבדיקות."""

    source: str
    filename: str = "<code>"
    tree: ast.AST | None = None
    lines: list[str] = field(default_factory=list)
    syntax_error: SyntaxError | None = None

    @classmethod
    def from_source(cls, source: str, filename: str = "<code>") -> "SourceUnit":
        unit = cls(source=source, filename=filename, lines=source.splitlines())
        try:
            unit.tree = ast.parse(source, filename=filename)
            _attach_parents(unit.tree)
        except SyntaxError as exc:
            unit.syntax_error = exc
        return unit

    @classmethod
    def from_path(cls, path: str) -> "SourceUnit":
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return cls.from_source(handle.read(), filename=path)

    def line(self, number: int) -> str:
        if 1 <= number <= len(self.lines):
            return self.lines[number - 1].strip()
        return ""


def _attach_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.sbpy_parent = parent  # type: ignore[attr-defined]


def _parent(node: ast.AST) -> ast.AST | None:
    return getattr(node, "sbpy_parent", None)


def _ancestors(node: ast.AST) -> Iterator[ast.AST]:
    current = _parent(node)
    while current is not None:
        yield current
        current = _parent(current)


def _enclosing_loop(node: ast.AST) -> ast.AST | None:
    for parent in _ancestors(node):
        if isinstance(parent, (ast.For, ast.AsyncFor, ast.While)):
            return parent
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
    return None


def _dotted(node: ast.AST | None) -> str:
    """מחזיר 'os.path.join' עבור צומת קריאה/תכונה."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return ""


class _Collector:
    """אוסף ממצאים עם גישה נוחה לקובץ המקור."""

    def __init__(self, unit: SourceUnit) -> None:
        self.unit = unit
        self.findings: list[Finding] = []

    def add(
        self,
        rule: str,
        node: ast.AST | int,
        message: str,
        *,
        severity: str = "warn",
        hint: str = "",
        confidence: float = 0.9,
        symbol: str = "",
    ) -> None:
        if isinstance(node, int):
            line, col = node, 0
        else:
            line = getattr(node, "lineno", 0)
            col = getattr(node, "col_offset", 0)
        self.findings.append(
            Finding(
                rule=rule,
                message=message,
                line=line,
                col=col,
                severity=severity,  # type: ignore[arg-type]
                file=self.unit.filename,
                hint=hint,
                snippet=self.unit.line(line),
                source="static",
                confidence=confidence,
                symbol=symbol,
            )
        )


# ======================================================================
# באגים כלליים - @SFB
# ======================================================================
R_MUTABLE_DEFAULT = _register("mutable-default-arg", CATEGORY_BUG)
R_BARE_EXCEPT = _register("bare-except", CATEGORY_BUG)
R_SILENT_EXCEPT = _register("silent-except", CATEGORY_BUG)
R_EQ_NONE = _register("compare-none-with-eq", CATEGORY_BUG)
R_IS_LITERAL = _register("is-with-literal", CATEGORY_BUG)
R_EQ_BOOL = _register("compare-bool-with-eq", CATEGORY_STYLE)
R_FSTRING = _register("missing-f-prefix", CATEGORY_BUG)
R_UNUSED_IMPORT = _register("unused-import", CATEGORY_STYLE)
R_SHADOW_BUILTIN = _register("shadows-builtin", CATEGORY_BUG)
R_ASSERT_TUPLE = _register("assert-on-tuple", CATEGORY_BUG)
R_UNREACHABLE = _register("unreachable-code", CATEGORY_BUG)
R_DUP_KEY = _register("duplicate-dict-key", CATEGORY_BUG)
R_SELF_ASSIGN = _register("self-assignment", CATEGORY_BUG)
R_EXCEPT_ORDER = _register("except-order", CATEGORY_BUG)
R_LOOP_CLOSURE = _register("loop-variable-capture", CATEGORY_BUG)
R_MUTABLE_CLASSATTR = _register("mutable-class-attribute", CATEGORY_BUG)
R_RETURN_FINALLY = _register("return-in-finally", CATEGORY_BUG)
R_BOOLOP_CONST = _register("comparison-against-constant-chain", CATEGORY_BUG)
R_TYPE_EQ = _register("type-equality", CATEGORY_STYLE)
R_OPEN_NO_WITH = _register("open-without-with", CATEGORY_BUG)
R_OPEN_NO_ENCODING = _register("open-without-encoding", CATEGORY_BUG)
R_REDEFINED = _register("redefined-name", CATEGORY_BUG)
R_FLOAT_EQ = _register("float-equality", CATEGORY_BUG)
R_MUTATE_WHILE_ITER = _register("mutate-while-iterating", CATEGORY_BUG)
R_MISSING_SELF = _register("method-missing-self", CATEGORY_BUG)
R_DEFAULT_CALL = _register("call-in-default-arg", CATEGORY_BUG)
R_EMPTY_BLOCK = _register("empty-body", CATEGORY_STYLE)


def check_bugs(unit: SourceUnit) -> list[Finding]:
    """כל בדיקות הבאגים הכלליות. זה הלב של @SFB."""
    collector = _Collector(unit)
    tree = unit.tree
    if tree is None:
        return collector.findings

    _check_functions(unit, collector)
    _check_exceptions(unit, collector)
    _check_comparisons(unit, collector)
    _check_literals(unit, collector)
    _check_assignments(unit, collector)
    _check_flow(unit, collector)
    _check_files(unit, collector)
    _check_loops_bugs(unit, collector)
    _check_unused_imports(unit, collector)
    return collector.findings


def _check_functions(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    for node in ast.walk(unit.tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        defaults = list(args.defaults) + [d for d in args.kw_defaults if d is not None]
        for default in defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                out.add(
                    R_MUTABLE_DEFAULT,
                    default,
                    f"ערך ברירת מחדל מסוג {type(default).__name__} בפונקציה `{node.name}` משותף לכל הקריאות",
                    severity="error",
                    hint="השתמש ב-None כברירת מחדל וצור את האובייקט בתוך הפונקציה.",
                )
            elif isinstance(default, ast.Call):
                name = _dotted(default.func)
                if name.split(".")[-1] in {"now", "today", "time", "uuid4", "list", "dict", "set"}:
                    out.add(
                        R_DEFAULT_CALL,
                        default,
                        f"`{name}()` מחושב פעם אחת בהגדרת הפונקציה, לא בכל קריאה",
                        severity="error",
                        hint="העבר את הקריאה לגוף הפונקציה.",
                    )

        # מתודה בלי self
        parent = _parent(node)
        if isinstance(parent, ast.ClassDef):
            decorators = {_dotted(d).split(".")[-1] for d in node.decorator_list}
            if not decorators & {"staticmethod", "classmethod", "property"}:
                first = args.posonlyargs[0].arg if args.posonlyargs else (
                    args.args[0].arg if args.args else ""
                )
                if first not in {"self", "cls"} and not args.vararg:
                    out.add(
                        R_MISSING_SELF,
                        node,
                        f"למתודה `{node.name}` אין `self` כפרמטר ראשון",
                        severity="error",
                        hint="הוסף `self`, או סמן ב-@staticmethod.",
                    )

        # גוף ריק. מתודה ריקה בתוך מחלקה היא לרוב דריסה מכוונת
        # (למשל השתקת `log_message` של שרת HTTP), ולא שכחה.
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            if not node.decorator_list and not isinstance(_parent(node), ast.ClassDef):
                out.add(
                    R_EMPTY_BLOCK,
                    node,
                    f"הפונקציה `{node.name}` ריקה",
                    severity="info",
                    hint="השאר `raise NotImplementedError` כדי לא לשכוח.",
                    confidence=0.7,
                )


def _check_exceptions(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Try):
            seen_broad: str = ""
            for handler in node.handlers:
                name = _dotted(handler.type) if handler.type else ""
                if handler.type is None:
                    out.add(
                        R_BARE_EXCEPT,
                        handler,
                        "`except:` בלי סוג תופס גם Ctrl+C ו-SystemExit",
                        severity="error",
                        hint="השתמש ב-`except Exception:` לכל הפחות.",
                    )
                if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                    out.add(
                        R_SILENT_EXCEPT,
                        handler,
                        "השגיאה נבלעת בשקט ואי אפשר לאתר אותה",
                        severity="warn",
                        hint="לפחות רשום ללוג: `logging.exception(...)`.",
                    )
                if seen_broad and name:
                    out.add(
                        R_EXCEPT_ORDER,
                        handler,
                        f"`except {name}` לעולם לא יגיע - `{seen_broad}` תופס אותו קודם",
                        severity="error",
                        hint="סדר את ה-handlers מהספציפי לכללי.",
                    )
                if name in {"Exception", "BaseException"} and not seen_broad:
                    seen_broad = name
            if node.finalbody:
                for inner in node.finalbody:
                    for sub in ast.walk(inner):
                        if isinstance(sub, (ast.Return, ast.Break)):
                            out.add(
                                R_RETURN_FINALLY,
                                sub,
                                "`return`/`break` בתוך finally מבטל שגיאות שקרו קודם",
                                severity="error",
                                hint="הוצא את ההחזרה מחוץ ל-finally.",
                            )


def _check_comparisons(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comparator, ast.Constant):
                    value = comparator.value
                    if value is None:
                        out.add(
                            R_EQ_NONE,
                            node,
                            "השוואה ל-None עם `==` במקום `is`",
                            severity="warn",
                            hint="השתמש ב-`is None` / `is not None`.",
                        )
                    elif isinstance(value, bool):
                        out.add(
                            R_EQ_BOOL,
                            node,
                            f"השוואה ל-{value} מיותרת",
                            severity="info",
                            hint="כתוב `if x:` או `if not x:`.",
                            confidence=0.8,
                        )
                    elif isinstance(value, float):
                        out.add(
                            R_FLOAT_EQ,
                            node,
                            "השוואת שוויון בין מספרים עשרוניים אינה אמינה",
                            severity="warn",
                            hint="השתמש ב-`math.isclose(a, b)`.",
                        )
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comparator, ast.Constant):
                    if comparator.value is not None and not isinstance(comparator.value, bool):
                        out.add(
                            R_IS_LITERAL,
                            node,
                            f"`is` מול הקבוע {comparator.value!r} בודק זהות אובייקט, לא ערך",
                            severity="error",
                            hint="החלף ל-`==`.",
                        )
                if isinstance(op, (ast.Eq, ast.NotEq)):
                    left_is_type = isinstance(node.left, ast.Call) and _dotted(node.left.func) == "type"
                    right_is_type = isinstance(comparator, ast.Call) and _dotted(comparator.func) == "type"
                    if left_is_type or right_is_type:
                        out.add(
                            R_TYPE_EQ,
                            node,
                            "השוואת `type(...)` מתעלמת מירושה",
                            severity="warn",
                            hint="השתמש ב-`isinstance(x, T)`.",
                        )

        # if x == 1 or 2  -> תמיד אמת.
        # רק כשיש השוואה אמיתית באחד האגפים; אחרת זה סתם `value or default`
        # שהוא ניב לגיטימי לחלוטין ואסור לדווח עליו.
        if isinstance(node, ast.BoolOp) and any(
            isinstance(value, ast.Compare) for value in node.values
        ):
            for value in node.values:
                if isinstance(value, ast.Constant) and not isinstance(value.value, bool):
                    out.add(
                        R_BOOLOP_CONST,
                        node,
                        f"הקבוע {value.value!r} בתוך `{'or' if isinstance(node.op, ast.Or) else 'and'}` "
                        "הופך את התנאי לקבוע",
                        severity="error",
                        hint="כתוב `x in (1, 2)` או השווה כל צד בנפרד.",
                    )
                    break


_BRACE = re.compile(r"\{([^{}]+)\}")
_IDENT = re.compile(r"^([A-Za-z_]\w*)")


def _known_names(tree: ast.AST) -> set[str]:
    names: set[str] = set(_BUILTIN_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


def _is_docstring(node: ast.Constant) -> bool:
    parent = _parent(node)
    if not isinstance(parent, ast.Expr):
        return False
    grand = _parent(parent)
    body = getattr(grand, "body", None)
    return isinstance(body, list) and bool(body) and body[0] is parent


def _check_literals(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    known = _known_names(unit.tree)

    for node in ast.walk(unit.tree):
        # מחרוזת עם {placeholder} בלי f בתחילתה
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if "{" not in text or "{{" in text or _is_docstring(node):
                continue
            parent = _parent(node)
            if isinstance(parent, ast.JoinedStr):
                continue
            if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Mod):
                continue
            # ערך בתוך מילון הוא כמעט תמיד תבנית שתפורמט מאוחר יותר
            # (קטלוג תרגום, הגדרות, מפת הודעות) - ולא f-string שנשכח.
            if isinstance(parent, ast.Dict) and node in parent.values:
                continue
            if isinstance(parent, ast.Attribute) and parent.attr in {"format", "format_map"}:
                continue
            # A module-level CONSTANT holding a template is filled in later,
            # somewhere else. An f-string here would interpolate too early.
            if isinstance(parent, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id.isupper() for t in parent.targets
            ):
                continue
            if isinstance(parent, ast.keyword) and parent.arg in {"pattern", "regex"}:
                continue
            hits = [match.group(1) for match in _BRACE.finditer(text)]
            resolved = []
            for hit in hits:
                ident = _IDENT.match(hit.strip())
                if ident and ident.group(1) in known:
                    resolved.append(ident.group(1))
            if resolved:
                out.add(
                    R_FSTRING,
                    node,
                    f"מחרוזת עם `{{{resolved[0]}}}` בלי הקידומת `f` - הטקסט יודפס כמו שהוא",
                    severity="error",
                    hint="הוסף `f` לפני המרכאות.",
                    confidence=0.85,
                )

        # מפתחות כפולים במילון
        if isinstance(node, ast.Dict):
            seen: dict[object, int] = {}
            for key in node.keys:
                if isinstance(key, ast.Constant):
                    if key.value in seen:
                        out.add(
                            R_DUP_KEY,
                            key,
                            f"המפתח {key.value!r} מופיע פעמיים - הערך הראשון נדרס",
                            severity="error",
                            hint="מחק את הכפילות או שנה את אחד המפתחות.",
                        )
                    seen[key.value] = key.lineno

        # assert (a, b) - תמיד אמת
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Tuple) and node.test.elts:
            out.add(
                R_ASSERT_TUPLE,
                node,
                "`assert` על tuple תמיד מצליח - הבדיקה חסרת משמעות",
                severity="error",
                hint="הסר את הסוגריים: `assert cond, 'message'`.",
            )


def _check_assignments(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Assign):
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Name)
                and node.targets[0].id == node.value.id
            ):
                out.add(
                    R_SELF_ASSIGN,
                    node,
                    f"`{node.value.id} = {node.value.id}` לא עושה כלום",
                    severity="warn",
                    hint="כנראה התכוונת ל-`self.x = x` או לשם אחר.",
                )
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in _SHADOWABLE:
                    out.add(
                        R_SHADOW_BUILTIN,
                        target,
                        f"המשתנה `{target.id}` דורס פונקציה מובנית של פייתון",
                        severity="warn",
                        hint=f"שנה שם, למשל `{target.id}_` או שם משמעותי יותר.",
                        confidence=0.85,
                    )

        # תכונת מחלקה שהיא אובייקט משתנה - משותפת לכל המופעים
        if isinstance(node, ast.ClassDef):
            for statement in node.body:
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    value = statement.value
                    if isinstance(value, (ast.List, ast.Dict, ast.Set)):
                        out.add(
                            R_MUTABLE_CLASSATTR,
                            statement,
                            f"תכונת מחלקה מסוג {type(value).__name__} משותפת לכל המופעים של `{node.name}`",
                            severity="warn",
                            hint="אתחל אותה בתוך `__init__`.",
                        )

    # שם שהוגדר פעמיים באותו היקף
    for scope in ast.walk(unit.tree):
        body = getattr(scope, "body", None)
        if not isinstance(body, list):
            continue
        defined: dict[str, int] = {}
        for statement in body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if statement.name in defined:
                    out.add(
                        R_REDEFINED,
                        statement,
                        f"`{statement.name}` מוגדר שוב - ההגדרה מהשורה {defined[statement.name]} נדרסת",
                        severity="error",
                        hint="מחק או שנה שם לאחת ההגדרות.",
                    )
                defined[statement.name] = statement.lineno


def _check_flow(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    terminators = (ast.Return, ast.Raise, ast.Continue, ast.Break)
    for node in ast.walk(unit.tree):
        body = getattr(node, "body", None)
        bodies = []
        if isinstance(body, list):
            bodies.append(body)
        for attribute in ("orelse", "finalbody"):
            extra = getattr(node, attribute, None)
            if isinstance(extra, list):
                bodies.append(extra)
        for block in bodies:
            for index, statement in enumerate(block[:-1]):
                if isinstance(statement, terminators):
                    following = block[index + 1]
                    out.add(
                        R_UNREACHABLE,
                        following,
                        f"קוד שלא ירוץ לעולם - השורה {statement.lineno} מסיימת את הבלוק",
                        severity="error",
                        hint="מחק את הקוד או העבר אותו מעל.",
                    )
                    break


def _check_files(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    for node in ast.walk(unit.tree):
        if not isinstance(node, ast.Call) or _dotted(node.func) != "open":
            continue
        kwargs = {kw.arg for kw in node.keywords}
        mode = ""
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = str(kw.value.value)
        if "b" not in mode and "encoding" not in kwargs:
            out.add(
                R_OPEN_NO_ENCODING,
                node,
                "`open()` בלי `encoding` - התוצאה תלויה בהגדרות המערכת (בעיה קלאסית עם עברית)",
                severity="warn",
                hint="הוסף `encoding='utf-8'`.",
            )
        parent = _parent(node)
        in_with = isinstance(parent, ast.withitem)
        if not in_with:
            has_close = False
            if isinstance(parent, ast.Assign) and parent.targets:
                target = parent.targets[0]
                if isinstance(target, ast.Name):
                    for sub in ast.walk(unit.tree):
                        if (
                            isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "close"
                            and _dotted(sub.func.value) == target.id
                        ):
                            has_close = True
                            break
            if not has_close:
                out.add(
                    R_OPEN_NO_WITH,
                    node,
                    "`open()` בלי `with` - הקובץ עלול להישאר פתוח אם תיזרק שגיאה",
                    severity="warn",
                    hint="השתמש ב-`with open(...) as f:`.",
                    confidence=0.75,
                )


def _check_loops_bugs(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None
    mutators = {"append", "remove", "pop", "insert", "clear", "extend", "sort"}
    for node in ast.walk(unit.tree):
        if not isinstance(node, (ast.For, ast.AsyncFor)):
            continue

        # שינוי הרשימה בזמן מעבר עליה
        if isinstance(node.iter, ast.Name):
            iterated = node.iter.id
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr in mutators
                    and _dotted(sub.func.value) == iterated
                ):
                    out.add(
                        R_MUTATE_WHILE_ITER,
                        sub,
                        f"`{iterated}.{sub.func.attr}()` בתוך לולאה שרצה על `{iterated}` - איברים ידולגו",
                        severity="error",
                        hint=f"רוץ על עותק: `for x in {iterated}[:]` או בנה רשימה חדשה.",
                    )

        # lambda שלוכדת את משתנה הלולאה
        targets = {
            child.id for child in ast.walk(node.target) if isinstance(child, ast.Name)
        }
        for sub in ast.walk(node):
            if isinstance(sub, ast.Lambda):
                used = {
                    child.id
                    for child in ast.walk(sub.body)
                    if isinstance(child, ast.Name)
                }
                captured = used & targets
                bound = {arg.arg for arg in sub.args.args}
                captured -= bound
                if captured:
                    out.add(
                        R_LOOP_CLOSURE,
                        sub,
                        f"ה-lambda לוכדת את `{sorted(captured)[0]}` בהפניה - כל הפונקציות יקבלו את הערך האחרון",
                        severity="error",
                        hint=f"קבע את הערך: `lambda x, {sorted(captured)[0]}={sorted(captured)[0]}: ...`",
                    )


def _string_annotation_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for match in re.finditer(r"[A-Za-z_]\w*", node.value):
                names.add(match.group(0))
    return names


def _exported_names(tree: ast.AST) -> set[str]:
    """The strings in ``__all__`` - names the module deliberately re-exports.

    A package ``__init__`` imports names purely so others can import them
    from it. Those imports look unused inside the file, and are not.
    """
    exported: set[str] = set()
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AugAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        if node.value is None:
            continue
        for element in ast.walk(node.value):
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                exported.add(element.value)
    return exported


def _check_unused_imports(unit: SourceUnit, out: _Collector) -> None:
    assert unit.tree is not None

    # A package ``__init__`` re-exports by importing. Its imports look unused
    # inside the file while other modules depend on them - and this file
    # cannot see that. Reporting here means proposing a breaking deletion.
    if os.path.basename(unit.filename) == "__init__.py":
        return

    imported: dict[str, ast.AST] = {}
    for node in unit.tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__" or any(alias.name == "*" for alias in node.names):
                continue
            for alias in node.names:
                imported[alias.asname or alias.name] = node

    if not imported:
        return

    used: set[str] = set()
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value  # type: ignore[assignment]
            if isinstance(root, ast.Name):
                used.add(root.id)
    used |= _string_annotation_names(unit.tree)
    used |= _exported_names(unit.tree)

    for name, node in imported.items():
        if name not in used:
            out.add(
                R_UNUSED_IMPORT,
                node,
                f"`{name}` מיובא אבל לא בשימוש",
                severity="info",
                hint="מחק את השם מהייבוא כדי לקצר את זמן הטעינה.",
                confidence=0.85,
                symbol=name,
            )


# ======================================================================
# אבטחה - @SEC
# ======================================================================
R_EVAL = _register("dangerous-eval", CATEGORY_SEC)
R_SHELL = _register("shell-injection", CATEGORY_SEC)
R_PICKLE = _register("unsafe-deserialization", CATEGORY_SEC)
R_YAML = _register("unsafe-yaml-load", CATEGORY_SEC)
R_WEAK_HASH = _register("weak-hash", CATEGORY_SEC)
R_NO_VERIFY = _register("tls-verification-disabled", CATEGORY_SEC)
R_SECRET = _register("hardcoded-secret", CATEGORY_SEC)
R_SQL = _register("sql-string-building", CATEGORY_SEC)
R_TEMPFILE = _register("insecure-tempfile", CATEGORY_SEC)
R_WEAK_RANDOM = _register("weak-random-for-secret", CATEGORY_SEC)


def check_security(unit: SourceUnit) -> list[Finding]:
    collector = _Collector(unit)
    tree = unit.tree
    if tree is None:
        return collector.findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            short = name.split(".")[-1]

            if short in {"eval", "exec"} and node.args:
                literal = isinstance(node.args[0], ast.Constant)
                collector.add(
                    R_EVAL,
                    node,
                    f"`{short}()` מריץ קוד שרירותי",
                    severity="info" if literal else "critical",
                    hint="השתמש ב-`ast.literal_eval` או ב-json.",
                    confidence=0.75 if literal else 0.95,
                )

            if name in {"os.system", "os.popen"}:
                collector.add(
                    R_SHELL,
                    node,
                    f"`{name}` מריץ פקודת מעטפת - קלט לא מסונן מאפשר הזרקת פקודות",
                    severity="critical",
                    hint="השתמש ב-`subprocess.run([...])` עם רשימת ארגומנטים.",
                )

            if name.startswith("subprocess."):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                        collector.add(
                            R_SHELL,
                            node,
                            "`shell=True` חושף להזרקת פקודות",
                            severity="critical",
                            hint="העבר רשימת ארגומנטים במקום מחרוזת אחת.",
                        )

            if name in {"pickle.load", "pickle.loads", "marshal.loads", "shelve.open", "dill.loads"}:
                collector.add(
                    R_PICKLE,
                    node,
                    f"`{name}` מריץ קוד בזמן הפענוח",
                    severity="error",
                    hint="אל תפענח נתונים ממקור לא אמין. השתמש ב-json.",
                )

            if name in {"yaml.load"} and not any(kw.arg == "Loader" for kw in node.keywords):
                collector.add(
                    R_YAML,
                    node,
                    "`yaml.load` בלי Loader מריץ קוד מהקובץ",
                    severity="error",
                    hint="השתמש ב-`yaml.safe_load(...)`.",
                )

            if name.startswith("hashlib.") and short in _INSECURE_HASHES:
                collector.add(
                    R_WEAK_HASH,
                    node,
                    f"`{short}` שבור לצרכי אבטחה",
                    severity="warn",
                    hint="לסיסמאות השתמש ב-`hashlib.scrypt` או ב-argon2.",
                )

            if name == "tempfile.mktemp":
                collector.add(
                    R_TEMPFILE,
                    node,
                    "`mktemp` פגיע ל-race condition",
                    severity="warn",
                    hint="השתמש ב-`tempfile.NamedTemporaryFile`.",
                )

            for kw in node.keywords:
                if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    collector.add(
                        R_NO_VERIFY,
                        node,
                        "`verify=False` מבטל בדיקת תעודות TLS",
                        severity="error",
                        hint="השאר את האימות פעיל, או ציין `verify='/path/ca.pem'`.",
                    )

            # בניית SQL ממחרוזות
            if short in {"execute", "executemany", "executescript"} and node.args:
                first = node.args[0]
                risky = (
                    isinstance(first, ast.JoinedStr)
                    or (isinstance(first, ast.BinOp) and isinstance(first.op, (ast.Add, ast.Mod)))
                )
                if risky:
                    collector.add(
                        R_SQL,
                        node,
                        "שאילתת SQL נבנית משרשור מחרוזות - פתח להזרקת SQL",
                        severity="critical",
                        hint="השתמש בפרמטרים: `cur.execute('... WHERE id = ?', (value,))`.",
                    )

            if name.startswith("random.") and short in {"random", "randint", "choice", "randrange"}:
                for ancestor in _ancestors(node):
                    if isinstance(ancestor, (ast.Assign, ast.AnnAssign)):
                        target_text = _dotted(getattr(ancestor, "targets", [None])[0] if getattr(ancestor, "targets", None) else getattr(ancestor, "target", None))
                        if re.search(r"(?i)token|password|secret|salt|key|otp", target_text or ""):
                            collector.add(
                                R_WEAK_RANDOM,
                                node,
                                "`random` אינו קריפטוגרפי ואינו מתאים לסודות",
                                severity="error",
                                hint="השתמש ב-`secrets.token_urlsafe(...)`.",
                            )
                        break

    for kind, line in scan_secrets(unit.source):
        collector.add(
            R_SECRET,
            line,
            f"סוד כתוב בקוד ({kind})",
            severity="critical",
            hint="העבר למשתנה סביבה וטען עם `os.environ`.",
            confidence=0.8,
        )

    return collector.findings


# ======================================================================
# ביצועים - @OPT
# ======================================================================
R_CONCAT_LOOP = _register("string-concat-in-loop", CATEGORY_OPT)
R_IN_LIST_LOOP = _register("membership-on-list-in-loop", CATEGORY_OPT)
R_RANGE_LEN = _register("range-len", CATEGORY_OPT)
R_LEN_ZERO = _register("len-compare-zero", CATEGORY_OPT)
R_LIST_IN_SUM = _register("list-comprehension-in-aggregate", CATEGORY_OPT)
R_KEYS_IN = _register("keys-membership", CATEGORY_OPT)
R_SORTED_INDEX = _register("sorted-then-index", CATEGORY_OPT)
R_LIST_CONCAT_LOOP = _register("list-concat-in-loop", CATEGORY_OPT)
R_REPEATED_CALL = _register("repeated-call-in-loop-condition", CATEGORY_OPT)
R_RE_COMPILE_IN_FUNC = _register("re-compile-in-func", CATEGORY_OPT)


def check_performance(unit: SourceUnit) -> list[Finding]:
    collector = _Collector(unit)
    tree = unit.tree
    if tree is None:
        return collector.findings

    list_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.ListComp)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    list_names.add(target.id)

    for node in ast.walk(tree):
        # s += "..." בתוך לולאה
        if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
            if _enclosing_loop(node) is not None:
                value_is_str = isinstance(node.value, (ast.Constant, ast.JoinedStr)) and not isinstance(
                    getattr(node.value, "value", ""), (int, float)
                )
                if value_is_str:
                    collector.add(
                        R_CONCAT_LOOP,
                        node,
                        "שרשור מחרוזות בלולאה יוצר עותק חדש בכל סיבוב",
                        severity="warn",
                        hint="אסוף ל-list והשתמש ב-`''.join(parts)`.",
                    )
                elif isinstance(node.value, (ast.List, ast.ListComp)):
                    collector.add(
                        R_LIST_CONCAT_LOOP,
                        node,
                        "חיבור רשימות בלולאה - עדיף `extend`",
                        severity="info",
                        hint="השתמש ב-`items.extend(...)`.",
                        confidence=0.75,
                    )

        if isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                # x in [...] בתוך לולאה
                if isinstance(op, ast.In):
                    is_list = isinstance(comparator, (ast.List, ast.Tuple)) or (
                        isinstance(comparator, ast.Name) and comparator.id in list_names
                    )
                    if is_list and _enclosing_loop(node) is not None:
                        collector.add(
                            R_IN_LIST_LOOP,
                            node,
                            "בדיקת `in` על רשימה בתוך לולאה היא O(n) בכל סיבוב",
                            severity="warn",
                            hint="המר ל-`set(...)` פעם אחת מחוץ ללולאה.",
                        )
                    if (
                        isinstance(comparator, ast.Call)
                        and isinstance(comparator.func, ast.Attribute)
                        and comparator.func.attr == "keys"
                    ):
                        collector.add(
                            R_KEYS_IN,
                            node,
                            "`in d.keys()` מיותר",
                            severity="info",
                            hint="כתוב `in d`.",
                            confidence=0.9,
                        )
                # len(x) == 0
                if (
                    isinstance(op, (ast.Eq, ast.Gt, ast.NotEq))
                    and isinstance(node.left, ast.Call)
                    and _dotted(node.left.func) == "len"
                    and isinstance(comparator, ast.Constant)
                    and comparator.value == 0
                ):
                    collector.add(
                        R_LEN_ZERO,
                        node,
                        "השוואת `len(x)` לאפס",
                        severity="info",
                        hint="כתוב `if not x:` או `if x:`.",
                        confidence=0.85,
                    )

        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name == "range" and len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.Call) and _dotted(arg.func) == "len":
                    parent = _parent(node)
                    if isinstance(parent, (ast.For, ast.AsyncFor)):
                        collector.add(
                            R_RANGE_LEN,
                            node,
                            "`for i in range(len(x))` - עדיף `enumerate`",
                            severity="info",
                            hint="`for i, item in enumerate(x):`",
                            confidence=0.9,
                        )
            if name in {"sum", "any", "all", "min", "max"} and node.args:
                if isinstance(node.args[0], ast.ListComp):
                    collector.add(
                        R_LIST_IN_SUM,
                        node,
                        f"`{name}([...])` בונה רשימה שלמה בזיכרון",
                        severity="info",
                        hint=f"הסר את הסוגריים המרובעים: `{name}(x for x in ...)`.",
                        confidence=0.85,
                    )

        if isinstance(node, ast.Subscript):
            value = node.value
            if isinstance(value, ast.Call) and _dotted(value.func) == "sorted":
                slice_node = node.slice
                if isinstance(slice_node, ast.Constant) and slice_node.value in (0, -1):
                    collector.add(
                        R_SORTED_INDEX,
                        node,
                        "מיון מלא רק כדי לקחת איבר אחד",
                        severity="info",
                        hint="השתמש ב-`min(...)` או `max(...)`.",
                        confidence=0.85,
                    )

        if isinstance(node, ast.While) and isinstance(node.test, ast.Compare):
            for comparator in node.test.comparators:
                if isinstance(comparator, ast.Call) and _dotted(comparator.func) == "len":
                    collector.add(
                        R_REPEATED_CALL,
                        node,
                        "`len(...)` מחושב מחדש בכל סיבוב של הלולאה",
                        severity="info",
                        hint="שמור את האורך במשתנה לפני הלולאה.",
                        confidence=0.7,
                    )

        if isinstance(node, ast.Call) and _dotted(node.func) in {"re.compile"}:
            for ancestor in _ancestors(node):
                if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    collector.add(
                        R_RE_COMPILE_IN_FUNC,
                        node,
                        "קריאה ל-`re.compile` בתוך פונקציה מהדרת את הביטוי בכל ריצה מחדש",
                        severity="info",
                        hint="העבר את ה-`re.compile` לקבוע מחוץ לפונקציה.",
                        confidence=0.85,
                    )
                    break

    return collector.findings


# ======================================================================
# מורכבות - @CMP
# ======================================================================
R_COMPLEX = _register("high-complexity", CATEGORY_COMPLEXITY)
R_LONG_FUNC = _register("long-function", CATEGORY_COMPLEXITY)
R_DEEP_NEST = _register("deep-nesting", CATEGORY_COMPLEXITY)
R_MANY_ARGS = _register("too-many-parameters", CATEGORY_COMPLEXITY)

COMPLEXITY_LIMIT = 10
LENGTH_LIMIT = 60
NESTING_LIMIT = 4
ARGS_LIMIT = 6


def cyclomatic_complexity(node: ast.AST) -> int:
    """מדד מקורב: מספר נקודות ההחלטה + 1."""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.Assert)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            score += 1 + len(child.ifs)
        elif hasattr(ast, "match_case") and isinstance(child, ast.match_case):
            score += 1
    return score


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    nesting_types = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        step = 1 if isinstance(child, nesting_types) else 0
        best = max(best, _max_nesting(child, depth + step))
    return best


def check_complexity(unit: SourceUnit) -> list[Finding]:
    collector = _Collector(unit)
    tree = unit.tree
    if tree is None:
        return collector.findings

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        score = cyclomatic_complexity(node)
        if score > COMPLEXITY_LIMIT:
            collector.add(
                R_COMPLEX,
                node,
                f"`{node.name}` במורכבות ציקלומטית {score} (מעל {COMPLEXITY_LIMIT})",
                severity="warn" if score < COMPLEXITY_LIMIT * 2 else "error",
                hint="פצל לפונקציות קטנות, או החלף שרשרת if במילון.",
            )
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        length = end - node.lineno
        if length > LENGTH_LIMIT:
            collector.add(
                R_LONG_FUNC,
                node,
                f"`{node.name}` באורך {length} שורות",
                severity="info",
                hint="פונקציה שקשה לראות במסך אחד קשה גם לתחזק.",
                confidence=0.8,
            )
        nesting = _max_nesting(node)
        if nesting > NESTING_LIMIT:
            collector.add(
                R_DEEP_NEST,
                node,
                f"`{node.name}` בעומק קינון {nesting}",
                severity="warn",
                hint="השתמש ביציאה מוקדמת (`if not x: return`).",
            )
        arg_count = len(node.args.args) + len(node.args.kwonlyargs) + len(node.args.posonlyargs)
        if node.args.args and node.args.args[0].arg in {"self", "cls"}:
            arg_count -= 1
        if arg_count > ARGS_LIMIT:
            collector.add(
                R_MANY_ARGS,
                node,
                f"`{node.name}` מקבלת {arg_count} פרמטרים",
                severity="info",
                hint="קבץ אותם ל-dataclass.",
                confidence=0.8,
            )
    return collector.findings


# ======================================================================
# תיעוד וטיפוסים - @DOC / @TYP
# ======================================================================
R_NO_DOC = _register("missing-docstring", CATEGORY_DOC)
R_NO_TYPES = _register("missing-type-hints", CATEGORY_TYPE)
R_TODO = _register("todo-comment", CATEGORY_TODO)


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def check_docs(unit: SourceUnit) -> list[Finding]:
    collector = _Collector(unit)
    tree = unit.tree
    if tree is None:
        return collector.findings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if _is_public(node.name) and not ast.get_docstring(node):
                kind = "מחלקה" if isinstance(node, ast.ClassDef) else "פונקציה"
                collector.add(
                    R_NO_DOC,
                    node,
                    f"{kind} ציבורית `{node.name}` בלי docstring",
                    severity="info",
                    hint="הסבר מה היא עושה, מה מקבלת ומה מחזירה.",
                    confidence=0.95,
                )
    return collector.findings


def check_types(unit: SourceUnit) -> list[Finding]:
    collector = _Collector(unit)
    tree = unit.tree
    if tree is None:
        return collector.findings
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_public(node.name):
            continue
        args = [
            arg
            for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            if arg.arg not in {"self", "cls"}
        ]
        missing = [arg.arg for arg in args if arg.annotation is None]
        if missing or node.returns is None:
            parts = []
            if missing:
                parts.append("פרמטרים: " + ", ".join(missing))
            if node.returns is None:
                parts.append("ערך החזרה")
            collector.add(
                R_NO_TYPES,
                node,
                f"`{node.name}` בלי רמזי טיפוס ({'; '.join(parts)})",
                severity="info",
                hint="הוסף annotations כדי ש-IDE יתפוס שגיאות מראש.",
                confidence=0.95,
            )
    return collector.findings


_TODO_PATTERN = re.compile(r"(?i)\b(TODO|FIXME|XXX|HACK|BUG)\b[:\s]*(.*)")


def check_todos(unit: SourceUnit) -> list[Finding]:
    collector = _Collector(unit)
    try:
        tokens = tokenize.generate_tokens(io.StringIO(unit.source).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            match = _TODO_PATTERN.search(token.string)
            if match:
                collector.add(
                    R_TODO,
                    token.start[0],
                    f"{match.group(1).upper()}: {match.group(2).strip() or '(בלי תיאור)'}",
                    severity="info",
                    hint="",
                    confidence=1.0,
                )
    except (tokenize.TokenError, IndentationError, SyntaxError):  # sbpy: ignore=silent-except
        pass
    return collector.findings


# ======================================================================
# שדרוג תחביר מודרני - @MOD
# ======================================================================
R_USE_PATHLIB = _register("use-pathlib", CATEGORY_MOD)
R_MODERN_TYPING = _register("modern-type-annotations", CATEGORY_MOD)


def check_modernizer(unit: SourceUnit) -> list[Finding]:
    collector = _Collector(unit)
    tree = unit.tree
    if tree is None:
        return collector.findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name in {"os.path.join", "os.path.exists", "os.path.isfile", "os.path.isdir", "os.path.abspath"}:
                collector.add(
                    R_USE_PATHLIB,
                    node,
                    f"שימוש ב-`{name}` במקום pathlib המודרנית",
                    severity="info",
                    hint="השתמש ב-`pathlib.Path` לתחביר קריא ומודרני יותר.",
                    confidence=0.85,
                )

        if isinstance(node, ast.Subscript):
            val_name = _dotted(node.value)
            if val_name in {
                "typing.List",
                "typing.Dict",
                "typing.Set",
                "typing.Tuple",
                "typing.Union",
                "typing.Optional",
            }:
                collector.add(
                    R_MODERN_TYPING,
                    node,
                    f"שימוש ב-`{val_name}` מיושן מ-typing",
                    severity="info",
                    hint="השתמש ב-`list[...]` או `dict[...]` מובנה (Python 3.9+) או `X | None` (Python 3.10+).",
                    confidence=0.90,
                )

    return collector.findings


# ======================================================================
# הרצה מרוכזת
# ======================================================================
# check_bugs מייצר גם ממצאי style, לכן הוא מכסה שתי קטגוריות
CATEGORY_PROVIDERS = {
    CATEGORY_BUG: (check_bugs,),
    CATEGORY_STYLE: (check_bugs,),
    CATEGORY_SEC: (check_security,),
    CATEGORY_OPT: (check_performance,),
    CATEGORY_COMPLEXITY: (check_complexity,),
    CATEGORY_DOC: (check_docs,),
    CATEGORY_TYPE: (check_types,),
    CATEGORY_TODO: (check_todos,),
    CATEGORY_MOD: (check_modernizer,),
}

_register("banned-import", CATEGORY_BUG, "שימוש בספרייה שאסורה לפי חוקי הפרויקט")
_register("banned-call", CATEGORY_BUG, "קריאה לפונקציה שאסורה לפי חוקי הפרויקט")
_register("class-naming", CATEGORY_STYLE, "חריגה מכללי שמות מחלקות של הפרויקט")
_register("function-naming", CATEGORY_STYLE, "חריגה מכללי שמות פונקציות של הפרויקט")
_register("dead-code", CATEGORY_STYLE, "הגדרה שלעולם אינה בשימוש בפרויקט")
_register("circular-import", CATEGORY_BUG, "נמצא ייבוא מעגלי בין מודולים")
_register("layer-violation", CATEGORY_STYLE, "הפרת כיווניות שכבות בארכיטקטורת הפרויקט")
_register("code-clone", CATEGORY_STYLE, "פונקציה זהה מבנית לפונקציה אחרת בפרויקט")
_register("taint-vulnerability", CATEGORY_SEC, "קלט לא מסונן זורם ישירות לפונקציה רגישה")


# ``# noqa`` / ``# sbpy: ignore`` משתיקים את כל הממצאים בשורה,
# ``# sbpy: ignore=rule-a,rule-b`` / ``# sbpy: ignore[rule-a, rule-b]`` משתיק רק את החוקים שצוינו.
_SUPPRESS = re.compile(
    r"#[^\n]*?(?:noqa|sbpy\s*:\s*ignore)(?:\s*(?:[=:\[]\s*|\s+)(?P<rules>[\w\-,\s]+)\]?)?"
)
_FILE_SUPPRESS = re.compile(r"#[^\n]*?sbpy\s*:\s*(?:ignore-file|skip-file|no-scan)")


def suppressed_rules(unit: SourceUnit) -> dict[int, set[str] | None]:
    """מיפוי מספר-שורה -> חוקים מושתקים. ``None`` פירושו: הכל בשורה הזו."""
    out: dict[int, set[str] | None] = {}
    for number, text in enumerate(unit.lines, start=1):
        match = _SUPPRESS.search(text)
        if match is None:
            continue
        raw = match.group("rules")
        if raw:
            # Clean possible trailing brackets
            raw = raw.rstrip("]")
            out[number] = {item.strip() for item in raw.split(",") if item.strip()}
        else:
            out[number] = None
    return out


def _is_suppressed(finding: Finding, table: dict[int, set[str] | None]) -> bool:
    if finding.line not in table:
        return False
    rules = table[finding.line]
    return rules is None or finding.rule in rules


def analyze(unit: SourceUnit, categories: Iterable[str] | None = None) -> list[Finding]:
    """מריץ את הבדיקות של הקטגוריות המבוקשות ומחזיר ממצאים ממוינים לפי שורה."""
    # Check file-level ignore in top lines
    for line in unit.lines[:20]:
        if _FILE_SUPPRESS.search(line):
            return []

    wanted = set(categories) if categories else {CATEGORY_BUG, CATEGORY_STYLE}
    functions = []
    for category in wanted:
        for func in CATEGORY_PROVIDERS.get(category, ()):
            if func not in functions:
                functions.append(func)

    findings: list[Finding] = []
    for func in functions:
        try:
            findings.extend(func(unit))
        except Exception:  # pragma: no cover - בדיקה שנכשלת לא מפילה את הסריקה
            if os.environ.get("SBPY_DEBUG"):
                raise
            continue

    try:
        from ..rules import check_project_rules

        findings.extend(check_project_rules(unit))
    except Exception:  # sbpy: ignore=silent-except
        pass

    findings = [f for f in findings if RULE_CATEGORY.get(f.rule, CATEGORY_BUG) in wanted]
    
    # Filter by global ignore_rules in config if available
    try:
        from ..config import get_config

        ignored_global = set(get_config().ignore_rules or [])
        if ignored_global:
            findings = [f for f in findings if f.rule not in ignored_global]
    except Exception:  # sbpy: ignore=silent-except
        pass

    table = suppressed_rules(unit)
    if table:
        findings = [f for f in findings if not _is_suppressed(f, table)]
    seen: set[tuple[str, int, int]] = set()
    unique: list[Finding] = []
    for finding in sorted(findings, key=lambda f: (f.line, f.col, f.rule)):
        key = (finding.rule, finding.line, finding.col)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def rules_by_category() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for rule, category in RULE_CATEGORY.items():
        grouped.setdefault(category, []).append(rule)
    return {key: sorted(value) for key, value in sorted(grouped.items())}

