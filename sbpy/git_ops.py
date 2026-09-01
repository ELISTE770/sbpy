"""Git Integration, Patch Undo/Rollback, and Semantic Commit generation for SBpy."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from .console import get_console

BACKUP_SUFFIX = ".sbpy.bak"

@dataclass
class UndoRecord:
    file: str
    original_content: str
    timestamp: float


_UNDO_STACK: list[UndoRecord] = []


def record_backup(file: str, original_content: str) -> None:
    """Records an undo state in memory and creates a physical .sbpy.bak file."""
    import time

    abs_path = os.path.abspath(file)
    _UNDO_STACK.append(UndoRecord(file=abs_path, original_content=original_content, timestamp=time.time()))
    try:
        with open(abs_path + BACKUP_SUFFIX, "w", encoding="utf-8", newline="\n") as f:
            f.write(original_content)
    except OSError:  # sbpy: ignore=silent-except
        pass


def snapshot(files: list[str] | tuple[str, ...]) -> None:
    """Creates a snapshot backup for each file in the given sequence."""
    for f in files:
        if os.path.isfile(f):
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as handle:
                    record_backup(f, handle.read())
            except OSError:  # sbpy: ignore=silent-except
                pass


def undo_last_patch(console: Any = None) -> str | None:
    """Reverts the last applied patch from the undo stack or from .sbpy.bak files."""
    console = console or get_console()

    if _UNDO_STACK:
        record = _UNDO_STACK.pop()
        try:
            with open(record.file, "w", encoding="utf-8", newline="\n") as f:
                f.write(record.original_content)
            console.write(console.paint(f"  ✓ Successfully restored {os.path.basename(record.file)} to previous state.", "green", bold=True))
            return record.file
        except OSError as exc:
            console.write(console.paint(f"  ! Failed to restore {record.file}: {exc}", "red"))
            return None

    # If memory stack is empty, search for .sbpy.bak files in working directory
    for root, _, files in os.walk(os.getcwd()):
        for name in files:
            if name.endswith(BACKUP_SUFFIX):
                bak_path = os.path.join(root, name)
                target_path = bak_path[: -len(BACKUP_SUFFIX)]
                try:
                    shutil.copy2(bak_path, target_path)
                    os.remove(bak_path)
                    console.write(console.paint(f"  ✓ Restored {os.path.basename(target_path)} from {name}", "green", bold=True))
                    return target_path
                except OSError as exc:
                    console.write(console.paint(f"  ! Error restoring {bak_path}: {exc}", "red"))
                    return None

    console.write(console.paint("  No backup or undo history found to revert.", "yellow"))
    return None


def is_git_repo(path: str = ".") -> bool:
    """Checks if the directory is inside a Git repository."""
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return res.returncode == 0 and "true" in res.stdout.lower()
    except Exception:
        return False


def git_commit_changes(files: list[str] | None = None, message: str = "", console: Any = None) -> bool:
    """Stages files and creates a git commit."""
    console = console or get_console()
    if not is_git_repo():
        console.write(console.paint("  ! Current directory is not a git repository.", "yellow"))
        return False

    if not files:
        # Stage all modified python files
        cmd_add = ["git", "add", "-u"]
    else:
        cmd_add = ["git", "add"] + files

    try:
        subprocess.run(cmd_add, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as exc:
        console.write(console.paint(f"  ! Git add failed: {exc}", "red"))
        return False

    if not message:
        base_names = [os.path.basename(f) for f in (files or [])]
        subject = f"fix({', '.join(base_names)})" if base_names else "fix: apply automated SBpy code fixes"
        message = f"{subject}\n\nAutomated fixes applied via SBpy."

    try:
        res = subprocess.run(
            ["git", "commit", "-m", message],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode == 0:
            console.write(console.paint(f"  ✓ Git commit created: {message.splitlines()[0]}", "green", bold=True))
            return True
        else:
            console.write(console.paint(f"  ! Git commit output: {res.stdout or res.stderr}", "yellow"))
            return False
    except Exception as exc:
        console.write(console.paint(f"  ! Git commit error: {exc}", "red"))
        return False


PRE_COMMIT_SCRIPT = """#!/usr/bin/env sh
# SBpy Pre-Commit Hook: Runs local security and bug checks before commit
echo "🔍 Running SBpy pre-commit quality & security checks..."
sbpy scan --changed --fail-on=error
if [ $? -ne 0 ]; then
    echo "❌ SBpy detected critical errors or security risks. Commit aborted."
    echo "💡 Run 'sbpy fix' or 'sbpy scan' to inspect and auto-fix."
    exit 1
fi
echo "✓ SBpy checks passed cleanly."
exit 0
"""

GITHUB_ACTIONS_WORKFLOW = """name: SBpy Code Security & Quality Scan

on:
  push:
    branches: [ main, master, dev ]
  pull_request:
    branches: [ main, master, dev ]

jobs:
  sbpy-audit:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Dependencies & SBpy
        run: |
          python -m pip install --upgrade pip
          pip install -e .

      - name: Run SBpy Security & Bug Scan
        run: |
          sbpy scan --github --fail-on=error
"""


def install_git_pre_commit_hook(repo_path: str = ".", console: Any = None) -> bool:
    """Installs a pre-commit git hook to prevent commiting broken or vulnerable code."""
    console = console or get_console()
    git_dir = os.path.join(os.path.abspath(repo_path), ".git")
    if not os.path.isdir(git_dir):
        console.write(console.paint("  ! No .git directory found to install hook into.", "red"))
        return False

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook_file = os.path.join(hooks_dir, "pre-commit")

    try:
        with open(hook_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(PRE_COMMIT_SCRIPT)
        if os.name != "nt":
            import stat

            os.chmod(hook_file, os.stat(hook_file).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        console.write(console.paint(f"  ✓ Git pre-commit hook installed successfully at: {hook_file}", "green", bold=True))
        return True
    except Exception as exc:
        console.write(console.paint(f"  ! Failed to install git hook: {exc}", "red"))
        return False


def generate_github_ci_workflow(repo_path: str = ".", console: Any = None) -> str | None:
    """Generates a GitHub Actions workflow for automated PR auditing."""
    console = console or get_console()
    wf_dir = os.path.join(os.path.abspath(repo_path), ".github", "workflows")
    os.makedirs(wf_dir, exist_ok=True)
    wf_file = os.path.join(wf_dir, "sbpy.yml")

    try:
        with open(wf_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(GITHUB_ACTIONS_WORKFLOW)
        console.write(console.paint(f"  ✓ GitHub Actions CI workflow created at: {wf_file}", "green", bold=True))
        return wf_file
    except Exception as exc:
        console.write(console.paint(f"  ! Failed to create GitHub Actions CI workflow: {exc}", "red"))
        return None
