"""מטמון תשובות על הדיסק - אותה שגיאה לא נשלחת ל-Gemini פעמיים."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .config import Config, get_config

# נרמול הודעות שגיאה: כתובות זיכרון, מספרים ונתיבים משתנים בין ריצות
_NORMALIZERS = (
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"\b\d{4,}\b"), "<num>"),
    (re.compile(r"[A-Za-z]:\\[^\s'\"]+"), "<path>"),
    (re.compile(r"(?<![\w])/(?:[\w.\-]+/)+[\w.\-]+"), "<path>"),
    (re.compile(r"\s+"), " "),
)


def normalize(text: str) -> str:
    """מצמצם שונות חסרת משמעות כדי שהמטמון יפגע יותר."""
    for pattern, replacement in _NORMALIZERS:
        text = pattern.sub(replacement, text)
    return text.strip()


def fingerprint(*parts: object) -> str:
    """מזהה יציב לשגיאה/משימה."""
    payload = "␟".join(normalize(str(part)) for part in parts if part is not None)
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()[:32]


class Cache:
    """מטמון קבצים פשוט. כשל בכתיבה לעולם לא מפיל את הקוד של המשתמש."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()

    # ------------------------------------------------------------------
    @property
    def directory(self) -> Path:
        return self.config.cache_dir

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.config.cache_enabled:
            return None
        path = self._path(key)
        try:
            if not path.exists():
                return None
            age_days = (time.time() - path.stat().st_mtime) / 86400
            if age_days > self.config.cache_ttl_days:
                path.unlink(missing_ok=True)
                return None
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if isinstance(data, dict):
            data["_cached_at"] = data.get("_cached_at")
            return data
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.config.cache_enabled:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            payload = dict(value)
            payload["_cached_at"] = time.time()
            temporary = self._path(key).with_suffix(".tmp")
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=1)
            os.replace(temporary, self._path(key))
        except (OSError, TypeError, ValueError):
            return

    # ------------------------------------------------------------------
    def clear(self) -> int:
        count = 0
        try:
            for path in self.directory.glob("*.json"):
                path.unlink(missing_ok=True)
                count += 1
        except OSError:  # sbpy: ignore=silent-except
            pass
        return count

    def stats(self) -> dict[str, Any]:
        entries = 0
        size = 0
        oldest: float | None = None
        try:
            for path in self.directory.glob("*.json"):
                entries += 1
                stat = path.stat()
                size += stat.st_size
                oldest = stat.st_mtime if oldest is None else min(oldest, stat.st_mtime)
        except OSError:  # sbpy: ignore=silent-except
            pass
        return {
            "entries": entries,
            "bytes": size,
            "directory": str(self.directory),
            "oldest_age_days": round((time.time() - oldest) / 86400, 2) if oldest else 0.0,
        }
