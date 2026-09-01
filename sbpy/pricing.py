"""הערכת עלות של הפניות ל-Gemini.

**המספרים כאן הם הערכה, לא מחירון רשמי.** המחירים משתנים, ולכן:

* אפשר לדרוס אותם בקובץ ``~/.sbpy/pricing.json``
* אפשר לדרוס דרך ``SBPY_PRICE_<MODEL>`` (דולר למיליון טוקנים)

התצוגה תמיד מסומנת ב-``~`` כדי שברור שזו הערכה ולא חיוב.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .config import Config, get_config

# דולר למיליון טוקנים, מחיר מעורב (קלט+פלט) - הערכה גסה.
# עדכן ב-~/.sbpy/pricing.json אם המחירון השתנה.
DEFAULT_PRICES: dict[str, float] = {
    "gemini-3.5-flash-lite": 0.20,
    "gemini-3.1-flash-lite": 0.20,
    "gemini-3.6-flash": 0.60,
    "gemini-3.1-pro-preview": 5.00,
}

FALLBACK_PRICE = 0.60
_cache: dict[str, float] | None = None


def _env_overrides() -> dict[str, float]:
    found: dict[str, float] = {}
    for key, value in os.environ.items():
        if not key.startswith("SBPY_PRICE_"):
            continue
        model = key[len("SBPY_PRICE_") :].lower().replace("_", "-")
        try:
            found[model] = float(value)
        except ValueError:
            continue
    return found


def load_prices(config: Config | None = None, *, refresh: bool = False) -> dict[str, float]:
    global _cache
    if _cache is not None and not refresh:
        return _cache

    config = config or get_config()
    prices = dict(DEFAULT_PRICES)

    path = config.home / "pricing.json"
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                for model, value in data.items():
                    try:
                        prices[str(model)] = float(value)
                    except (TypeError, ValueError):
                        continue
    except (OSError, ValueError):  # sbpy: ignore=silent-except
        pass

    prices.update(_env_overrides())
    _cache = prices
    return prices


def price_per_million(model: str, config: Config | None = None) -> float:
    prices = load_prices(config)
    if model in prices:
        return prices[model]
    # התאמה חלקית: gemini-3.6-flash-002 -> gemini-3.6-flash
    for known, value in prices.items():
        if model.startswith(known):
            return value
    return FALLBACK_PRICE


def estimate(tokens: int, model: str, config: Config | None = None) -> float:
    """עלות מוערכת בדולרים."""
    if tokens <= 0:
        return 0.0
    return tokens / 1_000_000 * price_per_million(model, config)


def format_usd(amount: float) -> str:
    if amount <= 0:
        return "$0"
    if amount < 0.01:
        return f"~${amount:.4f}"
    return f"~${amount:.2f}"


def table(config: Config | None = None) -> list[tuple[str, float]]:
    prices = load_prices(config)
    return sorted(prices.items(), key=lambda item: item[1])


def describe(config: Config | None = None) -> dict[str, Any]:
    config = config or get_config()
    return {
        "source": str(config.home / "pricing.json"),
        "note": "הערכה בלבד - עדכן את הקובץ אם המחירון השתנה",
        "usd_per_million_tokens": load_prices(config),
    }
