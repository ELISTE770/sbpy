"""שכבה 2.5: בסיס ידע מקומי של שגיאות פייתון נפוצות.

השכבה הזו נכנסת אחרי המתקנים המקומיים ולפני Gemini. היא מכסה שגיאות
שאי אפשר לפתור בהתאמת שמות, אבל התשובה שלהן קבועה וידועה - ולכן חבל
לשלם עליה. כל ערך הוא ביטוי רגולרי על ``"ExcType: message"``.

הרחבה: ``~/.sbpy/knowledge.json`` עם רשימת אובייקטים באותו מבנה.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import Config, get_config
from .results import Diagnosis


@dataclass
class Entry:
    pattern: str
    title_he: str
    fix_he: str
    title_en: str = ""
    fix_en: str = ""
    confidence: float = 0.80
    tag: str = ""

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.IGNORECASE)


def _e(pattern: str, title: str, fix: str, *, en: tuple[str, str] = ("", ""), conf: float = 0.80, tag: str = "") -> Entry:
    return Entry(pattern, title, fix, en[0], en[1], conf, tag)


# ----------------------------------------------------------------------
ENTRIES: list[Entry] = [
    # --- טיפוסים ומבני נתונים ---
    _e(
        r"list indices must be integers or slices, not str",
        "ניגשת לרשימה עם מפתח טקסט",
        "אם התכוונת למילון - בדוק מה באמת חזר. אם זו רשימה של מילונים, צריך קודם אינדקס: `rows[0]['name']`.",
        en=("Indexing a list with a string key", "If you expected a dict, check what was returned. For a list of dicts index first: `rows[0]['name']`."),
        conf=0.86,
    ),
    _e(
        r"string indices must be integers",
        "ניגשת למחרוזת כאילו הייתה מילון",
        "כנראה `json.loads` לא הורץ, או שהורץ פעמיים והוחזר טקסט. בדוק את הטיפוס עם `type(x)`.",
        en=("Indexing a string as if it were a dict", "Probably `json.loads` was skipped or applied twice. Check with `type(x)`."),
        conf=0.86,
    ),
    _e(
        r"unhashable type: '(list|dict|set|bytearray)'",
        "אי אפשר להשתמש ברשימה/מילון כמפתח או באיברי set",
        "המר ל-`tuple` (`tuple(items)`) או ל-`frozenset`.",
        en=("A list/dict cannot be a dict key or set member", "Convert with `tuple(items)` or `frozenset(...)`."),
        conf=0.90,
    ),
    _e(
        r"'(tuple|str|bytes|frozenset)' object does not support item assignment",
        "הטיפוס הזה הוא immutable - אי אפשר לשנות אותו במקום",
        "בנה עותק חדש: לרשימה `list(x)`, למחרוזת `x[:i] + new + x[i+1:]` או `''.join(parts)`.",
        en=("This type is immutable", "Build a new value: `list(x)` for tuples, slicing or `''.join(parts)` for strings."),
        conf=0.90,
    ),
    _e(
        r"object of type 'NoneType' has no len\(\)",
        "קיבלת None במקום רצף",
        "הפונקציה שהחזירה את הערך לא החזירה כלום בכל המסלולים. בדוק שיש `return` בכל ענף.",
        en=("Got None instead of a sequence", "The producing function returns nothing on some path. Ensure every branch returns."),
        conf=0.86,
    ),
    _e(
        r"'NoneType' object is not (iterable|subscriptable)",
        "ניסית לעבור על None או לגשת אליו באינדקס",
        "בדוק מה החזירה הפונקציה הקודמת. `re.match` מחזיר None כשאין התאמה, ו-`dict.get` כשאין מפתח.",
        en=("Iterating or indexing None", "Check the previous call. `re.match` returns None on no match, `dict.get` on a missing key."),
        conf=0.86,
    ),
    _e(
        r"can't multiply sequence by non-int",
        "ניסית להכפיל טקסט או רשימה במספר עשרוני",
        "המר למספר: `int(x)` או `float(x)` לפני הכפל.",
        en=("Multiplying a sequence by a non-int", "Convert with `int(x)` or `float(x)` first."),
        conf=0.88,
    ),
    _e(
        r"unsupported format string passed to",
        "פורמט לא מתאים לטיפוס",
        "`:.2f` עובד רק על מספרים. המר קודם, או השתמש ב-`{x}` בלי פורמט.",
        en=("Format spec does not match the type", "`:.2f` only works on numbers. Convert first or drop the spec."),
        conf=0.85,
    ),
    # --- לולאות ואוספים ---
    _e(
        r"dictionary changed size during iteration",
        "שינית את המילון בזמן שרצת עליו",
        "רוץ על עותק: `for key in list(d):`.",
        en=("Modified a dict while iterating it", "Iterate a copy: `for key in list(d):`."),
        conf=0.93,
    ),
    _e(
        r"Set changed size during iteration",
        "שינית את ה-set בזמן שרצת עליו",
        "רוץ על עותק: `for item in set(values):`.",
        en=("Modified a set while iterating it", "Iterate a copy: `for item in set(values):`."),
        conf=0.93,
    ),
    _e(
        r"list\.remove\(x\): x not in list",
        "ניסית להסיר איבר שלא קיים ברשימה",
        "בדוק לפני: `if x in items: items.remove(x)`. שים לב שהסרה בתוך לולאה מדלגת על איברים.",
        en=("Removing an item that is not in the list", "Guard with `if x in items:`. Removing while looping also skips items."),
        conf=0.90,
    ),
    _e(
        r"pop from empty (list|set)",
        "ניסית להוציא איבר ממבנה ריק",
        "בדוק `if items:` לפני, או השתמש ב-`items.pop() if items else default`.",
        en=("Popping from an empty container", "Check `if items:` first, or use a default."),
        conf=0.90,
    ),
    _e(
        r"dictionary update sequence element",
        "ניסית לבנות מילון ממבנה לא מתאים",
        "`dict()` מצפה לזוגות. השתמש ב-`dict(zip(keys, values))` או ב-`json.loads` אם זה טקסט.",
        en=("Building a dict from an unsuitable structure", "`dict()` expects pairs. Use `dict(zip(keys, values))` or `json.loads`."),
        conf=0.85,
    ),
    # --- תחביר וקריאות ---
    _e(
        r"positional argument follows keyword argument",
        "ארגומנט רגיל אחרי ארגומנט עם שם",
        "העבר את כל הארגומנטים ללא שם לתחילת הקריאה.",
        en=("Positional argument after a keyword argument", "Move all positional arguments to the front."),
        conf=0.95,
    ),
    _e(
        r"takes \d+ positional arguments? but \d+ (was|were) given",
        "מספר הארגומנטים לא תואם לחתימה",
        "אם זו מתודה - ייתכן ששכחת `self`, או שקראת דרך המחלקה במקום דרך מופע.",
        en=("Argument count does not match the signature", "For a method, check `self` or that you called it on an instance."),
        conf=0.82,
    ),
    _e(
        r"__init__\(\) should return None",
        "`__init__` מחזיר ערך",
        "`__init__` בונה את האובייקט ולא מחזיר אותו. הסר את ה-`return`.",
        en=("`__init__` returns a value", "`__init__` must not return anything. Remove the `return`."),
        conf=0.95,
    ),
    # --- ייבוא ---
    _e(
        r"attempted relative import with no known parent package",
        "import יחסי בקובץ שרץ ישירות",
        "הרץ כמודול: `python -m package.module`, או החלף ל-import מוחלט.",
        en=("Relative import in a directly-run file", "Run as a module: `python -m package.module`, or use absolute imports."),
        conf=0.92,
    ),
    _e(
        r"most likely due to a circular import",
        "ייבוא מעגלי",
        "העבר את ה-import לתוך הפונקציה שצריכה אותו, או הוצא את הקוד המשותף למודול שלישי.",
        en=("Circular import", "Move the import inside the function that needs it, or extract shared code to a third module."),
        conf=0.92,
    ),
    _e(
        r"No module named '(src|app|tests?|lib)'",
        "פייתון לא מוצא את תיקיית הפרויקט",
        "הרץ מהשורש עם `python -m ...`, או התקן את הפרויקט עם `pip install -e .`.",
        en=("Python cannot find the project directory", "Run from the root with `python -m ...`, or `pip install -e .`."),
        conf=0.80,
    ),
    # --- קבצים ומערכת ---
    _e(
        r"\[Errno 13\]|Permission denied",
        "אין הרשאה לגשת לקובץ",
        "הקובץ פתוח בתוכנה אחרת, או שהוא לקריאה בלבד. סגור אותו ובדוק הרשאות.",
        en=("No permission to access the file", "The file may be open elsewhere or read-only."),
        conf=0.85,
    ),
    _e(
        r"WinError 32|being used by another process",
        "הקובץ נעול על ידי תהליך אחר",
        "ב-Windows אי אפשר למחוק או לשנות שם לקובץ פתוח. ודא שכל `open` נסגר (עדיף עם `with`).",
        en=("The file is locked by another process", "On Windows an open file cannot be deleted or renamed. Use `with open(...)`."),
        conf=0.88,
    ),
    _e(
        r"codec can't decode byte",
        "הקובץ אינו בקידוד שציינת",
        "נסה `encoding='utf-8'`, ולקובץ עברי ישן `cp1255`. כמוצא אחרון `errors='replace'`.",
        en=("The file is not in the encoding you specified", "Try `encoding='utf-8'`, or `cp1255` for legacy Hebrew files."),
        conf=0.85,
    ),
    _e(
        r"codec can't encode character",
        "ניסית לכתוב תו שהקידוד לא תומך בו",
        "פתח לכתיבה עם `encoding='utf-8'`, ובטרמינל הגדר `PYTHONIOENCODING=utf-8`.",
        en=("Writing a character the encoding cannot represent", "Open with `encoding='utf-8'` and set `PYTHONIOENCODING=utf-8`."),
        conf=0.88,
    ),
    # --- רשת ---
    _e(
        r"CERTIFICATE_VERIFY_FAILED",
        "אימות תעודת TLS נכשל",
        "לרוב פרוקסי או תוכנת סינון שמפענחת TLS. השתמש במאגר התעודות של המערכת (`ssl.create_default_context()`), לא ב-certifi בלבד.",
        en=("TLS certificate verification failed", "Usually a TLS-inspecting proxy. Use the OS trust store via `ssl.create_default_context()`."),
        conf=0.88,
    ),
    _e(
        r"Only one usage of each socket address|Address already in use|\[Errno 98\]",
        "הפורט תפוס",
        "תהליך אחר מאזין באותו פורט. סגור אותו, או בחר פורט אחר.",
        en=("The port is already in use", "Another process is listening. Stop it or pick another port."),
        conf=0.90,
    ),
    # --- asyncio ---
    _e(
        r"coroutine.*was never awaited|'coroutine' object is not",
        "קראת לפונקציית async בלי await",
        "הוסף `await`, או הרץ עם `asyncio.run(main())`.",
        en=("Called an async function without awaiting", "Add `await`, or run it with `asyncio.run(main())`."),
        conf=0.92,
    ),
    _e(
        r"asyncio\.run\(\) cannot be called from a running event loop|This event loop is already running",
        "כבר רץ event loop",
        "בתוך Jupyter או שרת async השתמש ב-`await main()` ישירות, לא ב-`asyncio.run`.",
        en=("An event loop is already running", "Inside Jupyter or an async server use `await main()` directly."),
        conf=0.90,
    ),
    # --- מסדי נתונים ---
    _e(
        r"database is locked",
        "SQLite נעול על ידי חיבור אחר",
        "סגור חיבורים פתוחים, בצע `commit()`, והוסף `timeout=` ל-`connect`.",
        en=("SQLite is locked by another connection", "Close open connections, `commit()`, and add `timeout=` to `connect`."),
        conf=0.88,
    ),
    _e(
        r"no such table",
        "הטבלה לא קיימת",
        "ודא ש-`CREATE TABLE` רץ, ושאתה מתחבר לאותו קובץ מסד נתונים (נתיב יחסי נפתר מתיקיית העבודה).",
        en=("The table does not exist", "Ensure `CREATE TABLE` ran and that you connect to the same database file."),
        conf=0.88,
    ),
    _e(
        r"UNIQUE constraint failed",
        "ניסית להכניס ערך שכבר קיים בעמודה ייחודית",
        "השתמש ב-`INSERT OR REPLACE` / `ON CONFLICT`, או בדוק קיום לפני ההכנסה.",
        en=("Inserting a duplicate value into a unique column", "Use `INSERT OR REPLACE` / `ON CONFLICT`, or check first."),
        conf=0.90,
    ),
    # --- JSON ---
    _e(
        r"Object of type \w+ is not JSON serializable",
        "טיפוס שאין ל-JSON ייצוג עבורו",
        "`json.dumps(data, default=str)`, או המר ידנית (`datetime.isoformat()`, `list(set_value)`).",
        en=("A type JSON cannot represent", "Use `json.dumps(data, default=str)` or convert manually."),
        conf=0.90,
    ),
    _e(
        r"Expecting value: line 1 column 1",
        "התוכן שניסית לפענח אינו JSON",
        "לרוב תגובת שגיאה של שרת או קובץ ריק. הדפס את הטקסט הגולמי לפני `json.loads`.",
        en=("The content is not JSON", "Usually a server error page or an empty file. Print the raw text first."),
        conf=0.88,
    ),
    _e(
        r"Extra data: line",
        "יש יותר מאובייקט JSON אחד בקובץ",
        "אם זה JSONL - קרא שורה-שורה: `[json.loads(line) for line in file]`.",
        en=("More than one JSON object in the input", "For JSONL parse line by line."),
        conf=0.88,
    ),
    # --- ספריות נפוצות ---
    _e(
        r"main thread is not in main loop",
        "עדכנת ממשק Tkinter מתוך thread אחר",
        "Tkinter חייב לרוץ ב-thread הראשי. השתמש ב-`widget.after(0, callback)` כדי לעדכן.",
        en=("Updated Tkinter from another thread", "Tkinter must run on the main thread; use `widget.after(0, callback)`."),
        conf=0.90,
    ),
    _e(
        r"Working outside of (application|request) context",
        "גישה להקשר של Flask מחוץ לבקשה",
        "עטוף ב-`with app.app_context():`.",
        en=("Flask context accessed outside a request", "Wrap in `with app.app_context():`."),
        conf=0.90,
    ),
    _e(
        r"CUDA out of memory",
        "אין מספיק זיכרון GPU",
        "הקטן batch size, הוסף `torch.no_grad()` בהסקה, וקרא ל-`torch.cuda.empty_cache()`.",
        en=("GPU out of memory", "Reduce batch size, use `torch.no_grad()` for inference, and `empty_cache()`."),
        conf=0.88,
    ),
    _e(
        r"Expected all tensors to be on the same device",
        "טנזורים על מכשירים שונים",
        "העבר הכל לאותו מכשיר: `tensor.to(device)` גם לקלט וגם למודל.",
        en=("Tensors on different devices", "Move everything with `tensor.to(device)`."),
        conf=0.90,
    ),
    _e(
        r"DataFrame' object has no attribute '(\w+)'",
        "אין עמודה או מתודה בשם הזה ב-DataFrame",
        "גישה לעמודה עם רווח או תו מיוחד חייבת להיות `df['name']`. בדוק `df.columns`.",
        en=("No such column or method on the DataFrame", "Use `df['name']` for odd column names; check `df.columns`."),
        conf=0.82,
    ),
    _e(
        r"truth value of a (Series|DataFrame|array) is ambiguous",
        "השתמשת ב-if על מבנה שלם",
        "השתמש ב-`.any()` / `.all()`, או ב-`&` ו-`|` עם סוגריים במקום `and` ו-`or`.",
        en=("Used `if` on a whole Series/array", "Use `.any()` / `.all()`, or `&` / `|` with parentheses."),
        conf=0.90,
    ),
]


_extra_loaded = False


def _load_extra(config: Config) -> None:
    """טוען ערכים נוספים מ-``~/.sbpy/knowledge.json`` פעם אחת."""
    global _extra_loaded
    if _extra_loaded:
        return
    _extra_loaded = True
    path = config.home / "knowledge.json"
    try:
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as handle:
            rows = json.load(handle)
    except (OSError, ValueError):
        return
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict) or not row.get("pattern"):
            continue
        try:
            re.compile(str(row["pattern"]))
        except re.error:
            continue
        ENTRIES.append(
            Entry(
                pattern=str(row["pattern"]),
                title_he=str(row.get("title_he") or row.get("title") or ""),
                fix_he=str(row.get("fix_he") or row.get("fix") or ""),
                title_en=str(row.get("title_en") or ""),
                fix_en=str(row.get("fix_en") or ""),
                confidence=float(row.get("confidence") or 0.8),
                tag=str(row.get("tag") or "custom"),
            )
        )


def lookup(exc_type: str, message: str, *, config: Config | None = None) -> Diagnosis | None:
    """מחפש התאמה בבסיס הידע. מחזיר ``Diagnosis`` או None."""
    config = config or get_config()
    _load_extra(config)
    haystack = f"{exc_type}: {message}"
    lang = config.language

    for entry in ENTRIES:
        try:
            if not entry.compiled().search(haystack):
                continue
        except re.error:  # pragma: no cover
            continue
        title = entry.title_he if lang == "he" else (entry.title_en or entry.title_he)
        fix = entry.fix_he if lang == "he" else (entry.fix_en or entry.fix_he)
        return Diagnosis(
            title=title,
            suggestion=fix,
            confidence=entry.confidence,
            source="local",
            rule=f"kb.{entry.tag or 'builtin'}",
            meta={"kind": "knowledge", "pattern": entry.pattern},
        )
    return None


def size() -> int:
    return len(ENTRIES)


def describe(config: Config | None = None) -> dict[str, Any]:
    config = config or get_config()
    _load_extra(config)
    return {
        "entries": len(ENTRIES),
        "custom_file": str(config.home / "knowledge.json"),
    }
