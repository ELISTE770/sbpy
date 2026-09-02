"""פרומפטים וסכמות JSON. קצרים בכוונה - כל טוקן עולה כסף.

כלל: לעולם לא שולחים את כל הקובץ אם אפשר לשלוח חלון של עשר שורות.
"""

from __future__ import annotations

from typing import Any

LANGUAGE_LINE = {
    "he": "השב בעברית, קצר ולעניין. שמות משתנים וקוד נשארים באנגלית.",
    "en": "Answer in English, short and direct.",
}


def _language(lang: str) -> str:
    return LANGUAGE_LINE.get(lang, LANGUAGE_LINE["en"])


# ======================================================================
# סכמות
# ======================================================================
DIAGNOSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "שורה אחת: מה בדיוק שבור"},
        "cause": {"type": "string", "description": "הסיבה השורשית, שתי שורות לכל היותר"},
        "fix": {"type": "string", "description": "מה לעשות, בצעד אחד או שניים"},
        "patch": {"type": "string", "description": "שורות הקוד המתוקנות בלבד, בלי הסבר. ריק אם אין."},
        "confidence": {"type": "number", "description": "0 עד 1"},
    },
    "required": ["title", "cause", "fix", "confidence"],
}

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "severity": {"type": "string", "enum": ["info", "warn", "error", "critical"]},
                    "title": {"type": "string"},
                    "why": {"type": "string", "description": "למה זה באג - כולל תרחיש כישלון קונקרטי"},
                    "fix": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["line", "severity", "title", "why", "fix"],
            },
        }
    },
    "required": ["findings"],
}

BATCH_DIAGNOSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "מספר השגיאה כפי שהופיע בקלט"},
                    "title": {"type": "string"},
                    "cause": {"type": "string"},
                    "fix": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["index", "title", "cause", "fix", "confidence"],
            },
        }
    },
    "required": ["answers"],
}

BATCH_FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "שם הקובץ כפי שהופיע בכותרת"},
                    "line": {"type": "integer"},
                    "severity": {"type": "string", "enum": ["info", "warn", "error", "critical"]},
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                    "fix": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["file", "line", "severity", "title", "why", "fix"],
            },
        }
    },
    "required": ["findings"],
}


VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "real": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["real", "reason"],
}


# ======================================================================
# הוראות מערכת
# ======================================================================
SYSTEM_DIAGNOSE = (
    "אתה מומחה לאבחון שגיאות Python. המטרה שלך היא למצוא את הסיבה השורשית המדויקת ולספק את התיקון הקונקרטי. "
    "1. זהה תמיד את שורש הבעיה ותן פתרון ברור. "
    "2. בדיקת שפות ומקלדות זרות (Multi-language & Keyboard Layout Detection): "
    "אם שורת הקוד, פונקציה, משתנה או השגיאה מכילים תווים שאינם באנגלית (כגון עברית, רוסית/קירילית, ערבית, יוונית או תווים זרים אחרים), בדוק מיד: "
    "   א. האם מדובר בהקלדה בטעות במקלדת שאינה אנגלית (Keyboard Layout Mismatch / QWERTY transliteration - כגון 'פרןמא'/'דנפט'/'שא'/'הקכ' בעברית, או 'принт'/'вуа' ברוסית). "
    "   ב. האם מדובר בפקודות מתורגמות בשפה טבעית/פסאודו-קוד (כגון 'הדפס' במקום print, 'אם' במקום if, 'החזר' במקום return). "
    "במקרים אלו, הסבר את אי-התאמת השפה/מקלדת ב-cause, תן הנחיה ברורה ב-fix, והחזר בשדה 'patch' את שורת הקוד המלאה והמדויקת באנגלית תקינה. "
    "3. החזר JSON מדויק לפי הסכמה בלבד."
)

SYSTEM_REVIEW = (
    "אתה בודק קוד Python מנוסה. דווח רק על באגים אמיתיים עם תרחיש כישלון קונקרטי. "
    "אל תדווח על סגנון, שמות, או העדפות. אם אין באג - החזר רשימה ריקה."
)

SYSTEM_WRITE = (
    "אתה כותב קוד Python נקי ומודרני. החזר קוד בלבד, בלי הסברים ובלי גדר markdown, "
    "אלא אם התבקשת אחרת."
)

SYSTEM_EXPLAIN = "אתה מסביר קוד Python בבהירות, בלי מילים מיותרות."


# ======================================================================
# בוני פרומפטים
# ======================================================================
def diagnose_prompt(
    *,
    exc_type: str,
    message: str,
    where: str,
    code: str,
    traceback_tail: str = "",
    local_notes: str = "",
    lang: str = "he",
) -> str:
    parts = [
        _language(lang),
        "",
        f"שגיאה: {exc_type}: {message}",
        f"מיקום: {where}",
    ]
    if code:
        parts += ["", "הקוד סביב השגיאה:", "```python", code, "```"]
    if traceback_tail:
        parts += ["", "סוף ה-traceback:", "```", traceback_tail, "```"]
    if local_notes:
        parts += ["", f"מה שהבדיקה המקומית כבר מצאה (אל תחזור על זה): {local_notes}"]

    # אם זוהו תווים זרים / non-ASCII בשגיאה או בקוד - מוסיפים הנחיה ייעודית וממוקדת
    if any(ord(c) > 127 for c in f"{message} {code}"):
        parts += [
            "",
            "💡 הנחיית שפות ומקלדת:",
            "- זוהו תווים בשפה שאינה אנגלית (non-ASCII) בקוד או בהודעת השגיאה.",
            "- בדוק האם מדובר בטעות של פריסת מקלדת (שפה זרה על מקלדת QWERTY כגון עברית, רוסית, ערבית) או מילות מפתח מתורגמות (הדפס/אם/החזר).",
            "- תרגם ושחזר את שורת הפייתון המקורית המלאה באנגלית והחזר אותה בשדה 'patch'.",
        ]

    parts += ["", "מה הסיבה השורשית ומה התיקון?"]
    return "\n".join(parts)


def review_prompt(*, code: str, filename: str, focus: str, known: str = "", lang: str = "he") -> str:
    parts = [
        _language(lang),
        "",
        f"קובץ: {filename}",
        f"מוקד הבדיקה: {focus}",
    ]
    if known:
        parts += ["", f"בדיקה סטטית כבר מצאה את אלה, אל תחזור עליהם: {known}"]
    parts += [
        "",
        "הקוד (מספרי השורות אמיתיים):",
        "```python",
        code,
        "```",
        "",
        "מצא באגים שניתוח סטטי לא תופס: לוגיקה שגויה, מקרי קצה, מצבי מרוץ, "
        "הנחות שקריות על הקלט, off-by-one, וטיפול חסר בשגיאות.",
    ]
    return "\n".join(parts)


def explain_prompt(*, code: str, question: str = "", lang: str = "he") -> str:
    parts = [_language(lang), ""]
    if question:
        parts.append(question)
    parts += ["", "```python", code, "```"]
    if not question:
        parts.append("\nהסבר מה הקוד עושה, ומה חשוב לשים לב אליו.")
    return "\n".join(parts)


def write_prompt(*, task: str, code: str, filename: str = "", lang: str = "he") -> str:
    parts = [_language(lang), "", task]
    if filename:
        parts.append(f"(קובץ: {filename})")
    parts += ["", "```python", code, "```"]
    return "\n".join(parts)


def numbered(code: str, start: int = 1) -> str:
    """מוסיף מספרי שורות אמיתיים כדי שההפניות של המודל יהיו מדויקות."""
    lines = code.splitlines()
    width = len(str(start + len(lines) - 1))
    return "\n".join(f"{start + index:>{width}} | {line}" for index, line in enumerate(lines))


def batch_diagnose_prompt(items: list[dict[str, Any]], lang: str = "he") -> str:
    """פרומפט אחד ל-N שגיאות. חוסך N-1 קריאות."""
    parts = [
        _language(lang),
        "",
        f"להלן {len(items)} שגיאות שכלי מקומי לא הצליח לפתור.",
        "ענה על כל אחת בנפרד, והחזר את `index` כפי שהוא מופיע כאן.",
    ]
    for item in items:
        parts += [
            "",
            f"--- שגיאה {item['index']} ---",
            f"{item['exc_type']}: {item['message']}",
            f"מיקום: {item.get('where', '')}",
        ]
        if item.get("code"):
            parts += ["```python", item["code"], "```"]
    return "\n".join(parts)


def batch_review_prompt(files: list[dict[str, Any]], focus: str, lang: str = "he") -> str:
    """סקירה של כמה קבצים בקריאה אחת."""
    parts = [
        _language(lang),
        "",
        f"מוקד הבדיקה: {focus}",
        f"להלן {len(files)} קבצים. ציין בכל ממצא את שם הקובץ ואת מספר השורה האמיתי.",
        "אם בקובץ אין באג אמיתי - אל תמציא ממצא עבורו.",
    ]
    for entry in files:
        parts += [
            "",
            f"### FILE: {entry['name']}",
            "```python",
            entry["code"],
            "```",
        ]
    return "\n".join(parts)
