"""הגדרות גלובליות ל-SBpy.

כל הגדרה ניתנת לשליטה דרך משתני סביבה בקידומת ``SBPY_``,
או דרך ``sbpy.configure(...)`` בזמן ריצה.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

_TRUTHY = {"1", "true", "yes", "on", "y"}
_FALSY = {"0", "false", "no", "off", "n", ""}

# שלוש דרגות מודל. ההבדל ביניהן הוא כל הרעיון של ניהול העלות:
#
#   auto     - הסלמה אוטומטית שהמשתמש לא ביקש (טעות כתיב, שגיאה בריצה).
#              חייב להיות הזול ביותר, כי הוא נקרא בלי שביקשו.
#   command  - פקודה מפורשת: `@...` ב-shell, או `sbpy exp app.py`.
#              המשתמש ביקש, אז מגיע לו מודל טוב יותר.
#   pro      - רק כשמסמנים במפורש: `+` בסוף השורה, או `--pro`.
TIER_AUTO = "auto"
TIER_COMMAND = "command"
TIER_PRO = "pro"
TIERS = (TIER_AUTO, TIER_COMMAND, TIER_PRO)

DEFAULT_MODEL_AUTO = "gemini-3.5-flash-lite"
DEFAULT_MODEL_COMMAND = "gemini-3.6-flash"
DEFAULT_MODEL_PRO = "gemini-3.1-pro-preview"

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "gemini": {
        "auto": "gemini-3.5-flash-lite",
        "command": "gemini-3.6-flash",
        "pro": "gemini-3.1-pro-preview",
    },
    "openai": {
        "auto": "gpt-4o-mini",
        "command": "gpt-4o-mini",
        "pro": "gpt-4o",
    },
    "anthropic": {
        "auto": "claude-3-5-haiku-20241022",
        "command": "claude-3-5-sonnet-20241022",
        "pro": "claude-3-7-sonnet-20250219",
    },
    "claude": {
        "auto": "claude-3-5-haiku-20241022",
        "command": "claude-3-5-sonnet-20241022",
        "pro": "claude-3-7-sonnet-20250219",
    },
    "groq": {
        "auto": "llama-3.1-8b-instant",
        "command": "llama-3.3-70b-versatile",
        "pro": "llama-3.3-70b-versatile",
    },
    "deepseek": {
        "auto": "deepseek-chat",
        "command": "deepseek-chat",
        "pro": "deepseek-reasoner",
    },
    "ollama": {
        "auto": "llama3.2",
        "command": "llama3.2",
        "pro": "llama3.3",
    },
}


import json


def config_file_path(home: Path | None = None) -> Path:
    h = home or _default_home()
    return h / "config.json"


def load_project_toml(root: str | Path | None = None) -> dict[str, Any]:
    """Finds and parses pyproject.toml ([tool.sbpy]) or .sbpy.toml / sbpy.toml in root or parents."""
    cur = Path(root or os.getcwd()).resolve()
    while True:
        pyproj = cur / "pyproject.toml"
        if pyproj.is_file():
            try:
                import tomllib

                with open(pyproj, "rb") as f:
                    data = tomllib.load(f)
                if "tool" in data and "sbpy" in data["tool"] and isinstance(data["tool"]["sbpy"], dict):
                    return dict(data["tool"]["sbpy"])
            except Exception:  # sbpy: ignore=silent-except
                pass

        for name in (".sbpy.toml", "sbpy.toml"):
            sb_toml = cur / name
            if sb_toml.is_file():
                try:
                    import tomllib

                    with open(sb_toml, "rb") as f:
                        return dict(tomllib.load(f))
                except Exception:  # sbpy: ignore=silent-except
                    pass

        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    return {}


def load_stored_config(home: Path | None = None) -> dict[str, Any]:
    """קורא את קובץ התצורה מ-``~/.sbpy/config.json`` ומשלב עם ``pyproject.toml`` אם קיים."""
    path = config_file_path(home)
    result: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                if isinstance(loaded, dict):
                    result.update(loaded)
        except Exception:  # sbpy: ignore=silent-except
            pass

    # Merge project-level pyproject.toml / .sbpy.toml settings
    project_cfg = load_project_toml()
    if project_cfg:
        result.update(project_cfg)

    return result


def save_stored_config(data: dict[str, Any], home: Path | None = None) -> str:
    path = config_file_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return str(path)


def set_config_value(key: str, value: Any, home: Path | None = None) -> None:
    data = load_stored_config(home)
    data[key] = value
    save_stored_config(data, home)


def _env_bool(name: str, default: bool, stored_key: str = "") -> bool:
    raw = os.environ.get(name)
    if raw is None and stored_key:
        stored = load_stored_config()
        if stored_key in stored:
            return bool(stored[stored_key])
    if raw is None:
        return default
    raw = raw.strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


def _env_int(name: str, default: int, stored_key: str = "") -> int:
    raw = os.environ.get(name)
    if raw is None and stored_key:
        stored = load_stored_config()
        if stored_key in stored:
            try:
                return int(stored[stored_key])
            except ValueError:  # sbpy: ignore=silent-except
                pass
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _env_float(name: str, default: float, stored_key: str = "") -> float:
    raw = os.environ.get(name)
    if raw is None and stored_key:
        stored = load_stored_config()
        if stored_key in stored:
            try:
                return float(stored[stored_key])
            except ValueError:  # sbpy: ignore=silent-except
                pass
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _env_str(name: str, default: str, stored_key: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None and stored_key:
        stored = load_stored_config()
        if stored_key in stored:
            return str(stored[stored_key]).strip()
    return default if raw is None else raw.strip()


def _default_home() -> Path:
    raw = os.environ.get("SBPY_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".sbpy"


def _default_custom_shortcuts() -> dict[str, str]:
    stored = load_stored_config()
    sc = stored.get("custom_shortcuts", {})
    if not isinstance(sc, dict):
        sc = {}
    return {str(k).lower(): str(v) for k, v in sc.items()}


def _default_api_keys() -> dict[str, str]:
    stored = load_stored_config()
    keys = stored.get("api_keys", {})
    if not isinstance(keys, dict):
        keys = {}
    return {str(k): str(v) for k, v in keys.items()}

def _default_api_key() -> str | None:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SBPY_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    stored = load_stored_config()
    if stored.get("api_key"):
        return str(stored["api_key"]).strip()
    return None

def _default_custom_instructions() -> str:
    stored = load_stored_config()
    if stored.get("custom_instructions"):
        return str(stored["custom_instructions"]).strip()
    return ""


@dataclass
class Config:
    """מצב התצורה של SBpy."""

    # --- מתגים ראשיים ---
    enabled: bool = field(default_factory=lambda: _env_bool("SBPY_ENABLED", True, "enabled"))
    offline: bool = field(default_factory=lambda: _env_bool("SBPY_OFFLINE", False, "offline"))
    """offline=True => לעולם לא לפנות ל-Gemini. הכל מקומי בלבד."""

    # --- ספק AI (Gemini / Ollama / OpenAI / Claude) ---
    backend: str = field(default_factory=lambda: _env_str("SBPY_BACKEND", "gemini", "backend"))
    ollama_url: str = field(default_factory=lambda: _env_str("SBPY_OLLAMA_URL", "http://localhost:11434", "ollama_url"))
    ollama_model: str = field(default_factory=lambda: _env_str("SBPY_OLLAMA_MODEL", "llama3.2", "ollama_model"))

    api_key: str | None = field(default_factory=_default_api_key)
    api_keys: dict[str, str] = field(default_factory=_default_api_keys)
    custom_shortcuts: dict[str, str] = field(default_factory=_default_custom_shortcuts)
    custom_instructions: str = field(
        default_factory=lambda: _env_str("SBPY_INSTRUCTIONS", _default_custom_instructions(), "custom_instructions")
    )
    slash_menu: bool = field(default_factory=lambda: _env_bool("SBPY_SLASH_MENU", True, "slash_menu"))
    model_auto: str = field(
        default_factory=lambda: _env_str(
            "SBPY_MODEL_AUTO", _env_str("SBPY_MODEL_CHEAP", DEFAULT_MODEL_AUTO), "model_auto"
        )
    )
    model_command: str = field(
        default_factory=lambda: _env_str(
            "SBPY_MODEL_COMMAND", _env_str("SBPY_MODEL_SMART", DEFAULT_MODEL_COMMAND), "model_command"
        )
    )
    model_pro: str = field(
        default_factory=lambda: _env_str("SBPY_MODEL_PRO", DEFAULT_MODEL_PRO, "model_pro")
    )
    timeout: float = field(default_factory=lambda: _env_float("SBPY_TIMEOUT", 12.0, "timeout"))
    check_updates: bool = field(default_factory=lambda: _env_bool("SBPY_CHECK_UPDATES", True, "check_updates"))
    update_interval_hours: int = field(default_factory=lambda: _env_int("SBPY_UPDATE_INTERVAL_HOURS", 6, "update_interval_hours"))
    github_repo: str = field(default_factory=lambda: _env_str("SBPY_REPO", "eliste770-cmyk/sbpy", "github_repo"))
    store: bool = field(default_factory=lambda: _env_bool("SBPY_STORE", False, "store"))
    """האם לאפשר לשרת לשמור את האינטראקציה. ברירת מחדל: לא (פרטיות)."""

    thinking_level: str = field(
        default_factory=lambda: _env_str("SBPY_THINKING", "low", "thinking_level")
    )

    profile: str = field(default_factory=lambda: _env_str("SBPY_PROFILE", "strict", "profile"))
    """How much to report: quiet (errors only) / normal (warnings up) / strict (all)."""

    exclude: list[str] = field(default_factory=lambda: list(load_stored_config().get("exclude", [])))
    ignore_rules: list[str] = field(default_factory=lambda: list(load_stored_config().get("ignore_rules", [])))
    fail_on: str = field(default_factory=lambda: _env_str("SBPY_FAIL_ON", "error", "fail_on"))

    scan_cache: bool = field(
        default_factory=lambda: _env_bool("SBPY_SCAN_CACHE", True, "scan_cache")
    )
    """Reuse static findings for files unchanged since the last scan."""

    parallel_scan: bool = field(
        default_factory=lambda: _env_bool("SBPY_PARALLEL", os.name != "nt", "parallel_scan")
    )
    """Analyse files across processes.

    Off by default on Windows: `spawn` re-imports the package in every
    worker, which measured slower than a serial scan on a project this size.
    """

    pro_fallback: bool = field(default_factory=lambda: _env_bool("SBPY_PRO_FALLBACK", True, "pro_fallback"))
    """אם דרגת pro חסומה בתוכנית - לרדת ל-command במקום להיכשל."""

    ssl_trust: str = field(default_factory=lambda: _env_str("SBPY_SSL", "auto", "ssl_trust"))

    # --- סולם ההסלמה ---
    escalate_threshold: float = field(
        default_factory=lambda: _env_float("SBPY_THRESHOLD", 0.72, "escalate_threshold")
    )
    always_local_first: bool = field(
        default_factory=lambda: _env_bool("SBPY_LOCAL_FIRST", True, "always_local_first")
    )
    project_index: bool = field(default_factory=lambda: _env_bool("SBPY_INDEX", True, "project_index"))
    knowledge: bool = field(default_factory=lambda: _env_bool("SBPY_KB", True, "knowledge"))
    learning: bool = field(default_factory=lambda: _env_bool("SBPY_LEARN", True, "learning"))

    # --- תקציב ---
    max_calls_per_run: int = field(
        default_factory=lambda: _env_int("SBPY_MAX_CALLS_RUN", 10, "max_calls_per_run")
    )
    max_calls_per_day: int = field(
        default_factory=lambda: _env_int("SBPY_MAX_CALLS_DAY", 200, "max_calls_per_day")
    )

    # --- הקשר שנשלח ---
    context_lines: int = field(default_factory=lambda: _env_int("SBPY_CONTEXT_LINES", 8, "context_lines"))
    max_context_chars: int = field(
        default_factory=lambda: _env_int("SBPY_MAX_CONTEXT_CHARS", 6000, "max_context_chars")
    )
    redact: bool = field(default_factory=lambda: _env_bool("SBPY_REDACT", True, "redact"))

    # --- מטמון ---
    cache_enabled: bool = field(default_factory=lambda: _env_bool("SBPY_CACHE", True, "cache_enabled"))
    cache_ttl_days: int = field(default_factory=lambda: _env_int("SBPY_CACHE_TTL", 30, "cache_ttl_days"))

    language: str = field(
        default_factory=lambda: _env_str(
            "SBPY_LANG", _env_str("SBPY_LANGUAGE", "en", "language"), "language"
        )
    )
    color: bool = field(
        default_factory=lambda: _env_bool("SBPY_COLOR", os.environ.get("NO_COLOR") is None, "color")
    )
    verbose: bool = field(default_factory=lambda: _env_bool("SBPY_VERBOSE", False, "verbose"))

    # --- התנהגות ריצה ---
    auto_retry: bool = field(default_factory=lambda: _env_bool("SBPY_AUTO_RETRY", True, "auto_retry"))
    """מאפשר ל-@smart לתקן ולהריץ מחדש שגיאות בטוחות (למשל שם פרמטר עם טעות כתיב)."""

    home: Path = field(default_factory=_default_home)

    # ------------------------------------------------------------------
    def with_overrides(self, **kwargs: Any) -> "Config":
        unknown = set(kwargs) - {f for f in self.__dataclass_fields__}
        if unknown:
            raise TypeError(f"אפשרויות לא מוכרות: {sorted(unknown)}")
        return replace(self, **kwargs)

    def model_for(self, tier: str = TIER_AUTO) -> str:
        """שם המודל לפי דרגה וספק AI פעיל."""
        primary = (self.backend.split(",")[0] if self.backend else "gemini").strip().lower()
        defaults = PROVIDER_DEFAULTS.get(primary, PROVIDER_DEFAULTS["gemini"])

        if tier == TIER_PRO:
            if "gemini" in self.model_pro and primary != "gemini":
                return defaults["pro"]
            return self.model_pro
        if tier == TIER_COMMAND:
            if "gemini" in self.model_command and primary != "gemini":
                return defaults["command"]
            return self.model_command
        if "gemini" in self.model_auto and primary != "gemini":
            return defaults["auto"]
        return self.model_auto

    # --- שמות ישנים, נשמרים כדי לא לשבור קוד קיים ---
    @property
    def active_api_key(self) -> str | None:
        primary = (self.backend.split(",")[0] if self.backend else "gemini").strip().lower()
        if primary in self.api_keys:
            return self.api_keys[primary]
        return self.api_key

    @property
    def model_cheap(self) -> str:
        return self.model_auto

    @property
    def model_smart(self) -> str:
        return self.model_command

    @property
    def can_call_gemini(self) -> bool:
        if not self.enabled or self.offline:
            return False
        if self.backend == "ollama":
            return True
        return bool(self.active_api_key)

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    @property
    def usage_file(self) -> Path:
        return self.home / "usage.jsonl"

    def ensure_home(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home


_config = Config()


def get_config() -> Config:
    return _config


def configure(**kwargs: Any) -> Config:
    """עדכון תצורה בזמן ריצה. מחזיר את התצורה החדשה."""
    global _config
    _config = _config.with_overrides(**kwargs)
    return _config


def reset_config() -> Config:
    """טעינה מחדש ממשתני הסביבה (שימושי בטסטים)."""
    global _config
    _config = Config()
    return _config


def test_ai_connection(config: Config | None = None) -> dict[str, Any]:
    """בודק חיבור חי לספק ה-AI המוגדר."""
    import time
    from .gemini import GeminiEngine

    cfg = config or get_config()
    engine = GeminiEngine(cfg)
    status = engine.status()
    if not status.get("available"):
        return {
            "ok": False,
            "backend": status.get("backend", cfg.backend),
            "error": status.get("reason", "unavailable"),
            "fix": status.get("fix", ""),
        }

    started = time.perf_counter()
    res = engine.generate("Respond with the single word: OK", tier="auto")
    latency = int((time.perf_counter() - started) * 1000)
    if res.ok:
        return {
            "ok": True,
            "backend": cfg.backend,
            "model": res.model,
            "latency_ms": latency,
            "response": res.text.strip(),
        }
    return {
        "ok": False,
        "backend": cfg.backend,
        "error": res.error,
        "latency_ms": latency,
    }
