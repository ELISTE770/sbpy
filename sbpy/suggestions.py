"""Interactive numbered suggestions and action execution for SBpy.

**Trust boundary.** Suggestion text comes from a language model, and model
output is data - never a command. So an option is executable only when SBpy
itself built the action for it:

* ``patch``   - an edit our own patcher produced and verified.
* ``command`` - one of our own shortcuts, by code.
* ``shell``   - a package install, run without a shell and allow-listed.
* ``snippet`` - code the model wrote. Shown, never executed.

There is deliberately no ``eval``/``exec`` of model text here: typing a
number must never be able to run something the user did not read.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from .console import get_console
from .results import Report, ScanResult

_CODE_BLOCK_RE = re.compile(r"`([^`]+)`")
_PIP_RE = re.compile(r"\b(pip\s+install\s+[a-zA-Z0-9_\-]+)\b", re.IGNORECASE)

# A package name, and nothing that a shell would treat as syntax.
_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,99}(\[[A-Za-z0-9,_\-]+\])?$")
_SHELL_METACHARACTERS = set(";&|`$><\n\r\\\"'*?(){}[]!~")


def safe_install_argv(command: str) -> list[str] | None:
    """Turns ``pip install X`` into an argv list, or None if it is not that.

    Anything a shell could reinterpret is rejected outright rather than
    escaped, because the only command we ever need to run is this one.
    """
    if not command or set(command) & _SHELL_METACHARACTERS:
        return None
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if len(parts) < 3:
        return None

    if parts[:2] == ["pip", "install"]:
        packages = parts[2:]
    elif parts[:4] == [sys.executable, "-m", "pip", "install"] or parts[:3] == ["python", "-m", "pip"]:
        packages = parts[parts.index("install") + 1 :] if "install" in parts else []
    else:
        return None

    if not packages or not all(_PACKAGE_RE.match(name) for name in packages):
        return None
    return [sys.executable, "-m", "pip", "install", *packages]


@dataclass
class Option:
    index: int
    title: str
    kind: str  # "patch", "python", "command", "shell"
    command: str = ""
    action: Callable[[], Any] | None = None
    file: str = ""
    line: int = 0
    patch: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def display(self) -> str:
        return f"[{self.index}] {self.title}"


_CURRENT_OPTIONS: list[Option] = []


def get_options() -> list[Option]:
    """Returns the current active list of suggestions."""
    return list(_CURRENT_OPTIONS)


def clear_options() -> None:
    """Clears all active suggestions."""
    global _CURRENT_OPTIONS
    _CURRENT_OPTIONS = []


def set_options(options: list[Option]) -> None:
    """Sets the active suggestions."""
    global _CURRENT_OPTIONS
    _CURRENT_OPTIONS = options


def register_options_from_report(report: Report) -> list[Option]:
    """Generates and registers numbered options from an error Report."""
    from .patcher import build_from_report

    clear_options()
    options: list[Option] = []

    # 1. Check if an automated patch can be constructed directly from the report
    try:
        patch = build_from_report(report)
    except Exception:
        patch = None

    if patch and patch.edits:
        desc = patch.edits[0].description or f"Fix in {os.path.basename(report.file)}"
        options.append(
            Option(
                index=len(options) + 1,
                title=f"Apply auto-fix to {os.path.basename(report.file)} ({desc})",
                kind="patch",
                command=f"apply_patch()",
                action=lambda p=patch: p.apply(backup=True),
                file=report.file,
                patch=patch,
            )
        )

    # 2. Extract actionable suggestions from diagnoses
    for diag in report.sorted_diagnoses():
        sugg = diag.suggestion or ""
        if not sugg:
            continue

        # Check for pip install command
        pip_match = _PIP_RE.search(sugg)
        if pip_match:
            cmd = pip_match.group(1)
            options.append(
                Option(
                    index=len(options) + 1,
                    title=f"Run command: {cmd}",
                    kind="shell",
                    command=cmd,
                )
            )

        # Check for inline python expressions / statements in backticks
        code_matches = _CODE_BLOCK_RE.findall(sugg)
        for code in code_matches:
            code = code.strip()
            # If it's a code snippet, import or fix
            if any(code.startswith(k) for k in ("open(", "import ", "with open", "from ", "def ", "class ")) or ("=" in code and not code.startswith("--")):
                # Avoid duplicate options
                if not any(opt.command == code for opt in options):
                    options.append(
                        Option(
                            index=len(options) + 1,
                            title=f"Show suggested code: {code[:60]}",
                            kind="snippet",
                            command=code,
                        )
                    )

    # 3. Add shortcut escalation option if file is known
    if report.file and os.path.isfile(report.file):
        base_name = os.path.basename(report.file)
        if not any(opt.command == f"/FIX {report.file}" for opt in options):
            options.append(
                Option(
                    index=len(options) + 1,
                    title=f"Run AI fix: /FIX {base_name}",
                    kind="command",
                    command=f"/FIX {report.file}",
                    file=report.file,
                )
            )

    set_options(options)
    return options


def register_options_from_scan(result: ScanResult) -> list[Option]:
    """Generates and registers numbered options from a ScanResult."""
    from .patcher import build_from_scan

    clear_options()
    options: list[Option] = []

    if result.findings and result.target and os.path.isfile(result.target):
        try:
            patch = build_from_scan(result)
        except Exception:
            patch = None

        if patch and patch.edits:
            options.append(
                Option(
                    index=len(options) + 1,
                    title=f"Apply all {len(patch.edits)} auto-fixes to {os.path.basename(result.target)}",
                    kind="patch",
                    command=f"/FIX {result.target}",
                    action=lambda p=patch: p.apply(backup=True),
                    file=result.target,
                    patch=patch,
                )
            )

    set_options(options)
    return options


def execute_option(
    index: int,
    namespace: dict[str, Any] | None = None,
    console: Any = None,
) -> Any:
    """Executes a numbered option by index (1-based)."""
    options = get_options()
    if not options:
        if console:
            console.write(console.paint("  No active suggestions to execute.", "yellow"))
        else:
            print("  No active suggestions to execute.")
        return None

    if index < 1 or index > len(options):
        msg = f"  Option [{index}] not found. Available options: 1 to {len(options)}"
        if console:
            console.write(console.paint(msg, "red"))
        else:
            print(msg)
        return None

    opt = options[index - 1]
    console = console or get_console()
    console.write(console.paint(f"\n  ▶ Executing Option [{opt.index}]: {opt.title}", "green", bold=True))

    try:
        # 1. Dedicated Action callable
        if opt.action is not None:
            res = opt.action()
            if isinstance(res, list) and res:
                console.write(console.paint(f"  ✓ Successfully updated {len(res)} file(s): {', '.join(map(os.path.basename, res))}", "green"))
            elif res is not None:
                console.write(console.paint(f"  Result: {res}", "cyan"))
            return res

        # 2. Patch kind
        if opt.kind == "patch" and opt.patch is not None:
            changed = opt.patch.apply(backup=True)
            if changed:
                console.write(console.paint(f"  ✓ Applied patch to: {', '.join(map(os.path.basename, changed))}", "green"))
            else:
                console.write(console.paint("  ! Patch could not be applied.", "yellow"))
            return changed

        # 3. Command kind (e.g. /FIX, /SFB)
        if opt.kind == "command" or opt.command.startswith("/"):
            from .shortcuts import run as run_shortcut
            from .render import render_scan

            raw_cmd = opt.command.lstrip("/")
            code, _, arg = raw_cmd.partition(" ")
            code = code.upper()
            target = arg.strip() or None
            res = run_shortcut(code, target)
            render_scan(res, root=os.getcwd())
            return res

        # 4. Shell kind - only an allow-listed package install, no shell
        if opt.kind == "shell":
            argv = safe_install_argv(opt.command)
            if argv is None:
                console.write(
                    console.paint(
                        f"  Refused to run: {opt.command}" + chr(10) +
                        "  Only a plain `pip install <package>` may run from a suggestion.",
                        "yellow",
                    )
                )
                return None
            console.write(console.paint(f"  $ {' '.join(argv)}", "grey"))
            proc = subprocess.run(argv, capture_output=True, text=True)
            if proc.stdout:
                console.write(proc.stdout)
            if proc.stderr:
                console.write(console.paint(proc.stderr, "red"))
            if proc.returncode == 0:
                console.write(console.paint("  ✓ Command finished successfully.", "green"))
            else:
                console.write(console.paint(f"  ! Command exited with code {proc.returncode}", "red"))
            return proc.returncode

        # 5. Model-written code: shown, never executed.
        # It arrived as text from a model, so running it on a keystroke would
        # mean executing something the user never read.
        if opt.kind in ("snippet", "python"):
            console.write(console.paint("  Suggested code (not executed):", "cyan"))
            for line in opt.command.splitlines():
                console.write("    " + console.paint(line, "bright_cyan"))
            console.write(
                console.paint("  Review it and paste it in yourself if it is right.", "grey")
            )
            return opt.command

    except Exception as exc:
        console.write(console.paint(f"  ! Error executing option [{opt.index}]: {exc}", "red"))
        return None
