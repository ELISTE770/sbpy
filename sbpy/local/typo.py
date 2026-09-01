"""מנוע התאמת טעויות כתיב - מקומי לחלוטין, בלי שום קריאת רשת.

זו השכבה שחוסכת את רוב הפניות ל-Gemini: רוב שגיאות ה-``NameError`` /
``AttributeError`` / ``KeyError`` בעולם האמיתי הן פשוט טעות הקלדה.
"""

from __future__ import annotations

import difflib
from typing import Iterable, Sequence

# מקלדת QWERTY - שכנות פיזית בין תווים.
_KEYBOARD_ROWS = (
    "`1234567890-=",
    "qwertyuiop[]\\",
    "asdfghjkl;'",
    "zxcvbnm,./",
)

_ADJACENT: dict[str, set[str]] = {}


def _build_adjacency() -> None:
    for row_index, row in enumerate(_KEYBOARD_ROWS):
        for col_index, char in enumerate(row):
            neighbours: set[str] = set()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    r, c = row_index + dr, col_index + dc
                    if 0 <= r < len(_KEYBOARD_ROWS) and 0 <= c < len(_KEYBOARD_ROWS[r]):
                        neighbours.add(_KEYBOARD_ROWS[r][c])
            _ADJACENT[char] = neighbours


_build_adjacency()


def keyboard_adjacent(a: str, b: str) -> bool:
    """האם שני תווים שכנים על המקלדת."""
    return b.lower() in _ADJACENT.get(a.lower(), ())


def levenshtein(a: str, b: str, max_distance: int = 4) -> int:
    """מרחק עריכה עם חיתוך מוקדם."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > max_distance:
        return max_distance + 1
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        best_in_row = i
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            best_in_row = min(best_in_row, value)
        if best_in_row > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


def _is_transposition(a: str, b: str) -> bool:
    """האם ההבדל הוא החלפת שני תווים סמוכים (teh <-> the)."""
    if len(a) != len(b) or a == b:
        return False
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diffs) != 2:
        return False
    i, j = diffs
    return j == i + 1 and a[i] == b[j] and a[j] == b[i]


def _normalize_style(name: str) -> str:
    """snake_case / camelCase / kebab -> צורה מנורמלת להשוואה."""
    return name.replace("_", "").replace("-", "").lower()


def similarity(word: str, candidate: str) -> float:
    """ציון דמיון בין 0 ל-1, מכויל לשמות מזהים בקוד."""
    if not word or not candidate:
        return 0.0
    if word == candidate:
        return 1.0

    low_word, low_cand = word.lower(), candidate.lower()

    # הבדל של אותיות גדולות/קטנות בלבד - כמעט ודאי הכוונה.
    if low_word == low_cand:
        return 0.97

    # אותו שם בסגנון כתיבה אחר (userName מול user_name).
    if _normalize_style(word) == _normalize_style(candidate):
        return 0.94

    ratio = difflib.SequenceMatcher(None, low_word, low_cand).ratio()
    distance = levenshtein(low_word, low_cand)
    length = max(len(low_word), len(low_cand))

    score = ratio
    if _is_transposition(low_word, low_cand):
        score = max(score, 0.95)
    elif distance == 1:
        # תו אחד שונה. במילים קצרות זה פחות משכנע.
        base = 0.93 if length >= 5 else 0.80 if length >= 3 else 0.62
        # אם התו המוחלף שכן על המקלדת - זו כמעט בוודאות טעות הקלדה.
        if length == len(low_word) == len(low_cand):
            for x, y in zip(low_word, low_cand):
                if x != y and keyboard_adjacent(x, y):
                    base = min(0.96, base + 0.04)
                    break
        score = max(score, base)
    elif distance == 2 and length >= 7:
        score = max(score, 0.80)

    # קידומת משותפת ארוכה מחזקת את ההשערה.
    common = 0
    for x, y in zip(low_word, low_cand):
        if x != y:
            break
        common += 1
    if common >= 3 and length:
        score = min(0.98, score + 0.04 * (common / length))

    return round(min(score, 0.98), 4)


def rank(word: str, candidates: Iterable[str], *, limit: int = 5, cutoff: float = 0.55) -> list[tuple[str, float]]:
    """מדרג מועמדים לפי דמיון, מהטוב לפחות טוב."""
    seen: set[str] = set()
    scored: list[tuple[str, float]] = []
    for candidate in candidates:
        if not isinstance(candidate, str) or candidate in seen or candidate == word:
            continue
        seen.add(candidate)
        score = similarity(word, candidate)
        if score >= cutoff:
            scored.append((candidate, score))
    scored.sort(key=lambda item: (-item[1], len(item[0]), item[0]))
    return scored[:limit]


def best_match(word: str, candidates: Iterable[str], *, cutoff: float = 0.62) -> tuple[str | None, float]:
    """מחזיר את המועמד הטוב ביותר ואת הביטחון שלו."""
    ranked = rank(word, candidates, limit=2, cutoff=cutoff)
    if not ranked:
        return None, 0.0
    best, score = ranked[0]
    # אם יש שני מועמדים כמעט זהים - הביטחון יורד, כי לא ברור לאיזה התכוונו.
    if len(ranked) > 1 and abs(ranked[1][1] - score) < 0.03:
        score = round(score * 0.80, 4)
    return best, score


def close_names(word: str, candidates: Iterable[str], limit: int = 5) -> list[str]:
    """רשימת שמות דומים לתצוגה (בלי ציונים)."""
    return [name for name, _ in rank(word, candidates, limit=limit, cutoff=0.5)]


def preview(items: Sequence[object], limit: int = 8) -> str:
    """מחרוזת תצוגה מקוצרת של רשימת ערכים."""
    shown = [repr(item) if not isinstance(item, str) else item for item in items[:limit]]
    text = ", ".join(str(item) for item in shown)
    if len(items) > limit:
        text += f", ... (+{len(items) - limit})"
    return text or "-"
