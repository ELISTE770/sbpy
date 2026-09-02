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
from pathlib import Path
from typing import Any, Callable

from .config import get_config
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

    installer_type, base_argv = detect_package_installer()

    if parts[:2] == ["pip", "install"]:
        packages = parts[2:]
    elif parts[:2] == ["poetry", "add"]:
        packages = parts[2:]
        base_argv = ["poetry", "add"]
    elif parts[:2] == ["pipenv", "install"]:
        packages = parts[2:]
        base_argv = ["pipenv", "install"]
    elif parts[:2] == ["uv", "add"]:
        packages = parts[2:]
        base_argv = ["uv", "add"]
    elif parts[:3] == ["uv", "pip", "install"]:
        packages = parts[3:]
        base_argv = ["uv", "pip", "install"]
    elif parts[:4] == [sys.executable, "-m", "pip", "install"] or parts[:3] == ["python", "-m", "pip"]:
        packages = parts[parts.index("install") + 1 :] if "install" in parts else []
    else:
        return None

    if not packages or not all(_PACKAGE_RE.match(name) for name in packages):
        return None
    return [*base_argv, *packages]


def detect_package_installer() -> tuple[str, list[str]]:
    """Detects active virtualenv or package manager (poetry, pipenv, uv, venv)."""
    cwd = Path.cwd()
    if (cwd / "poetry.lock").exists():
        return "poetry", ["poetry", "add"]
    if (cwd / "uv.lock").exists():
        return "uv", ["uv", "add"]
    if (cwd / "Pipfile").exists():
        return "pipenv", ["pipenv", "install"]

    venv_dir = os.environ.get("VIRTUAL_ENV")
    if not venv_dir:
        for candidate in (".venv", "venv"):
            if (cwd / candidate).is_dir():
                venv_dir = str(cwd / candidate)
                break

    if venv_dir:
        py_exe = (
            Path(venv_dir) / "Scripts" / "python.exe"
            if os.name == "nt"
            else Path(venv_dir) / "bin" / "python"
        )
        if py_exe.exists():
            return "venv", [str(py_exe), "-m", "pip", "install"]

    return "pip", [sys.executable, "-m", "pip", "install"]


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

    # 1. Check if an automated file patch can be constructed directly from the report
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
                command="apply_patch()",
                action=lambda p=patch: p.apply(backup=True),
                file=report.file,
                patch=patch,
            )
        )

    # 2. Extract actionable suggestions from diagnoses
    for diag in report.sorted_diagnoses():
        sugg = diag.suggestion or ""
        patch_text = (diag.patch or "").strip()
        meta = diag.meta or {}

        # 2a. Check direct patch
        if patch_text:
            if re.match(r"^pip\s+install?\b", patch_text, re.IGNORECASE):
                norm_cmd = re.sub(r"^pip\s+instal\b", "pip install", patch_text, flags=re.IGNORECASE)
                if not any(opt.command == norm_cmd for opt in options):
                    options.append(
                        Option(
                            index=len(options) + 1,
                            title=f"Run command: {norm_cmd}",
                            kind="shell",
                            command=norm_cmd,
                        )
                    )
            elif patch_text.lower() in ("sbpy", "setup", "models", "ui", "heal", "agent", "find", "gen", "undo", "commit") or patch_text.startswith("/"):
                cmd = patch_text if patch_text.startswith("/") else f"/{patch_text.upper()}"
                if not any(opt.command == cmd for opt in options):
                    options.append(
                        Option(
                            index=len(options) + 1,
                            title=f"Run SBpy command: {cmd}",
                            kind="command",
                            command=cmd,
                        )
                    )
            else:
                # Python code / transliterated statement / expression
                if not any(opt.command == patch_text for opt in options):
                    options.append(
                        Option(
                            index=len(options) + 1,
                            title=f"Execute / Apply Python code: {patch_text[:60]}",
                            kind="python",
                            command=patch_text,
                        )
                    )

        # 2b. Check for pip install command in suggestion
        pip_match = re.search(r"\b(pip\s+install?\s+[a-zA-Z0-9_\-]+)\b", sugg, re.IGNORECASE)
        if pip_match:
            cmd = re.sub(r"^pip\s+instal\b", "pip install", pip_match.group(1), flags=re.IGNORECASE)
            if not any(opt.command == cmd for opt in options):
                options.append(
                    Option(
                        index=len(options) + 1,
                        title=f"Run command: {cmd}",
                        kind="shell",
                        command=cmd,
                    )
                )

        # 2c. Check meta target/good
        good = meta.get("good") or meta.get("target")
        if good and isinstance(good, str):
            good = good.strip()
            if not any(opt.command == good for opt in options):
                if re.match(r"^pip\s+install?\b", good, re.IGNORECASE):
                    norm = re.sub(r"^pip\s+instal\b", "pip install", good, flags=re.IGNORECASE)
                    options.append(Option(index=len(options) + 1, title=f"Run command: {norm}", kind="shell", command=norm))
                elif good.lower() in ("sbpy", "setup", "models", "ui", "heal", "agent", "find", "gen", "undo", "commit"):
                    cmd = f"/{good.upper()}"
                    options.append(Option(index=len(options) + 1, title=f"Run SBpy command: {cmd}", kind="command", command=cmd))
                elif not any(opt.command == good for opt in options):
                    options.append(Option(index=len(options) + 1, title=f"Execute Python code: {good}", kind="python", command=good))

        # 2d. Check for inline python expressions / statements in backticks
        code_matches = _CODE_BLOCK_RE.findall(sugg)
        for code in code_matches:
            code = code.strip()
            if any(code.startswith(k) for k in ("open(", "import ", "with open", "from ", "def ", "class ")) or ("=" in code and not code.startswith("--")):
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

    # 4. Provide option to send or retry AI (Flash) without '+' suffix
    cfg = get_config()
    lang = getattr(report, "lang", None) or cfg.language
    if getattr(report, "escalated", False):
        ai_title = "לשלוח שוב ל-AI (Flash)" if lang == "he" else "Retry sending to AI (Flash)"
    else:
        ai_title = "שלח ל-AI (Flash)" if lang == "he" else "Send to AI (Flash)"

    if not any(opt.command in ("+", "/+", "/ai_escalate") for opt in options):
        options.append(
            Option(
                index=len(options) + 1,
                title=ai_title,
                kind="command",
                command="/+",
            )
        )

    # 5. Provide easy numbered option to update SBpy if update is available
    from .updater import read_cached_update
    up_cached = read_cached_update(cfg)
    if up_cached and up_cached.get("update_available"):
        latest = up_cached.get("latest_version")
        if not any(opt.command in ("/UPDATE", "/UPGRADE") for opt in options):
            options.append(
                Option(
                    index=len(options) + 1,
                    title=f"Upgrade SBpy to v{latest} from GitHub (/UPDATE)",
                    kind="command",
                    command="/UPDATE",
                )
            )

    set_options(options)
    return options


def register_options_from_scan(result: ScanResult) -> list[Option]:
    """Generates and registers numbered options from a ScanResult."""
    from .patcher import build_from_scan

    clear_options()
    options: list[Option] = []
    patch = None

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


def choose_option_interactively(options: list[Option], console: Any = None) -> Option | None:
    """Lets the user select an option using real-time arrow keys or numeric prompt."""
    if not options:
        return None
    console = console or get_console()

    # If terminal is interactive, use arrow-key picker
    if getattr(sys.stdin, "isatty", lambda: False)():
        try:
            from .keyboard import run_interactive_arrow_picker

            items = [(str(opt.index), f"[{opt.index}] {opt.title}", opt.kind) for opt in options]
            picked = run_interactive_arrow_picker(items, title="Select Action to Execute", console=console)
            if picked is not None:
                idx_str = picked[0]
                idx = int(idx_str)
                return next((o for o in options if o.index == idx), None)
            return None
        except Exception:  # sbpy: ignore=silent-except
            pass

    return options[0]


def execute_option(
    index: int | None = None,
    namespace: dict[str, Any] | None = None,
    console: Any = None,
) -> Any:
    """Executes a numbered option by index (1-based), or prompts interactively if index is None."""
    options = get_options()
    console = console or get_console()
    if not options:
        console.write(console.paint("  No active suggestions to execute.", "yellow"))
        return None

    if index is None:
        if len(options) == 1:
            index = 1
        else:
            chosen = choose_option_interactively(options, console=console)
            if chosen is None:
                return None
            index = chosen.index

    if index < 1 or index > len(options):
        msg = f"  Option [{index}] not found. Available options: 1 to {len(options)}"
        console.write(console.paint(msg, "red"))
        return None

    opt = options[index - 1]
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

        # 3. Command kind (e.g. /+, /FIX, /SFB, /SETUP)
        if opt.kind == "command" or opt.command.startswith("/"):
            if opt.command in ("+", "/+", "/ai", "/ask", "/ai_escalate"):
                from .config import TIER_COMMAND
                from .hooks import last_error, last_report
                from .ladder import diagnose, diagnose_text
                from .render import render_report

                err = last_error()
                rep = last_report()
                if err is not None:
                    console.write(console.paint("  🧠 Sending full error context to AI (Flash)...", "cyan", bold=True))
                    new_report = diagnose(err, force_gemini=True, tier=TIER_COMMAND)
                    render_report(new_report, console=console)
                    return new_report
                elif rep is not None:
                    console.write(console.paint("  🧠 Sending full error context to AI (Flash)...", "cyan", bold=True))
                    new_report = diagnose_text(f"{rep.exc_type}: {rep.exc_message}\n{rep.where}", force_gemini=True, tier=TIER_COMMAND)
                    render_report(new_report, console=console)
                    return new_report
                else:
                    console.write(console.paint("  No recent error found to send to AI.", "yellow"))
                    return None

            if opt.command.upper() in ("/UPDATE", "/UPGRADE", "UPDATE", "UPGRADE"):
                from .updater import run_upgrade
                return run_upgrade(console=console)

            from .shortcuts import run as run_shortcut
            from .render import render_scan

            raw_cmd = opt.command.lstrip("/")
            code, _, arg = raw_cmd.partition(" ")
            code = code.upper()
            target = arg.strip() or None
            res = run_shortcut(code, target)
            render_scan(res, root=os.getcwd())
            return res

        # 4. Shell kind - package install
        if opt.kind == "shell":
            argv = safe_install_argv(opt.command)
            if argv is None:
                console.write(
                    console.paint(
                        f"  Refused to run: {opt.command}\n"
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

        # 5. Code snippet / Python statement: shown clearly for user review
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
