"""Terminal UI spinner and progress bar for SBpy."""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def is_interactive_terminal() -> bool:
    """Returns True if running in an interactive terminal (not piped and not CI)."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


class Spinner:
    """Thread-safe live terminal animated spinner."""

    def __init__(self, message: str = "Thinking...", color: str = "\033[36m") -> None:
        self.message = message
        self.color = color
        self.reset_code = "\033[0m"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._interactive = is_interactive_terminal()
        self._start_time = 0.0

    def __enter__(self) -> "Spinner":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    def start(self) -> None:
        if not self._interactive:
            return
        self._start_time = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def update_message(self, message: str) -> None:
        self.message = message

    def _spin(self) -> None:
        frame_idx = 0
        while not self._stop_event.is_set():
            elapsed = time.time() - self._start_time
            frame = SPINNER_FRAMES[frame_idx % len(SPINNER_FRAMES)]
            msg = f"\r  {self.color}{frame}\033[0m {self.message} \033[90m({elapsed:.1f}s)\033[0m"
            try:
                sys.stdout.write(msg)
                sys.stdout.flush()
            except Exception:  # sbpy: ignore=silent-except
                break
            frame_idx += 1
            time.sleep(0.08)

    def stop(self, success_message: str | None = None) -> None:
        if not self._interactive:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        try:
            # Clear line
            sys.stdout.write("\r\033[K")
            if success_message:
                sys.stdout.write(f"  \033[32m✓\033[0m {success_message}\n")
            sys.stdout.flush()
        except Exception:  # sbpy: ignore=silent-except
            pass


def render_progress_bar(current: int, total: int, prefix: str = "Scanning", suffix: str = "", length: int = 30) -> str:
    """Renders a single-line ASCII progress bar string."""
    if total <= 0:
        total = 1
    percent = min(1.0, current / total)
    filled = int(length * percent)
    bar = "█" * filled + "░" * (length - filled)
    return f"{prefix} [{bar}] {int(percent * 100)}% ({current}/{total}) {suffix}".strip()
