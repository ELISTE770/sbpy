"""קטלוג הודעות דו-לשוני (עברית/אנגלית).

השפה נקבעת ב-``Config.language`` (``SBPY_LANG=he|en``).
"""

from __future__ import annotations

CATALOG: dict[str, dict[str, str]] = {
    # ---------- NameError ----------
    "name.typo.title": {
        "he": "שם לא מוגדר: `{name}`",
        "en": "Undefined name: `{name}`",
    },
    "name.typo.suggestion": {
        "he": "האם התכוונת ל-`{best}`?",
        "en": "Did you mean `{best}`?",
    },
    "name.import.title": {
        "he": "`{name}` הוא מודול - חסר import",
        "en": "`{name}` is a module - missing import",
    },
    "name.import.suggestion": {
        "he": "הוסף בראש הקובץ: `import {name}`",
        "en": "Add at the top of the file: `import {name}`",
    },
    "name.module.title": {
        "he": "`{name}` לא מוגדר - נראה כמו שם של מודול עם טעות כתיב",
        "en": "`{name}` is not defined - looks like a misspelled module name",
    },
    "name.module.suggestion": {
        "he": "הוסף `import {best}` והשתמש ב-`{best}`.",
        "en": "Add `import {best}` and use `{best}`.",
    },
    "name.project.title": {
        "he": "`{name}` מוגדר בפרויקט, אבל לא מיובא לקובץ הזה",
        "en": "`{name}` is defined in the project, but not imported here",
    },
    "name.project.suggestion": {
        "he": "הוסף: `{statement}`",
        "en": "Add: `{statement}`",
    },
    "name.project.detail": {
        "he": "ההגדרה נמצאת ב-{location}.",
        "en": "Defined at {location}.",
    },
    "name.generic.title": {
        "he": "השם `{name}` לא הוגדר לפני השימוש",
        "en": "The name `{name}` is not defined before use",
    },
    "name.generic.detail": {
        "he": "לא נמצא שם דומה בהיקף הנוכחי. בדוק איות, import חסר, או הגדרה בהיקף אחר.",
        "en": "No similar name found in scope. Check spelling, a missing import, or a definition in another scope.",
    },
    "name.later.title": {
        "he": "`{name}` מוגדר בקובץ, אבל אחרי השורה הזו",
        "en": "`{name}` is defined in the file, but after this line",
    },
    "name.later.suggestion": {
        "he": "ההגדרה נמצאת בשורה {line}. העבר אותה למעלה או קרא לה מאוחר יותר.",
        "en": "The definition is at line {line}. Move it up or call it later.",
    },
    # ---------- AttributeError ----------
    "attr.typo.title": {
        "he": "לאובייקט `{owner}` אין תכונה `{attr}`",
        "en": "`{owner}` has no attribute `{attr}`",
    },
    "attr.typo.suggestion": {
        "he": "האם התכוונת ל-`{best}`?",
        "en": "Did you mean `{best}`?",
    },
    "attr.none.title": {
        "he": "האובייקט הוא None - כנראה פונקציה שלא החזירה ערך",
        "en": "The object is None - probably a function that returned nothing",
    },
    "attr.none.suggestion": {
        "he": "בדוק שהפונקציה שיצרה את `{owner}` באמת מכילה `return`. מתודות כמו `sort()` ו-`append()` מחזירות None.",
        "en": "Check that the function producing `{owner}` actually returns a value. Methods like `sort()` and `append()` return None.",
    },
    "attr.generic.title": {
        "he": "תכונה חסרה: `{attr}` על טיפוס `{owner}`",
        "en": "Missing attribute: `{attr}` on type `{owner}`",
    },
    "attr.candidates.detail": {
        "he": "תכונות קיימות דומות: {items}",
        "en": "Similar existing attributes: {items}",
    },
    # ---------- ImportError ----------
    "import.pip.title": {
        "he": "החבילה `{module}` לא מותקנת",
        "en": "Package `{module}` is not installed",
    },
    "import.pip.suggestion": {
        "he": "התקן עם: `pip install {package}`",
        "en": "Install with: `pip install {package}`",
    },
    "import.typo.title": {
        "he": "המודול `{module}` לא נמצא - ייתכן שזו טעות כתיב",
        "en": "Module `{module}` not found - possibly a typo",
    },
    "import.typo.suggestion": {
        "he": "האם התכוונת ל-`{best}`?",
        "en": "Did you mean `{best}`?",
    },
    "import.name.title": {
        "he": "`{name}` לא קיים בתוך `{module}`",
        "en": "`{name}` does not exist inside `{module}`",
    },
    "import.self.title": {
        "he": "התנגשות שם: קובץ מקומי בשם `{module}.py` מסתיר את החבילה",
        "en": "Name clash: a local file named `{module}.py` shadows the real package",
    },
    "import.self.suggestion": {
        "he": "שנה את שם הקובץ המקומי `{path}`.",
        "en": "Rename the local file `{path}`.",
    },
    # ---------- KeyError ----------
    "key.typo.title": {
        "he": "המפתח `{key}` לא קיים במילון",
        "en": "Key `{key}` is not in the dict",
    },
    "key.typo.suggestion": {
        "he": "האם התכוונת ל-`{best}`?",
        "en": "Did you mean `{best}`?",
    },
    "key.generic.title": {
        "he": "מפתח חסר: `{key}`",
        "en": "Missing key: `{key}`",
    },
    "key.generic.suggestion": {
        "he": "השתמש ב-`.get(...)` כדי לקבל None במקום שגיאה, או בדוק `in` לפני הגישה.",
        "en": "Use `.get(...)` to get None instead of an error, or check with `in` first.",
    },
    "key.keys.detail": {
        "he": "מפתחות קיימים: {items}",
        "en": "Existing keys: {items}",
    },
    "key.casing.suggestion": {
        "he": "קיים מפתח `{best}` - ההבדל הוא רק באותיות גדולות/קטנות.",
        "en": "A key `{best}` exists - only the letter case differs.",
    },
    # ---------- IndexError ----------
    "index.title": {
        "he": "אינדקס מחוץ לתחום",
        "en": "Index out of range",
    },
    "index.detail": {
        "he": "האורך של `{owner}` הוא {length}, האינדקס החוקי האחרון הוא {last}.",
        "en": "`{owner}` has length {length}; the last valid index is {last}.",
    },
    "index.empty.detail": {
        "he": "`{owner}` ריק לחלוטין (אורך 0).",
        "en": "`{owner}` is completely empty (length 0).",
    },
    "index.suggestion": {
        "he": "בדוק את הגבול עם `if len(...) > i:` או השתמש ב-`enumerate`.",
        "en": "Guard with `if len(...) > i:` or use `enumerate`.",
    },
    # ---------- TypeError ----------
    "type.kwarg.title": {
        "he": "הפרמטר `{kwarg}` לא קיים ב-`{func}`",
        "en": "`{func}` has no parameter `{kwarg}`",
    },
    "type.kwarg.suggestion": {
        "he": "האם התכוונת ל-`{best}`?",
        "en": "Did you mean `{best}`?",
    },
    "type.params.detail": {
        "he": "פרמטרים אפשריים: {items}",
        "en": "Available parameters: {items}",
    },
    "type.missing.title": {
        "he": "חסרים ארגומנטים ל-`{func}`: {items}",
        "en": "Missing arguments for `{func}`: {items}",
    },
    "type.missing.detail": {
        "he": "החתימה היא `{signature}`.",
        "en": "The signature is `{signature}`.",
    },
    "type.operand.title": {
        "he": "אי אפשר לבצע `{op}` בין `{left}` ל-`{right}`",
        "en": "Cannot apply `{op}` between `{left}` and `{right}`",
    },
    "type.operand.suggestion": {
        "he": "המר במפורש: {hint}",
        "en": "Convert explicitly: {hint}",
    },
    "type.callable.title": {
        "he": "האובייקט מטיפוס `{owner}` אינו ניתן לקריאה",
        "en": "Object of type `{owner}` is not callable",
    },
    "type.callable.suggestion": {
        "he": "סיבות נפוצות: סוגריים מיותרים, משתנה שדרס שם של פונקציה, או פסיק חסר בין איברים.",
        "en": "Common causes: extra parentheses, a variable shadowing a function name, or a missing comma between items.",
    },
    "type.subscript.title": {
        "he": "אי אפשר להשתמש ב-`[]` על טיפוס `{owner}`",
        "en": "Type `{owner}` does not support `[]`",
    },
    "type.subscript.suggestion": {
        "he": "אם זו פונקציה - השתמש בסוגריים עגולים. אם זה None - בדוק מה הוחזר קודם.",
        "en": "If it is a function use round parentheses. If it is None, check what was returned earlier.",
    },
    "type.notiterable.title": {
        "he": "`{owner}` אינו ניתן לאיטרציה",
        "en": "`{owner}` is not iterable",
    },
    "type.notiterable.suggestion": {
        "he": "אם זה מספר - עטוף ב-`range(...)`. אם זה None - בדוק את הערך שהוחזר.",
        "en": "If it is a number, wrap it in `range(...)`. If it is None, check the returned value.",
    },
    # ---------- ValueError ----------
    "value.int.title": {
        "he": "אי אפשר להמיר את `{raw}` למספר שלם",
        "en": "Cannot convert `{raw}` to an integer",
    },
    "value.int.suggestion": {
        "he": "נסה `int(float(x))` למספר עשרוני, או `x.strip()` אם יש רווחים או תו שורה.",
        "en": "Try `int(float(x))` for decimals, or `x.strip()` for stray whitespace.",
    },
    "value.unpack.title": {
        "he": "פריקה לא תואמת: התקבלו {got} ערכים, נדרשו {want}",
        "en": "Unpacking mismatch: got {got} values, expected {want}",
    },
    "value.unpack.suggestion": {
        "he": "השתמש ב-`*rest` לקליטת השאר, או בדוק את מקור הנתונים.",
        "en": "Use `*rest` to absorb the extras, or check the data source.",
    },
    # ---------- ZeroDivisionError ----------
    "zero.title": {
        "he": "חלוקה באפס",
        "en": "Division by zero",
    },
    "zero.suggestion": {
        "he": "הגן על החלוקה: `x / y if y else 0`.",
        "en": "Guard the division: `x / y if y else 0`.",
    },
    # ---------- FileNotFoundError ----------
    "file.typo.title": {
        "he": "הקובץ `{name}` לא נמצא - קיים קובץ בשם דומה",
        "en": "File `{name}` not found - a similarly named file exists",
    },
    "file.typo.suggestion": {
        "he": "האם התכוונת ל-`{best}`?",
        "en": "Did you mean `{best}`?",
    },
    "file.generic.title": {
        "he": "הקובץ לא נמצא: `{name}`",
        "en": "File not found: `{name}`",
    },
    "file.cwd.detail": {
        "he": "תיקיית העבודה הנוכחית היא `{cwd}`. נתיב יחסי נפתר ממנה, לא מתיקיית הסקריפט.",
        "en": "The current working directory is `{cwd}`. Relative paths resolve from there, not from the script folder.",
    },
    "file.dirmissing.detail": {
        "he": "התיקייה `{parent}` עצמה לא קיימת.",
        "en": "The directory `{parent}` itself does not exist.",
    },
    # ---------- Unicode ----------
    "unicode.title": {
        "he": "בעיית קידוד בקריאת הקובץ",
        "en": "Encoding problem while reading the file",
    },
    "unicode.suggestion": {
        "he": "פתח עם קידוד מפורש: `open(path, encoding='utf-8')`. לקובץ עברי ישן נסה `cp1255`.",
        "en": "Open with an explicit encoding: `open(path, encoding='utf-8')`; for legacy files try `cp1255` or `latin-1`.",
    },
    # ---------- JSON ----------
    "json.title": {
        "he": "JSON לא תקין",
        "en": "Invalid JSON",
    },
    "json.suggestion": {
        "he": "בדוק פסיק עודף, מרכאות בודדות במקום כפולות, או תגובת שרת שאינה JSON.",
        "en": "Check for a trailing comma, single quotes instead of double, or a non-JSON server response.",
    },
    # ---------- UnboundLocal ----------
    "unbound.title": {
        "he": "`{name}` בשימוש לפני ההשמה בתוך הפונקציה",
        "en": "`{name}` is used before assignment inside the function",
    },
    "unbound.suggestion": {
        "he": "אם הכוונה למשתנה חיצוני - הוסף `global {name}` או `nonlocal {name}`. אחרת אתחל אותו בתחילת הפונקציה.",
        "en": "If you meant the outer variable, add `global {name}` or `nonlocal {name}`. Otherwise initialize it first.",
    },
    # ---------- Recursion ----------
    "recursion.title": {
        "he": "רקורסיה אינסופית",
        "en": "Infinite recursion",
    },
    "recursion.suggestion": {
        "he": "חסר תנאי עצירה, או שהקריאה הרקורסיבית לא מקטינה את הקלט.",
        "en": "A base case is missing, or the recursive call does not shrink the input.",
    },
    # ---------- Network ----------
    "network.title": {
        "he": "כשל בחיבור לרשת",
        "en": "Network connection failed",
    },
    "network.suggestion": {
        "he": "בדוק חיבור, כתובת URL, פרוקסי או חומת אש. הוסף `timeout=` לבקשה.",
        "en": "Check connectivity, the URL, a proxy or a firewall. Add `timeout=` to the request.",
    },
    # ---------- Syntax ----------
    "syntax.paren.title": {
        "he": "סוגריים לא מאוזנים",
        "en": "Unbalanced brackets",
    },
    "syntax.paren.suggestion": {
        "he": "חסר `{missing}` - בדרך כלל הבעיה מתחילה בשורה {line}.",
        "en": "Missing `{missing}` - the problem usually starts at line {line}.",
    },
    "syntax.colon.title": {
        "he": "חסרות נקודתיים בסוף השורה",
        "en": "Missing colon at end of line",
    },
    "syntax.colon.suggestion": {
        "he": "הוסף `:` בסוף השורה.",
        "en": "Add `:` at the end of the line.",
    },
    "syntax.assign.title": {
        "he": "שימוש ב-`=` במקום `==` בתוך תנאי",
        "en": "Used `=` instead of `==` in a condition",
    },
    "syntax.print2.title": {
        "he": "תחביר של Python 2",
        "en": "Python 2 syntax",
    },
    "syntax.print2.suggestion": {
        "he": "השתמש ב-`print(...)` עם סוגריים.",
        "en": "Use `print(...)` with parentheses.",
    },
    # ---------- Assertion ----------
    "assert.title": {
        "he": "טענת assert נכשלה",
        "en": "Assertion failed",
    },
    "assert.suggestion": {
        "he": "הדפס את הערכים שנבדקו לפני ה-assert כדי לראות מה באמת התקבל.",
        "en": "Print the compared values before the assert to see what actually arrived.",
    },
    "generic.title": {
        "he": "{exc_type}: {message}",
        "en": "{exc_type}: {message}",
    },
    # ---------- תצוגה ----------
    "ui.header": {
        "he": "SBpy · אבחון שגיאה",
        "en": "SBpy · error diagnosis",
    },
    "ui.local_only": {
        "he": "נפתר מקומית - ללא פנייה ל-Gemini",
        "en": "Solved locally - no Gemini call",
    },
    "ui.escalated": {
        "he": "הוסלם ל-Gemini ({reason})",
        "en": "Escalated to Gemini ({reason})",
    },
    "ui.cache_hit": {
        "he": "מהמטמון - ללא פנייה ל-Gemini",
        "en": "From cache - no Gemini call",
    },
    "ui.no_diagnosis": {
        "he": "לא נמצאה אבחנה מקומית.",
        "en": "No local diagnosis found.",
    },
    "ui.offline": {
        "he": "מצב offline - Gemini מנוטרל",
        "en": "Offline mode - Gemini disabled",
    },
    "ui.no_key": {
        "he": "אין מפתח API (GEMINI_API_KEY)",
        "en": "No API key (GEMINI_API_KEY)",
    },
    "ui.no_sdk": {
        "he": "החבילה google-genai לא מותקנת",
        "en": "The google-genai package is not installed",
    },
    "ui.budget": {
        "he": "התקציב מוצה ({used}/{limit})",
        "en": "Budget exhausted ({used}/{limit})",
    },
    "ui.suggestion_label": {
        "he": "הצעה",
        "en": "Suggestion",
    },
    "ui.detail_label": {
        "he": "פרטים",
        "en": "Details",
    },
    "ui.patch_label": {
        "he": "תיקון מוצע",
        "en": "Proposed fix",
    },
    "ui.retry.success": {
        "he": "SBpy תיקן אוטומטית: {what} · ההרצה החוזרת הצליחה",
        "en": "SBpy auto-fixed: {what} · retry succeeded",
    },
    "ui.no_findings": {
        "he": "לא נמצאו ממצאים.",
        "en": "No findings.",
    },
    # ---------- Asyncio / Concurrency ----------
    "async.loop_running.title": {
        "he": "לולאת האירועים (Event Loop) כבר רצה",
        "en": "Event loop is already running",
    },
    "async.loop_running.suggestion": {
        "he": "בסביבה אסינכרונית, השתמש ב-`await` ישיר במקום `asyncio.run()`, או השתמש ב-`nest_asyncio`.",
        "en": "In an async environment, use direct `await` instead of `asyncio.run()`, or use `nest_asyncio`.",
    },
    "async.not_awaited.title": {
        "he": "פונקציה אסינכרונית `{func}` נקראה ללא `await`",
        "en": "Async function `{func}` was called without `await`",
    },
    "async.not_awaited.suggestion": {
        "he": "הוסף `await` לפני הקריאה לפונקציה: `await {func}(...)`",
        "en": "Add `await` before calling the function: `await {func}(...)`",
    },
    "async.not_awaitable.title": {
        "he": "ניסיון לבצע `await` על אובייקט שאינו אסינכרוני",
        "en": "Attempted to `await` a non-awaitable object",
    },
    "async.not_awaitable.suggestion": {
        "he": "הסר את ה-`await` או ודא שהפונקציה מוגדרת כ-`async def`.",
        "en": "Remove `await` or verify the function is declared as `async def`.",
    },
    # ---------- Database / SQLite ----------
    "db.no_table.title": {
        "he": "הטבלה `{table}` אינה קיימת במסד הנתונים",
        "en": "Table `{table}` does not exist in database",
    },
    "db.no_table.suggestion": {
        "he": "ודא שפקודת יצירת הטבלה (CREATE TABLE) הורצה או בדוק שגיאות איות.",
        "en": "Ensure CREATE TABLE was executed or check for table name typos.",
    },
    "db.no_column.title": {
        "he": "העמודה `{column}` אינה קיימת בטבלה",
        "en": "Column `{column}` does not exist in table",
    },
    "db.no_column.suggestion": {
        "he": "בדוק את שמות העמודות בטבלה או האם חסרה מיגרציה של הסכמה.",
        "en": "Check table column names or if a schema migration is missing.",
    },
    "db.locked.title": {
        "he": "מסד הנתונים נעול (Database is locked)",
        "en": "Database is locked",
    },
    "db.locked.suggestion": {
        "he": "ודא שטרנזקציות קודמות נסגרו (commit/close) או הגדל את ה-timeout.",
        "en": "Ensure previous transactions are closed (commit/close) or increase timeout.",
    },
    # ---------- Pandas / DataFrames ----------
    "pandas.column_typo.title": {
        "he": "העמודה `{column}` אינה קיימת ב-DataFrame",
        "en": "Column `{column}` does not exist in DataFrame",
    },
    "pandas.column_typo.suggestion": {
        "he": "האם התכוונת לעמודה `{best}`? עמודות זמינות: {available}",
        "en": "Did you mean column `{best}`? Available columns: {available}",
    },
    # ---------- Pydantic ----------
    "pydantic.validation.title": {
        "he": "שגיאת ולידציה ב-Pydantic: {message}",
        "en": "Pydantic validation error: {message}",
    },
    "pydantic.validation.suggestion": {
        "he": "בדוק את תקינות המפתחות והטיפוסים שנמסרו לאובייקט.",
        "en": "Check the validity of keys and types passed to the model.",
    },
    # ---------- New Static AST Rules ----------
    "static.sql_injection.title": {
        "he": "חשש להזרקת SQL (SQL Injection) בבניית שאילתה",
        "en": "Potential SQL Injection vulnerability in query formatting",
    },
    "static.sql_injection.hint": {
        "he": "השתמש בפרמטרים מובנים (parameterized queries) במקום f-string או שרשור מחרוזות.",
        "en": "Use parameterized queries instead of f-strings or string concatenation.",
    },
    "static.unsafe_pickle.title": {
        "he": "שימוש לא מאובטח ב-pickle לטעינת נתונים",
        "en": "Insecure use of pickle for deserialization",
    },
    "static.unsafe_pickle.hint": {
        "he": "טעינת נתונים באמצעות pickle עלולה להריץ קוד זדוני; העדף פורמט בטוח כמו json.",
        "en": "Loading data with pickle can execute arbitrary code; prefer safe formats like json.",
    },
    "static.unsafe_yaml.title": {
        "he": "שימוש ב-yaml.load ללא SafeLoader",
        "en": "Using yaml.load without SafeLoader",
    },
    "static.unsafe_yaml.hint": {
        "he": "השתמש ב-yaml.safe_load(...) למניעת הרצת קוד זדוני.",
        "en": "Use yaml.safe_load(...) to prevent arbitrary code execution.",
    },
    "static.str_concat_in_loop.title": {
        "he": "שרשור מחרוזות בלולאה עלול לפגוע בביצועים",
        "en": "String concatenation in loop may degrade performance",
    },
    "static.str_concat_in_loop.hint": {
        "he": "אסוף את המחרוזות לרשימה והשתמש ב-`''.join(parts)` בסיום.",
        "en": "Collect strings into a list and use `''.join(parts)` at the end.",
    },
    "static.re_compile_in_func.title": {
        "he": "קריאה ל-re.compile בתוך גוף פונקציה",
        "en": "Calling re.compile inside function body",
    },
    "static.re_compile_in_func.hint": {
        "he": "הגדר את תבנית ה-Regex כקבוע ברמת המודול כדי לחסוך הידור חוזר בכל ריצה.",
        "en": "Define regex pattern as a module-level constant to avoid recompilation.",
    },
    "static.list_membership_in_loop.title": {
        "he": "חיפוש שייכות (`in list`) בלולאה על רשימה גדולה",
        "en": "Linear membership check (`in list`) inside a loop",
    },
    "static.list_membership_in_loop.hint": {
        "he": "המר את הרשימה ל-`set` לפני הלולאה לחיפוש בסיבוכיות O(1).",
        "en": "Convert the list to a `set` before the loop for O(1) lookups.",
    },
    "static.use_pathlib.title": {
        "he": "שימוש ב-os.path במקום ספריית pathlib המודרנית",
        "en": "Using os.path instead of modern pathlib",
    },
    "static.use_pathlib.hint": {
        "he": "מומלץ להשתמש ב-`pathlib.Path` לתחביר קריא ומודרני יותר.",
        "en": "Consider using `pathlib.Path` for cleaner and more modern filesystem code.",
    },
    "static.modern_typing.title": {
        "he": "שימוש בטיפוסים מיושנים מ-typing במקום built-in generics",
        "en": "Using legacy typing constructs instead of built-in generics",
    },
    "static.modern_typing.hint": {
        "he": "השתמש ב-`list[T]`, `dict[K, V]` ו-`X | Y` במקום `typing.List`, `typing.Dict`, `typing.Union`.",
        "en": "Use `list[T]`, `dict[K, V]`, and `X | Y` instead of `typing.List`, `typing.Dict`, `typing.Union`.",
    },
}


def t(key: str, lang: str = "en", /, **kwargs: object) -> str:
    """מחזיר מחרוזת מתורגמת ומפורמטת. אם המפתח חסר - מחזיר את המפתח עצמו."""
    entry = CATALOG.get(key)
    if entry is None:
        return key
    template = entry.get(lang) or entry.get("en") or entry.get("he") or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def available_languages() -> list[str]:
    langs: set[str] = set()
    for entry in CATALOG.values():
        langs.update(entry)
    return sorted(langs)
