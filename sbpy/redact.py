"""ניקוי סודות מקוד ומהודעות שגיאה לפני שליחה החוצה.

הכלל: מה שיוצא מהמחשב של המשתמש עובר כאן קודם.
"""

from __future__ import annotations

import os
import re

PLACEHOLDER = "<redacted>"

# תבניות של מפתחות מוכרים
_TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("stripe-key", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("connection-string", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:@/]+:[^\s:@/]+@[^\s]+")),
]

# השמות שמסגירות סוד: password = "...", api_key: "...", TOKEN="..."
_SECRET_NAME = r"(?:pass(?:word|wd)?|secret|token|api[_\-]?key|apikey|auth|credential|private[_\-]?key|access[_\-]?key|client[_\-]?secret)"
_ASSIGNMENT = re.compile(
    rf"(?i)\b(?P<name>\w*{_SECRET_NAME}\w*)\s*(?P<op>[:=]{{1,2}})\s*(?P<quote>['\"])(?P<value>[^'\"]{{3,}})(?P=quote)"
)

_ENV_ASSIGNMENT = re.compile(
    rf"(?i)^(?P<name>\w*{_SECRET_NAME}\w*)=(?P<value>.+)$", re.MULTILINE
)

# מחרוזות ארוכות שנראות כמו סוד גולמי
_LONG_BLOB = re.compile(r"\b[A-Za-z0-9+/=_\-]{48,}\b")

_EMAIL = re.compile(r"\b[\w.+\-]+@[\w\-]+\.[\w.\-]+\b")

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _mask(value: str, keep: int = 3) -> str:
    """משאיר רמז קצר כדי שהאבחון עדיין יהיה מובן."""
    if len(value) <= keep:
        return PLACEHOLDER
    return f"{value[:keep]}{PLACEHOLDER}"


def redact_paths(text: str) -> str:
    """מחליף נתיבי בית אישיים ב-~ כדי לא לחשוף שם משתמש."""
    home = os.path.expanduser("~")
    if not home or home in ("/", "\\"):
        return text
    variants = {home, home.replace("\\", "/"), home.replace("/", "\\")}
    for variant in variants:
        if variant:
            text = text.replace(variant, "~")
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if user and len(user) >= 3:
        text = re.sub(rf"(?<![\w]){re.escape(user)}(?![\w])", "<user>", text)
    return text


def redact(text: str, *, mask_emails: bool = True, mask_ips: bool = False) -> str:
    """מנקה סודות מטקסט. בטוח להריץ גם על קוד וגם על traceback."""
    if not text:
        return text

    for _, pattern in _TOKEN_PATTERNS:
        text = pattern.sub(PLACEHOLDER, text)

    def _assign_sub(match: re.Match[str]) -> str:
        return (
            f"{match.group('name')}{match.group('op')}"
            f"{match.group('quote')}{_mask(match.group('value'))}{match.group('quote')}"
        )

    text = _ASSIGNMENT.sub(_assign_sub, text)
    text = _ENV_ASSIGNMENT.sub(lambda m: f"{m.group('name')}={PLACEHOLDER}", text)
    text = _LONG_BLOB.sub(lambda m: _mask(m.group(0), 4), text)
    text = redact_paths(text)

    if mask_emails:
        text = _EMAIL.sub("<email>", text)
    if mask_ips:
        text = _IPV4.sub("<ip>", text)

    return text


_PLACEHOLDER_WORDS = {
    "", "none", "null", "nil", "changeme", "change_me", "your_key_here",
    "your-key-here", "yourkey", "xxx", "xxxx", "todo", "tbd", "redacted",
    "example", "sample", "dummy", "placeholder", "secret", "password",
    "test", "fake", "value",
}

_PLACEHOLDER_SHAPE = re.compile(r"^[.\-_*#x• ]+$", re.IGNORECASE)


def _is_placeholder(value: str) -> bool:
    """האם הערך הוא ברור שהוא דמה ולא סוד אמיתי."""
    stripped = value.strip()
    if stripped.lower() in _PLACEHOLDER_WORDS:
        return True
    if _PLACEHOLDER_SHAPE.match(stripped):
        return True
    if stripped.startswith(("${", "%", "<", "{{", "os.environ", "getenv")):
        return True
    return "os.environ" in stripped or "getenv" in stripped


def scan_secrets(text: str) -> list[tuple[str, int]]:
    """מאתר סודות בקוד ומחזיר (סוג, מספר שורה). משמש את @SEC.

    סורק גם תגובות בכוונה - סוד בקוד שהוער החוצה הוא עדיין סוד שדלף.
    """
    found: list[tuple[str, int]] = []
    for kind, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((kind, line))
    typed_lines = {line for _, line in found}
    for match in _ASSIGNMENT.finditer(text):
        if _is_placeholder(match.group("value")):
            continue
        line = text.count("\n", 0, match.start()) + 1
        # אם כבר זיהינו בשורה הזו מפתח מסוג ידוע, אין טעם לדווח גם "סוד כללי"
        if line in typed_lines:
            continue
        found.append(("hardcoded-secret", line))
    return sorted(set(found), key=lambda item: item[1])
