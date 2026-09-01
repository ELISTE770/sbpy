"""למידה מהתשובות של Gemini - כדי לא לשאול את אותה שאלה פעמיים.

המטמון הרגיל (``cache.py``) ממופתח לפי טביעת אצבע מדויקת: אותה שגיאה,
אותה שורה, אותה פונקציה. השכבה הזו רחבה יותר:

* **חבילות** - מ"התקן עם pip install X" נלמד מיפוי מודול -> חבילה,
  שיעבוד בכל פרויקט בעתיד.
* **חתימות** - הודעת השגיאה מנורמלת בלי מספרים/כתובות/נתיבים, כך
  שאותה שגיאה בקובץ אחר תיענה מקומית.

הכל נשמר ב-``~/.sbpy/learned.json`` וניתן למחיקה ב-``sbpy learn --clear``.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from .cache import normalize
from .config import Config, get_config
from .results import Diagnosis, Report

MAX_SIGNATURES = 500
MIN_CONFIDENCE_TO_LEARN = 0.7

_lock = threading.Lock()
_store: dict[str, Any] | None = None

_PIP_PATTERN = re.compile(r"pip\s+install\s+(?:-U\s+)?([A-Za-z0-9._\-\[\]]+)")
_QUOTED = re.compile(r"['\"]([A-Za-z_][\w.]*)['\"]")


@dataclass
class LearnedRule:
    signature: str
    title: str
    fix: str = ""
    detail: str = ""
    confidence: float = 0.75
    hits: int = 0
    learned_at: float = 0.0
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "fix": self.fix,
            "detail": self.detail,
            "confidence": self.confidence,
            "hits": self.hits,
            "learned_at": self.learned_at,
            "model": self.model,
        }


# ----------------------------------------------------------------------
def signature(exc_type: str, message: str) -> str:
    """חתימה יציבה לשגיאה, בלי פרטים שמשתנים בין ריצות."""
    text = normalize(f"{exc_type}: {message}")
    text = re.sub(r"\b\d+\b", "<n>", text)
    return text.strip()[:300]


def _path(config: Config) -> Any:
    return config.home / "learned.json"


def _empty() -> dict[str, Any]:
    return {"version": 1, "packages": {}, "signatures": {}, "saved_calls": 0}


def load(config: Config | None = None, *, refresh: bool = False) -> dict[str, Any]:
    global _store
    if _store is not None and not refresh:
        return _store
    config = config or get_config()
    data = _empty()
    try:
        path = _path(config)
        if path.exists():
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                data.update({k: v for k, v in loaded.items() if k in data})
    except (OSError, ValueError):  # sbpy: ignore=silent-except
        pass
    _store = data
    return data


def save(config: Config | None = None) -> None:
    config = config or get_config()
    data = load(config)
    try:
        config.ensure_home()
        with open(_path(config), "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
    except (OSError, TypeError, ValueError):  # sbpy: ignore=silent-except
        pass


def reset_memory() -> None:
    """מנקה רק את המטמון בזיכרון (לבדיקות)."""
    global _store
    _store = None


def clear(config: Config | None = None) -> int:
    """מוחק את כל מה שנלמד. מחזיר כמה פריטים נמחקו."""
    global _store
    config = config or get_config()
    data = load(config)
    count = len(data.get("packages", {})) + len(data.get("signatures", {}))
    _store = _empty()
    save(config)
    return count


# ----------------------------------------------------------------------
def _learn_package(report: Report, diagnosis: Diagnosis, config: Config) -> bool:
    """מ"pip install X" על ModuleNotFoundError -> מיפוי מודול->חבילה."""
    if report.exc_type != "ModuleNotFoundError":
        return False
    names = _QUOTED.findall(report.exc_message)
    if not names:
        return False
    module = names[0].split(".")[0]

    text = f"{diagnosis.suggestion} {diagnosis.patch or ''} {diagnosis.detail}"
    match = _PIP_PATTERN.search(text)
    if not match:
        return False
    package = match.group(1).strip()
    if not package or package.lower() == module.lower():
        return False

    data = load(config)
    packages = data.setdefault("packages", {})
    if packages.get(module) == package:
        return False
    packages[module] = package
    return True


def _learn_signature(report: Report, diagnosis: Diagnosis, config: Config) -> bool:
    key = signature(report.exc_type, report.exc_message)
    if not key or not diagnosis.title:
        return False

    data = load(config)
    signatures = data.setdefault("signatures", {})
    if key in signatures:
        return False

    if len(signatures) >= MAX_SIGNATURES:
        # מפנים מקום: זורקים את הוותיקים שלא נוצלו
        ordered = sorted(
            signatures.items(), key=lambda item: (item[1].get("hits", 0), item[1].get("learned_at", 0))
        )
        for old_key, _ in ordered[: max(1, len(ordered) // 5)]:
            signatures.pop(old_key, None)

    signatures[key] = LearnedRule(
        signature=key,
        title=diagnosis.title,
        fix=diagnosis.suggestion,
        detail=diagnosis.detail,
        confidence=round(min(0.88, max(0.6, diagnosis.confidence * 0.92)), 4),
        learned_at=time.time(),
        model=str(diagnosis.meta.get("model", "")),
    ).to_dict()
    return True


def learn_from(report: Report, *, config: Config | None = None) -> bool:
    """לומד מדוח שהוסלם ל-Gemini. מחזיר True אם משהו נשמר."""
    config = config or get_config()
    if not config.learning:
        return False
    best = report.best
    if best is None or best.source != "gemini" or best.confidence < MIN_CONFIDENCE_TO_LEARN:
        return False

    with _lock:
        changed = _learn_package(report, best, config)
        changed = _learn_signature(report, best, config) or changed
        if changed:
            save(config)
    return changed


# ----------------------------------------------------------------------
def package_for(module: str, *, config: Config | None = None) -> str | None:
    """שם החבילה ב-pip עבור מודול, אם נלמד בעבר."""
    config = config or get_config()
    if not config.learning:
        return None
    return load(config).get("packages", {}).get(module.split(".")[0])


def lookup(exc_type: str, message: str, *, config: Config | None = None) -> Diagnosis | None:
    """מחפש כלל שנלמד. מעדכן מונה פגיעות."""
    config = config or get_config()
    if not config.learning:
        return None

    key = signature(exc_type, message)
    data = load(config)
    row = data.get("signatures", {}).get(key)
    if not isinstance(row, dict):
        return None

    with _lock:
        row["hits"] = int(row.get("hits", 0)) + 1
        data["saved_calls"] = int(data.get("saved_calls", 0)) + 1
        save(config)

    return Diagnosis(
        title=str(row.get("title", "")),
        detail=str(row.get("detail", "")),
        suggestion=str(row.get("fix", "")),
        confidence=float(row.get("confidence") or 0.75),
        source="cache",
        rule="learned",
        meta={"kind": "learned", "signature": key, "hits": row.get("hits", 0)},
    )


def stats(config: Config | None = None) -> dict[str, Any]:
    config = config or get_config()
    data = load(config)
    signatures = data.get("signatures", {})
    top = sorted(
        ((key, row.get("hits", 0)) for key, row in signatures.items()),
        key=lambda item: -item[1],
    )[:5]
    return {
        "packages": len(data.get("packages", {})),
        "signatures": len(signatures),
        "saved_calls": data.get("saved_calls", 0),
        "top": top,
        "file": str(_path(config)),
    }
