"""בדיקת עדכונים אוטומטית מ-GitHub עבור SBpy.

עקרונות:
- בדיקה אסינכרונית ברקע (daemon thread) - לא מעכבת כלום.
- מטמון מקומי (~/.sbpy/update_cache.json) כדי לא לפנות לרשת בכל פקודה (כל 6 שעות).
- מימוש stdlib מלא (urllib.request) ללא תלויות חיצוניות.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import Config, get_config


CACHE_FILE_NAME = "update_cache.json"
DEFAULT_REPO = "eliste770-cmyk/sbpy"


def _parse_version_tuple(v_str: str) -> tuple[int, ...]:
    clean = re.sub(r"^[^\d]*", "", v_str.strip())
    nums = re.findall(r"\d+", clean)
    if not nums:
        return (0,)
    return tuple(int(x) for x in nums)


def _cache_path(config: Config | None = None) -> Path:
    cfg = config or get_config()
    home = cfg.home
    return home / CACHE_FILE_NAME


def read_cached_update(config: Config | None = None) -> dict[str, Any] | None:
    path = _cache_path(config)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:  # sbpy: ignore=silent-except
        pass
    return None


def write_cached_update(data: dict[str, Any], config: Config | None = None) -> None:
    path = _cache_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception:  # sbpy: ignore=silent-except
        pass


def fetch_remote_version(repo: str = DEFAULT_REPO, timeout: float = 3.0) -> str | None:
    """מושך את הגרסה האחרונה מ-pyproject.toml ב-GitHub."""
    url = f"https://raw.githubusercontent.com/{repo}/main/pyproject.toml"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"sbpy-updater/{sys.version_info.major}.{sys.version_info.minor}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                content = resp.read().decode("utf-8", errors="replace")
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1).strip()
    except Exception:  # sbpy: ignore=silent-except
        pass

    # Fallback to GitHub Releases API
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    api_req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "sbpy-updater",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    try:
        with urllib.request.urlopen(api_req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                tag = data.get("tag_name") or data.get("name")
                if tag:
                    return re.sub(r"^v", "", str(tag).strip())
    except Exception:  # sbpy: ignore=silent-except
        pass

    return None


def check_for_updates(
    *,
    config: Config | None = None,
    force: bool = False,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """בודק אם קיים עדכון חדש ב-GitHub."""
    from . import __version__ as current_version

    cfg = config or get_config()
    repo = getattr(cfg, "github_repo", DEFAULT_REPO) or DEFAULT_REPO
    interval_seconds = getattr(cfg, "update_interval_hours", 6) * 3600

    now = time.time()
    cached = read_cached_update(cfg)
    if not force and cached:
        last_checked = cached.get("last_checked", 0)
        if (now - last_checked) < interval_seconds:
            return cached

    remote_ver = fetch_remote_version(repo=repo, timeout=timeout)
    if not remote_ver:
        result = {
            "last_checked": now,
            "update_available": False,
            "current_version": current_version,
            "latest_version": current_version,
            "repo": repo,
            "status": "network_unavailable",
        }
        write_cached_update(result, cfg)
        return result

    curr_tuple = _parse_version_tuple(current_version)
    remote_tuple = _parse_version_tuple(remote_ver)
    is_newer = remote_tuple > curr_tuple

    install_cmd = f"pip install --upgrade git+https://github.com/{repo}"
    result = {
        "last_checked": now,
        "update_available": is_newer,
        "current_version": current_version,
        "latest_version": remote_ver,
        "repo": repo,
        "url": f"https://github.com/{repo}",
        "install_cmd": install_cmd,
        "status": "ok",
    }
    write_cached_update(result, cfg)
    return result


def start_background_check(config: Config | None = None) -> None:
    """מתחיל בדיקת עדכונים שקטה ברקע ב-Daemon thread."""
    cfg = config or get_config()
    if not getattr(cfg, "check_updates", True) or getattr(cfg, "offline", False):
        return

    now = time.time()
    cached = read_cached_update(cfg)
    interval_seconds = getattr(cfg, "update_interval_hours", 6) * 3600
    if cached and (now - cached.get("last_checked", 0)) < interval_seconds:
        return

    thread = threading.Thread(
        target=check_for_updates,
        kwargs={"config": cfg, "force": False, "timeout": 3.0},
        daemon=True,
    )
    thread.start()


def get_update_notification(config: Config | None = None) -> str | None:
    """מחזיר הודעת עדכון אם נמצאה גרסה חדשה במטמון."""
    cfg = config or get_config()
    cached = read_cached_update(cfg)
    if not cached or not cached.get("update_available"):
        return None

    curr = cached.get("current_version", "")
    latest = cached.get("latest_version", "")
    cmd = cached.get("install_cmd", f"pip install -U git+https://github.com/{DEFAULT_REPO}")
    lang = getattr(cfg, "language", "en")

    if lang == "he":
        return f"🔔 קיים עדכון חדש ל-SBpy: v{curr} -> v{latest} | הרץ: {cmd}"
    return f"🔔 SBpy update available: v{curr} -> v{latest} | Run: {cmd}"


def run_upgrade(config: Config | None = None, console: Any = None) -> int:
    """מריץ שדרוג ישיר של SBpy מ-GitHub."""
    import subprocess
    from .console import get_console

    cfg = config or get_config()
    con = console or get_console(cfg.color)
    repo = getattr(cfg, "github_repo", DEFAULT_REPO) or DEFAULT_REPO
    cmd_str = f"pip install --upgrade git+https://github.com/{repo}"

    con.write()
    con.write(con.paint("  📦 Upgrading SBpy to latest version from GitHub...", "cyan", bold=True))
    con.write(con.paint(f"  Running: {sys.executable} -m {cmd_str}\n", "grey"))

    code = subprocess.call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        f"git+https://github.com/{repo}",
    ])
    if code == 0:
        con.write(con.paint("\n  ✓ Successfully upgraded SBpy from GitHub!", "green", bold=True))
        con.write(con.paint("  Restart your shell or REPL to apply the latest changes.\n", "green"))
    else:
        con.write(con.paint(f"\n  ! Upgrade exited with code {code}. You can run manually:\n    {cmd_str}\n", "yellow"))
    return code
