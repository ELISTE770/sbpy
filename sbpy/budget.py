"""שומר תקציב: כמה פניות ל-Gemini מותרות, וכמה כבר נוצלו.

המטרה היא שהתוסף לעולם לא יפתיע בחשבון. ברירת המחדל שמרנית בכוונה.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .config import Config, get_config
from .pricing import estimate, format_usd


@dataclass
class BudgetState:
    calls_this_run: int = 0
    tokens_this_run: int = 0
    blocked: int = 0
    by_task: dict[str, int] = field(default_factory=dict)


_state = BudgetState()
_lock = threading.Lock()


def state() -> BudgetState:
    return _state


def reset_run() -> None:
    global _state
    with _lock:
        _state = BudgetState()


def _today() -> str:
    return date.today().isoformat()


def _read_usage(config: Config) -> list[dict[str, Any]]:
    path = config.usage_file
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows


def calls_today(config: Config | None = None) -> int:
    config = config or get_config()
    today = _today()
    return sum(1 for row in _read_usage(config) if row.get("date") == today)


def check(task: str = "", config: Config | None = None) -> tuple[bool, str]:
    """האם מותר לבצע פנייה נוספת. מחזיר (מותר, סיבה אם לא)."""
    config = config or get_config()

    if not config.enabled:
        return False, "disabled"
    if config.offline:
        return False, "offline"
    if not config.active_api_key:
        return False, "no-api-key"

    with _lock:
        used_run = _state.calls_this_run
    if config.max_calls_per_run and used_run >= config.max_calls_per_run:
        return False, f"run-limit {used_run}/{config.max_calls_per_run}"

    if config.max_calls_per_day:
        used_day = calls_today(config)
        if used_day >= config.max_calls_per_day:
            return False, f"day-limit {used_day}/{config.max_calls_per_day}"

    return True, ""


def record(
    task: str,
    model: str,
    tokens: int = 0,
    *,
    tier: str = "",
    cached: bool = False,
    ok: bool = True,
    config: Config | None = None,
) -> None:
    """רושם פנייה ביומן השימוש (JSONL) ובמונה הריצה."""
    config = config or get_config()
    if not cached:
        with _lock:
            _state.calls_this_run += 1
            _state.tokens_this_run += max(0, tokens)
            _state.by_task[task] = _state.by_task.get(task, 0) + 1

    row = {
        "date": _today(),
        "ts": round(time.time(), 3),
        "task": task,
        "model": model,
        "tier": tier,
        "tokens": tokens,
        "cached": cached,
        "ok": ok,
        "pid": os.getpid(),
    }
    try:
        config.ensure_home()
        with open(config.usage_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:  # sbpy: ignore=silent-except
        pass


def note_blocked() -> None:
    with _lock:
        _state.blocked += 1


def summary(config: Config | None = None, days: int = 7) -> dict[str, Any]:
    """סיכום שימוש להצגה ב-`sbpy usage`."""
    config = config or get_config()
    rows = _read_usage(config)
    today = _today()

    by_day: dict[str, int] = {}
    by_task: dict[str, int] = {}
    by_model: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    tokens = 0
    cached_hits = 0
    cost = 0.0
    cost_today = 0.0
    tokens_saved = 0

    for row in rows:
        day = str(row.get("date", ""))
        by_day[day] = by_day.get(day, 0) + 1
        if row.get("cached"):
            cached_hits += 1
            tokens_saved += int(row.get("tokens") or 0)
            continue
        by_task[str(row.get("task", "?"))] = by_task.get(str(row.get("task", "?")), 0) + 1
        model = str(row.get("model", "?"))
        by_model[model] = by_model.get(model, 0) + 1
        tier = str(row.get("tier") or "?")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        row_tokens = int(row.get("tokens") or 0)
        tokens += row_tokens
        row_cost = estimate(row_tokens, model, config)
        cost += row_cost
        if day == today:
            cost_today += row_cost

    recent = dict(sorted(by_day.items(), reverse=True)[:days])
    return {
        "total_rows": len(rows),
        "calls_today": by_day.get(today, 0),
        "tokens_total": tokens,
        "cached_hits": cached_hits,
        "by_day": recent,
        "by_task": dict(sorted(by_task.items(), key=lambda item: -item[1])),
        "by_model": by_model,
        "by_tier": by_tier,
        "cost_usd": round(cost, 6),
        "cost_usd_today": round(cost_today, 6),
        "cost_text": format_usd(cost),
        "tokens_saved_by_cache": tokens_saved,
        "run": {
            "calls": _state.calls_this_run,
            "tokens": _state.tokens_this_run,
            "blocked": _state.blocked,
        },
        "limits": {
            "per_run": config.max_calls_per_run,
            "per_day": config.max_calls_per_day,
        },
        "usage_file": str(config.usage_file),
    }
