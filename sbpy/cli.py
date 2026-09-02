"""Command line interface for SBpy (CLI).

    sbpy                          Opens the interactive REPL (REPL)
    sbpy run app.py               Runs a file with active error diagnostics
    sbpy sfb [path...]            Search For Bugs
    sbpy sec [path...]            Security scan
    sbpy opt [path...]            Performance optimization
    sbpy cmp [path...]            Complexity metric
    sbpy mod [path...]            Modernize Python syntax
    sbpy fix [path...]            Apply automatic fixes
    sbpy scan [path...]           Find directives / in the code
    sbpy dev [path...]            Run watcher on file changes
    sbpy explain "שגיאה..."       Diagnose pasted error message
    sbpy doctor                   Health check and connections
    sbpy usage                    Budget and token usage report
    sbpy cache / index / learn    Manage caches and local data
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence

from . import __version__, budget, learn
from .batch import review_many
from .cache import Cache
from .config import (
    TIER_COMMAND,
    TIER_PRO,
    Config,
    configure,
    get_config,
)
from .console import Console, get_console
from .gemini import get_engine, sdk_available
from .index import build as build_index, stats as index_stats
from .integrations import FORMATS, changed_files, is_git_repo, render_format
from .ladder import diagnose_text
from .patcher import build_from_findings
from .render import render_report, render_scan
from .results import Finding, ScanResult
from .shortcuts import (
    ESCALATE_NEVER,
    SHORTCUTS,
    list_shortcuts,
    run as run_shortcut,
    scan_directives,
)

# Encoding protection for Windows ב-Windows terminal
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # sbpy: ignore=silent-except
        pass

SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".tox",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".hypothesis",
        ".eggs",
        "build",
        "dist",
    }
)

SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2, "critical": 3}

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

PRO_TOKEN = "+"


def iter_python_files(target: str) -> list[str]:
    """Collects all Python files under target, skipping noise directories."""
    if os.path.isfile(target):
        return [target]
    found: list[str] = []
    for root, directories, files in os.walk(target):
        directories[:] = [
            d for d in directories if d not in SKIP_DIRECTORIES and not d.startswith(".")
        ]
        for name in sorted(files):
            if name.endswith(".py"):
                found.append(os.path.join(root, name))
    return found


def _is_interactive(stream: object = None) -> bool:
    """Is environment an interactive TTY."""
    if os.environ.get("SBPY_NO_SHELL"):
        return False
    for stream_obj in (sys.stdin, sys.stdout):
        if stream_obj is None or not getattr(stream_obj, "isatty", lambda: False)():
            return False
    return True


def _worst_severity(results: Iterable[ScanResult]) -> int:
    worst = -1
    for result in results:
        for finding in result.findings:
            rank = SEVERITY_RANK.get(finding.severity, 0)
            if rank > worst:
                worst = rank
    return worst


def _exit_code(results: Iterable[ScanResult], fail_on: str = "error") -> int:
    threshold = SEVERITY_RANK.get(fail_on, SEVERITY_RANK["error"])
    if _worst_severity(results) >= threshold:
        return EXIT_FINDINGS
    return EXIT_OK


def _apply_common(args: argparse.Namespace) -> Config:
    overrides: dict[str, object] = {}
    if getattr(args, "offline", False):
        overrides["offline"] = True
    if getattr(args, "lang", None):
        overrides["language"] = args.lang
    if getattr(args, "no_color", False):
        overrides["color"] = False
    if getattr(args, "no_cache", False):
        overrides["cache_enabled"] = False
    if getattr(args, "model", None):
        overrides["model_auto"] = args.model
        overrides["model_command"] = args.model
        overrides["model_pro"] = args.model
    if getattr(args, "backend", None):
        overrides["backend"] = args.backend
    if getattr(args, "profile", None):
        overrides["profile"] = args.profile

    if overrides:
        return configure(**overrides)
    return get_config()


def _resolve_paths(args: argparse.Namespace) -> list[str]:
    """Extracts file list from args (or git diff if --changed)."""
    if getattr(args, "changed", False):
        root = getattr(args, "path", None) or "."
        if not is_git_repo(root):
            print("  Error: --changed requires a git repository", file=sys.stderr)
            return []
        return changed_files(root, include_untracked=True)

    targets = getattr(args, "paths", None) or getattr(args, "path", None) or ["."]
    if isinstance(targets, str):
        targets = [targets]

    all_files: list[str] = []
    for target in targets:
        if os.path.isfile(target):
            all_files.append(target)
        elif os.path.isdir(target):
            all_files.extend(iter_python_files(target))
        else:
            all_files.append(target)
    return sorted(list(dict.fromkeys(all_files)))


PROFILE_MIN_SEVERITY = {"quiet": "error", "normal": "warn", "strict": "info"}


def apply_profile(results: list[ScanResult], profile: str) -> list[ScanResult]:
    """Drops findings below the profile's severity floor.

    Filtering happens at the very end, so the exit code and every output
    format see the same list the user does.
    """
    floor = SEVERITY_RANK.get(PROFILE_MIN_SEVERITY.get(profile, "info"), 0)
    if floor <= 0:
        return results
    for result in results:
        result.findings = [
            finding
            for finding in result.findings
            if SEVERITY_RANK.get(finding.severity, 0) >= floor
        ]
    return results


def _emit(args: argparse.Namespace, results: list[ScanResult], fmt: str | None = None) -> int:
    results = apply_profile(results, get_config().profile)

    fmt = fmt or getattr(args, "format", None)
    if getattr(args, "json", False):
        fmt = "json"
    elif getattr(args, "github", False):
        fmt = "github"
    elif getattr(args, "sarif", False):
        fmt = "sarif"

    if fmt:
        output = render_format(fmt, results)
        if output:
            print(output)
        return _exit_code(results, getattr(args, "fail_on", "error"))

    config = get_config()
    console = get_console(config.color)
    root = os.getcwd()
    for result in results:
        render_scan(result, config=config, console=console, root=root)
    return _exit_code(results, getattr(args, "fail_on", "error"))


# ======================================================================
# Main commands
# ======================================================================
def cmd_run(args: argparse.Namespace) -> int:
    from . import hooks

    config = _apply_common(args)
    hooks.install(config=config)

    script = args.script
    if not os.path.exists(script):
        print(f"  Error: File not found: {script}", file=sys.stderr)
        return EXIT_ERROR

    sys.argv = [script, *args.script_args]
    directory = os.path.dirname(os.path.abspath(script))
    if directory not in sys.path:
        sys.path.insert(0, directory)

    try:
        runpy.run_path(script, run_name="__main__")
        return EXIT_OK
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        # hooks._excepthook will handle diagnostics
        return EXIT_ERROR


def cmd_shell(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    if getattr(sys, "frozen", False):
        from . import _startup
        from .shell import run_console

        _startup._banner(short=getattr(args, "short", False))
        return run_console(globals(), config)

    startup = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_startup.py")

    environment = dict(os.environ)
    if config.offline:
        environment["SBPY_OFFLINE"] = "1"
    if not config.color:
        environment["SBPY_COLOR"] = "0"
    if config.language != "he":
        environment["SBPY_LANG"] = config.language
    if getattr(args, "short", False):
        environment["SBPY_SHORT_BANNER"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"

    root = os.getcwd()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = f"{root}{os.pathsep}{existing}" if existing else root

    command = [sys.executable, "-i", startup]
    return subprocess.call(command, env=environment)


@dataclass
class _ScanOptions:
    """The per-invocation switches that every scan path needs."""

    pro: bool = False
    deep: bool = False
    question: str = ""
    batch: bool = True

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "_ScanOptions":
        return cls(
            pro=bool(getattr(args, "pro", False)),
            deep=bool(getattr(args, "deep", False)),
            question=getattr(args, "question", "") or "",
            batch=bool(getattr(args, "batch", True)),
        )


def _error_result(code: str, path: str, rule: str, message: str) -> ScanResult:
    result = ScanResult(shortcut=code, target=path)
    result.findings.append(Finding(rule=rule, message=message, severity="error", file=path))
    return result


def common_root(paths: Sequence[str]) -> str:
    """The deepest directory that contains every path."""
    directories = [
        path if os.path.isdir(path) else (os.path.dirname(os.path.abspath(path)) or ".")
        for path in paths
        if path
    ]
    if not directories:
        return "."
    if len(directories) == 1:
        return directories[0]
    try:
        return os.path.commonpath([os.path.abspath(d) for d in directories])
    except ValueError:
        # Different drives on Windows - no shared root
        return directories[0]


def _run_project_wide(
    code: str, paths: Sequence[str], options: _ScanOptions, config: Config
) -> list[ScanResult]:
    """Runs a whole-project analysis exactly once.

    @DEAD / @ARCH / @CLONE build a graph over every file. Running them per
    file would report the same global findings once for each file scanned.
    """
    root = common_root(paths)
    result = run_shortcut(
        code, root, deep=options.deep, pro=options.pro, question=options.question, config=config
    )
    result.target = os.path.relpath(root, os.getcwd()) if root != "." else "."
    result.dedupe()
    return [result]


def _run_one(code: str, path: str, options: _ScanOptions, config: Config) -> ScanResult:
    if not os.path.exists(path):
        return _error_result(code, path, "not-found", f"File does not exist: {path}")
    try:
        return run_shortcut(
            code,
            path,
            deep=options.deep,
            pro=options.pro,
            question=options.question,
            config=config,
        )
    except OSError as exc:
        return _error_result(code, path, "os-error", str(exc))


def _local_pass_and_pending(
    code: str, paths: Sequence[str], options: _ScanOptions, config: Config
) -> tuple[list[ScanResult], list[tuple[str, str]], dict[str, str]]:
    """Local scan for every file; files with no findings become batch candidates."""
    results: list[ScanResult] = []
    pending: list[tuple[str, str]] = []
    name_to_path: dict[str, str] = {}

    for path in paths:
        if not os.path.exists(path):
            results.append(_error_result(code, path, "not-found", f"File does not exist: {path}"))
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                source = handle.read()
        except OSError as exc:
            results.append(_error_result(code, path, "os-error", str(exc)))
            continue

        local = run_shortcut(
            code,
            path,
            deep=False,
            pro=options.pro,
            question=options.question,
            config=config,
            local_only=True,
        )
        results.append(local)
        if not local.findings:
            name = os.path.basename(path)
            pending.append((name, source))
            name_to_path[name] = path

    return results, pending, name_to_path


def _attach_batch_findings(
    findings: Sequence[Finding], results: list[ScanResult], name_to_path: dict[str, str]
) -> None:
    by_target = {result.target: result for result in results}
    for finding in findings:
        real_path = name_to_path.get(finding.file, finding.file)
        target = by_target.get(real_path) or by_target.get(os.path.basename(real_path))
        if target is None:
            continue
        finding.file = real_path
        target.findings.append(finding)
        target.escalated = True
        target.escalation_reason = "batch"


def _run_shortcut_over(
    code: str,
    paths: list[str],
    args: argparse.Namespace,
    config: Config,
) -> list[ScanResult]:
    """Runs one shortcut over a file list, choosing the right strategy."""
    shortcut = SHORTCUTS[code]
    options = _ScanOptions.from_args(args)

    if shortcut.project_wide:
        return _run_project_wide(code, paths, options, config)

    batching = (
        options.batch
        and len(paths) > 1
        and not options.deep
        and shortcut.escalate != ESCALATE_NEVER
    )
    if not batching:
        results = [_run_one(code, path, options, config) for path in paths]
        for result in results:
            result.dedupe()
        return results

    results, pending, name_to_path = _local_pass_and_pending(code, paths, options, config)
    if pending and config.can_call_gemini:
        findings, _outcome = review_many(
            code,
            pending,
            focus=shortcut.focus,
            config=config,
            tier=TIER_PRO if options.pro else TIER_COMMAND,
        )
        _attach_batch_findings(findings, results, name_to_path)

    for result in results:
        result.dedupe()
    return results


def cmd_shortcut(args: argparse.Namespace, code: str) -> int:
    config = _apply_common(args)
    paths = _resolve_paths(args)
    if not paths:
        paths = ["."]

    try:
        results = _run_shortcut_over(code, paths, args, config)
    except Exception as exc:
        console = get_console(config.color)
        console.write(console.paint(f"  Error: {exc}", "red"))
        return EXIT_ERROR

    if code == "TST" and getattr(args, "verify", False):
        _verify_generated_tests(args, results, paths, config)

    if getattr(args, "fix", False):
        return _handle_fix(args, results, config, get_console(config.color))

    return _emit(args, results)


def _verify_generated_tests(
    args: argparse.Namespace,
    results: list[ScanResult],
    paths: Sequence[str],
    config: Config,
) -> None:
    """Runs the tests @TST wrote, and repairs them once if they fail."""
    from . import testgen

    console = get_console(config.color)
    for result, path in zip(results, paths):
        if not result.text:
            continue
        outcome = testgen.verify(
            result,
            target_path=path or "",
            config=config,
            pro=getattr(args, "pro", False),
            keep=getattr(args, "out", "") or "",
        )
        result.tokens += outcome.tokens
        if outcome.passed:
            location = f" -> {outcome.path}" if outcome.path else ""
            console.write(
                console.paint(
                    f"  Tests passed (attempt {outcome.attempts}){location}", "green", bold=True
                )
            )
            result.text = outcome.code
        elif outcome.ran:
            console.write(console.paint("  Tests still failing:", "yellow", bold=True))
            for line in outcome.output.splitlines()[-12:]:
                console.write("    " + console.paint(line, "grey"))
            result.text = outcome.code
        result.notes.extend(outcome.notes)


def _handle_fix(
    args: argparse.Namespace,
    results: list[ScanResult],
    config: Config,
    console: Console,
) -> int:
    all_findings: list[Finding] = []
    for r in results:
        all_findings.extend(r.findings)

    patch = build_from_findings(all_findings)
    if not patch:
        console.write(console.paint("  No automatic fixes found to apply.", "dim"))
        return EXIT_OK

    interactive = getattr(args, "interactive", False)
    dry_run = getattr(args, "dry_run", False)
    diff_only = getattr(args, "diff", False)
    backup = not getattr(args, "no_backup", False)

    if diff_only:
        diff_text = patch.diff()
        if diff_text:
            print(diff_text)
        return EXIT_OK

    if dry_run:
        console.write(console.paint(f"  Found {len(patch)} changes in{len(patch.files())} files (dry-run):", "cyan"))
        for edit in patch.edits:
            console.write(f"    {edit.file}:{edit.line} [{edit.rule}] {edit.description}")
        return EXIT_OK

    if interactive:
        changed = patch.apply_interactive(backup=backup, color=config.color)
    else:
        changed = patch.apply(backup=backup)

    if changed:
        console.write(
            console.paint(
                f"  Successfully applied fixes in{len(changed)} files: {', '.join(map(os.path.basename, changed))}",
                "green",
            )
        )
    return EXIT_OK


def cmd_fix(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    paths = _resolve_paths(args)
    if not paths:
        paths = ["."]

    # Run all checks with auto fixes
    results: list[ScanResult] = []
    for code in ("SFB", "SEC", "OPT", "MOD"):
        if code in SHORTCUTS:
            results.extend(_run_shortcut_over(code, paths, args, config))

    return _handle_fix(args, results, config, get_console(config.color))


def cmd_scan(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    console = get_console(config.color)
    paths = _resolve_paths(args)
    if not paths:
        paths = ["."]

    results: list[ScanResult] = []
    seen: set[str] = set()

    for path in paths:
        if not os.path.isfile(path):
            continue
        directives = scan_directives(path)
        for directive in directives:
            key = f"{path}:{directive.line}:{directive.code}"
            if key in seen:
                continue
            seen.add(key)
            res = run_shortcut(
                directive.code,
                path,
                pro=directive.pro,
                question=directive.question,
                config=config,
            )
            results.append(res)

    if not results:
        console.write(console.paint("  No / directives found in code.", "dim"))
        return EXIT_OK

    return _emit(args, results)


def cmd_dev(args: argparse.Namespace) -> int:
    from .patcher import build_from_scan
    from .watcher import Change, watch

    config = _apply_common(args)
    console = get_console(config.color)
    paths = _resolve_paths(args) or ["."]
    auto_fix = getattr(args, "auto_fix", False) or getattr(args, "fix", False)

    mode_str = "Auto-Healing Active" if auto_fix else "Diagnostic Mode"
    console.write(console.paint(f"\n  👀 SBpy Dev Watcher ({mode_str}) on {', '.join(paths)} (Ctrl+C to stop)...", "cyan", bold=True))

    def on_change(change: Change) -> None:
        touched = change.touched()
        for path in touched:
            if not path.endswith(".py") or not os.path.isfile(path):
                continue
            console.write(console.paint(f"\n  [File Changed] {os.path.basename(path)}", "yellow", bold=True))
            res = run_shortcut("SFB", path, config=config)
            render_scan(res, config=config, console=console, root=os.getcwd())

            if auto_fix and res.findings:
                try:
                    patch = build_from_scan(res)
                    if patch and patch.edits:
                        changed = patch.apply(backup=True)
                        if changed:
                            console.write(console.paint(f"  ✨ Auto-healed: Applied {len(patch.edits)} safe fix(es) to {os.path.basename(path)}", "green", bold=True))
                except Exception as exc:
                    console.write(console.paint(f"  ! Auto-heal skipped: {exc}", "grey"))

    try:
        watch(paths, on_change)
        return EXIT_OK
    except KeyboardInterrupt:
        return EXIT_OK


def cmd_explain(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    text = args.text
    code = ""
    if getattr(args, "file", None) and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8", errors="replace") as handle:
            code = handle.read()

    report = diagnose_text(text, code=code, config=config)
    render_report(report, config=config)
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    console = get_console(config.color)
    engine = get_engine(config)
    gem_status = engine.status()

    console.write(console.paint(f"\n  SBpy v{__version__} Doctor", "bold"))
    console.write(f"  Python:     {sys.version.split()[0]} ({sys.executable})")
    console.write(f"  Language:   {config.language}")
    console.write(f"  Offline:    {'Yes' if config.offline else 'No'}")
    console.write(f"  Backend:    {config.backend}")
    console.write(f"  SDK:        {'Available' if sdk_available() else 'Missing (google-genai)'}")
    console.write(f"  API Key:    {'Configured' if config.active_api_key else 'Missing'}")
    console.write(f"  Gemini OK:  {'Yes' if gem_status.get('connected') else 'No'}")
    console.write(f"  Home dir:   {config.home}")
    console.write(f"  Cache dir:  {config.cache_dir}")
    console.write(f"  Usage file: {config.usage_file}")
    try:
        from .updater import check_for_updates
        update_info = check_for_updates(config=config, timeout=2.0)
        if update_info.get("update_available"):
            console.write(console.paint(f"  Update:     v{update_info.get('latest_version')} available! (run: sbpy update)", "yellow", bold=True))
        else:
            console.write(f"  Update:     Up to date (v{__version__})")
    except Exception:  # sbpy: ignore=silent-except
        pass
    console.write("")
    return EXIT_OK


def cmd_usage(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    console = get_console(config.color)
    data = budget.summary(config)

    console.write(console.paint("\n  SBpy Budget and Token Usage", "bold"))
    console.write(f"  Total calls:   {data.get('calls_total', 0)}")
    console.write(f"  Total tokens:   {data.get('tokens_total', 0):,}")
    console.write(f"  Cache hits: {data.get('cached_hits', 0)}")
    console.write(f"  Budget blocked:  {data.get('blocked_calls', 0)}\n")
    return EXIT_OK


def cmd_cache(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    console = get_console(config.color)
    cache = Cache(config)

    if getattr(args, "clear", False):
        cache.clear()
        console.write(console.paint("  Cache cleared successfully.", "green"))
        return EXIT_OK

    stats = cache.stats()
    console.write(console.paint(f"  Cache: {stats.get('entries', 0)} entries ({stats.get('size_bytes', 0)} bytes)", "cyan"))
    return EXIT_OK


def cmd_index(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    console = get_console(config.color)
    target_path = getattr(args, "path", ".") or "."

    if getattr(args, "rebuild", False):
        build_index(target_path, use_cache=False, config=config)
        console.write(console.paint("  Project index rebuilt successfully.", "green"))
    else:
        build_index(target_path, config=config)

    st = index_stats(target_path, config=config)
    console.write(console.paint(f"  Project index: {st.get('files', 0)} files, {st.get('names', 0)} symbols", "cyan"))
    return EXIT_OK


def cmd_learn(args: argparse.Namespace) -> int:
    config = _apply_common(args)
    console = get_console(config.color)

    if getattr(args, "clear", False):
        learn.clear(config=config)
        console.write(console.paint("  Learned rules cleared successfully.", "green"))
        return EXIT_OK

    stats = learn.stats(config=config)
    console.write(console.paint(f"  Rules learned from Gemini: {stats.get('rules_count', 0)}", "cyan"))
    return EXIT_OK


def cmd_shortcuts(args: argparse.Namespace) -> int:
    from .shortcuts import SHORTCUTS, markdown_table

    config = _apply_common(args)
    console = get_console(config.color)
    code = getattr(args, "code", None)

    if getattr(args, "md", False):
        # The README embeds this table; generating it keeps docs from drifting.
        print(markdown_table(config.language))
        return EXIT_OK

    if code:
        code = code.strip().lstrip("/@").upper()
        if code not in SHORTCUTS:
            console.write(console.paint(f"  Unknown shortcut: /{code}", "red"))
            return EXIT_BAD_ARGS
        
        sc = SHORTCUTS[code]
        desc = sc.title_he if config.language == "he" else sc.title_en
        console.write(console.paint(f"\n  /{sc.code} - {desc}", "cyan", bold=True))
        console.write(f"  Focus:       {sc.focus}")
        console.write(f"  Tier:        {sc.tier} model")
        console.write(f"  Escalation:  {sc.escalate}")
        console.write(f"  Categories:  {', '.join(sc.categories)}")
        if sc.takes_question:
            console.write(f"  Usage:       /{sc.code} [optional context]")
        else:
            console.write(f"  Usage:       /{sc.code}")
        console.write("")
        return EXIT_OK

    console.write(console.paint("\n  Available shortcuts in SBpy:\n", "bold"))
    for sc_code, title, escalate in list_shortcuts(config.language):
        console.write(f"  /{sc_code:<6} {title}")
    console.write(console.paint("\n  Run `sbpy shortcuts <CODE>` for details on a specific shortcut, or `sbpy fullinfo` for full categorized directory.", "grey"))
    console.write("")
    return EXIT_OK


def cmd_fullinfo(args: argparse.Namespace) -> int:
    from .fullinfo import render_full_info

    config = _apply_common(args)
    console = get_console(config.color)
    render_full_info(console=console, config=config)
    return EXIT_OK


def cmd_lsp(args: argparse.Namespace) -> int:
    from .lsp import start_lsp_server

    start_lsp_server()
    return EXIT_OK


def cmd_dead(args: argparse.Namespace) -> int:
    from .graph import find_dead_code

    config = _apply_common(args)
    console = get_console(config.color)
    target = getattr(args, "path", ".") or "."
    findings = find_dead_code(target)

    if not findings:
        console.write(console.paint("  No dead code found in project! All settings in use.", "green"))
        return EXIT_OK

    console.write(console.paint(f"\n  Found {len(findings)} unused symbols:\n", "yellow", bold=True))
    for f in findings:
        console.write(f"  {console.paint(f.file + ':' + str(f.line), 'cyan')} {f.message}")
        if f.hint:
            console.write(f"    {console.paint('→ ' + f.hint, 'grey')}")
    console.write("")
    return EXIT_FINDINGS


def cmd_report(args: argparse.Namespace) -> int:
    from .batch import scan_paths
    from .report import generate_html_report

    config = _apply_common(args)
    console = get_console(config.color)
    target = getattr(args, "path", ".") or "."

    results = scan_paths([target], categories=None, config=config)
    html_out = getattr(args, "html", "") or "sbpy_report.html"
    out_file = generate_html_report(results, project_root=target, output_path=html_out)
    console.write(console.paint(f"\n  Interactive HTML report created successfully:\n  {out_file}\n", "green", bold=True))
    return EXIT_OK


def cmd_trace(args: argparse.Namespace) -> int:
    from .trace import run_with_trace

    config = _apply_common(args)
    console = get_console(config.color)
    script = getattr(args, "script", "")
    if not script or not os.path.exists(script):
        console.write(console.paint(f"  File does not exist: {script}", "red"))
        return EXIT_ERROR

    code, snapshot = run_with_trace(script, getattr(args, "script_args", []))
    if snapshot is not None:
        console.write(console.paint(f"\n  Crash detected: {snapshot.exc_type}: {snapshot.exc_value}\n", "red", bold=True))
        console.write(console.paint("  Recent operations timeline (Time-Travel):", "yellow", bold=True))
        for step in snapshot.timeline:
            loc = f"{os.path.basename(step.file)}:{step.line}"
            console.write(f"  [{console.paint(loc, 'cyan')}] {step.code}")
            if step.locals:
                vars_str = ", ".join(f"{k}={v}" for k, v in list(step.locals.items())[:4])
                console.write(f"    {console.paint('Variables: ' + vars_str, 'grey')}")

        dump_path = getattr(args, "dump", "") or "crash_dump.json"
        saved = snapshot.save_json(dump_path)
        console.write(console.paint(f"\n  Snapshot saved to: {saved}\n", "green"))

        if getattr(args, "ui", False):
            from .ui_server import start_dashboard_server

            start_dashboard_server(open_browser=True, console=console)
        return EXIT_ERROR

    return code


def cmd_migrate(args: argparse.Namespace) -> int:
    from .migrate import run_migration

    config = _apply_common(args)
    console = get_console(config.color)
    file_path = getattr(args, "file", "")
    target = getattr(args, "target", "pytest")
    dry_run = getattr(args, "dry_run", False)

    if not file_path or not os.path.exists(file_path):
        console.write(console.paint(f"  File does not exist: {file_path}", "red"))
        return EXIT_ERROR

    res = run_migration(file_path, target, dry_run=dry_run)
    if not res.has_changes:
        console.write(console.paint(f"  No migration changes required for {file_path}.", "green"))
        return EXIT_OK

    console.write(console.paint(f"\n  Completed migration to{target} for {file_path} ({len(res.changes)} changes):\n", "green", bold=True))
    for c in res.changes:
        console.write(f"  • {c}")
    console.write("")
    return EXIT_OK


def cmd_infer(args: argparse.Namespace) -> int:
    import runpy
    from .infer import TypeCollector, generate_type_signatures

    config = _apply_common(args)
    console = get_console(config.color)
    script = getattr(args, "script", "")
    if not script or not os.path.exists(script):
        console.write(console.paint(f"  File does not exist: {script}", "red"))
        return EXIT_ERROR

    collector = TypeCollector(target_dir=os.path.dirname(os.path.abspath(script)) or ".")
    try:
        with collector:
            runpy.run_path(script, run_name="__main__")
    except Exception:  # sbpy: ignore=silent-except
        pass

    summary = collector.summary()
    sigs = generate_type_signatures(summary)
    if not sigs:
        console.write(console.paint("  No functions sampled for type inference.", "yellow"))
        return EXIT_OK

    console.write(console.paint("\n  Type Hints inferred from code execution:\n", "green", bold=True))
    for f, lines in sigs.items():
        console.write(f"  {console.paint(os.path.basename(f), 'cyan')}:")
        for l in lines:
            console.write(f"    {l}")
    console.write("")
    return EXIT_OK


def cmd_diagram(args: argparse.Namespace) -> int:
    from .diagrams import generate_class_diagram, generate_flow_diagram, save_diagram

    config = _apply_common(args)
    console = get_console(config.color)
    root = getattr(args, "path", ".") or "."
    dtype = getattr(args, "type", "class")
    out_file = getattr(args, "out", "diagram.md") or "diagram.md"

    if dtype == "flow":
        diagram = generate_flow_diagram(root)
    else:
        diagram = generate_class_diagram(root)

    saved = save_diagram(diagram, out_file)
    console.write(console.paint(f"\n  Mermaid diagram created successfully:\n  {saved}\n", "green", bold=True))
    return EXIT_OK


def cmd_ui(args: argparse.Namespace) -> int:
    from .ui_server import start_dashboard_server

    config = _apply_common(args)
    console = get_console(config.color)
    port = getattr(args, "port", 8080) or 8080
    no_browser = getattr(args, "no_browser", False)

    start_dashboard_server(port=port, open_browser=not no_browser, console=console)
    return EXIT_OK


def cmd_test_gen(args: argparse.Namespace) -> int:
    from .test_gen import generate_test_file

    config = _apply_common(args)
    console = get_console(config.color)
    path = getattr(args, "path", None)
    if not path or not os.path.exists(path):
        console.write(console.paint("  ! Please specify a valid python file to generate tests for.", "red"))
        return EXIT_ERROR

    out_file = getattr(args, "out", None)
    created = generate_test_file(path, out_file)
    console.write(console.paint(f"\n  ✓ Smart Test Suite generated successfully:\n  {created}\n", "green", bold=True))
    return EXIT_OK


def cmd_install_hook(args: argparse.Namespace) -> int:
    from .git_ops import install_git_pre_commit_hook

    config = _apply_common(args)
    console = get_console(config.color)
    path = getattr(args, "path", ".") or "."
    ok = install_git_pre_commit_hook(path, console=console)
    return EXIT_OK if ok else EXIT_ERROR


def cmd_init_ci(args: argparse.Namespace) -> int:
    from .git_ops import generate_github_ci_workflow

    config = _apply_common(args)
    console = get_console(config.color)
    path = getattr(args, "path", ".") or "."
    wf = generate_github_ci_workflow(path, console=console)
    return EXIT_OK if wf else EXIT_ERROR


def cmd_heal(args: argparse.Namespace) -> int:
    from .agent import run_self_healing_tests

    config = _apply_common(args)
    console = get_console(config.color)
    root = getattr(args, "path", ".") or "."
    cmd = getattr(args, "cmd", None)
    max_iter = getattr(args, "max_iterations", 3)
    res = run_self_healing_tests(test_cmd=cmd, max_iterations=max_iter, root_dir=root, config=config, console=console)
    return EXIT_OK if res.success else EXIT_ERROR


def cmd_agent(args: argparse.Namespace) -> int:
    from .agent import run_autonomous_agent

    config = _apply_common(args)
    console = get_console(config.color)
    goal = getattr(args, "goal", "")
    root = getattr(args, "path", ".") or "."
    max_steps = getattr(args, "max_steps", 5)
    if not goal:
        console.write(console.paint("  ! Please specify a goal for the autonomous agent.", "red"))
        return EXIT_ERROR
    res = run_autonomous_agent(goal=goal, root_dir=root, max_steps=max_steps, config=config, console=console)
    return EXIT_OK if res.success else EXIT_ERROR


def cmd_find(args: argparse.Namespace) -> int:
    from .search import render_search_results, semantic_code_search

    config = _apply_common(args)
    console = get_console(config.color)
    query = getattr(args, "query", "")
    root = getattr(args, "path", ".") or "."
    limit = getattr(args, "limit", 5)
    if not query:
        console.write(console.paint("  ! Please specify a search query: sbpy find \"query\"", "red"))
        return EXIT_ERROR
    results = semantic_code_search(query, root_dir=root, max_results=limit, config=config)
    render_search_results(results, query, console=console)
    return EXIT_OK


def cmd_gen(args: argparse.Namespace) -> int:
    from .scaffold import generate_scaffold

    config = _apply_common(args)
    console = get_console(config.color)
    prompt = getattr(args, "prompt", "")
    root = getattr(args, "path", ".") or "."
    dry_run = getattr(args, "dry_run", False)
    if not prompt:
        console.write(console.paint("  ! Please specify what to scaffold: sbpy gen \"fastapi app...\"", "red"))
        return EXIT_ERROR
    res = generate_scaffold(prompt, root_dir=root, apply=not dry_run, config=config, console=console)
    return EXIT_OK if (res.written_files or dry_run) else EXIT_ERROR


def cmd_config(args: argparse.Namespace) -> int:
    from .config import (
        config_file_path,
        get_config,
        load_stored_config,
        save_stored_config,
        set_config_value,
        test_ai_connection,
    )

    config = _apply_common(args)
    console = get_console(config.color)
    action = getattr(args, "action", "") or "list"

    if action in ("wizard", "interactive") or getattr(args, "interactive", False):
        return cmd_setup(args)

    if action in ("test", "check"):
        console.write(console.paint("\n  Testing AI connection...", "cyan"))
        res = test_ai_connection(config)
        if res.get("ok"):
            console.write(console.paint(f"  ✓ Connection successful! (Backend: {res.get('backend')}, Model: {res.get('model')}, Latency: {res.get('latency_ms')}ms)", "green", bold=True))
            return EXIT_OK
        else:
            console.write(console.paint(f"  ✗ Connection failed: {res.get('error')}", "red", bold=True))
            if res.get("fix"):
                console.write(console.paint(f"    Suggested fix: {res.get('fix')}", "yellow"))
            return EXIT_ERROR

    if action == "set":
        key = getattr(args, "key", "")
        value = getattr(args, "value", "")
        if not key or value is None:
            console.write(console.paint("  You must specify key and value: sbpy config set <key> <value>", "red"))
            return EXIT_ERROR
        val_parsed: Any = value
        if value.lower() in ("true", "1", "yes", "on"):
            val_parsed = True
        elif value.lower() in ("false", "0", "no", "off"):
            val_parsed = False
        else:
            try:
                val_parsed = int(value)
            except ValueError:
                try:
                    val_parsed = float(value)
                except ValueError:
                    val_parsed = value

        set_config_value(key, val_parsed)
        console.write(console.paint(f"  Setting `{key}` successfully updated to: {val_parsed}", "green", bold=True))
        return EXIT_OK

    if action in ("set-key", "key"):
        key_val = getattr(args, "key", "") or getattr(args, "value", "")
        if not key_val:
            import getpass

            key_val = getpass.getpass("Enter API Key (Gemini / OpenAI / Claude): ").strip()
        if not key_val:
            console.write(console.paint("  No key provided.", "yellow"))
            return EXIT_ERROR
        set_config_value("api_key", key_val)
        console.write(console.paint("  API key successfully saved!", "green", bold=True))
        return EXIT_OK

    if action == "get":
        key = getattr(args, "key", "")
        stored = load_stored_config()
        val = stored.get(key, getattr(config, key, None))
        console.write(f"{key} = {val}")
        return EXIT_OK

    # Default: Show config dashboard
    cfg_file = config_file_path()
    stored = load_stored_config()

    console.write(console.paint("\n  ⚙️  SBpy Configuration Dashboard", "bold"))
    console.write(f"  Config File:  {console.paint(str(cfg_file), 'cyan')}")
    console.write(f"  Language:     {config.language}")
    console.write(f"  AI Provider:  {config.backend}")

    # API key masking
    if config.active_api_key:
        masked = config.active_api_key[:6] + "..." + config.active_api_key[-4:] if len(config.active_api_key) > 10 else "***"
        console.write(f"  API Key:      {console.paint(masked, 'green')} (configured)")
    else:
        console.write(f"  API Key:      {console.paint('Not configured (set with: sbpy config set-key)', 'yellow')}")

    console.write(f"  Auto Model:   {config.model_auto}")
    console.write(f"  Cmd Model:    {config.model_command}")
    console.write(f"  Pro Model:    {config.model_pro}")
    console.write(f"  Timeout:      {config.timeout}s")
    console.write(f"  Offline Mode: {config.offline}")
    console.write(f"  Cache:        {'Enabled' if config.cache_enabled else 'Disabled'}")
    console.write(f"  Index:        {'Enabled' if config.project_index else 'Disabled'}")
    console.write(f"  Learning:     {'Enabled' if config.learning else 'Disabled'}")

    if stored:
        custom_items = [k for k in stored if k != "api_key"]
        if custom_items:
            console.write(console.paint(f"\n  Custom Stored Values ({len(custom_items)}):", "grey"))
            for k in custom_items:
                console.write(f"    {k} = {stored[k]}")

    console.write(console.paint("\n  Useful Commands:", "grey"))
    console.write(console.paint("    sbpy config set <key> <value>   - Change setting", "grey"))
    console.write(console.paint("    sbpy config set-key <api_key>   - Set API key", "grey"))
    console.write(console.paint("    sbpy config test                - Test connection", "grey"))
    console.write(console.paint("    sbpy setup                      - Interactive setup wizard\n", "grey"))
    return EXIT_OK


def cmd_setup(args: argparse.Namespace) -> int:
    """Interactive models and providers wizard."""
    import getpass
    from .config import get_config, set_config_value, test_ai_connection, load_stored_config, save_stored_config

    config = _apply_common(args)
    console = get_console(config.color)

    console.write(console.paint("\n  🚀 SBpy Models & Providers Setup\n", "green", bold=True))

    stored = load_stored_config()
    api_keys = stored.get("api_keys", {})
    if not isinstance(api_keys, dict):
        api_keys = {}
        
    old_key = stored.get("api_key")
    if old_key and "gemini" not in api_keys:
        api_keys["gemini"] = old_key

    # 1. AI Provider Selection
    console.write(console.paint("  1. Active AI Provider / Backend", "cyan", bold=True))
    console.write(f"     Current: {config.backend}")
    console.write("     [1] gemini     (Google Gemini - 2.5 Flash / Pro)")
    console.write("     [2] openai     (OpenAI - GPT-4o / GPT-4o-mini)")
    console.write("     [3] anthropic  (Anthropic Claude - 3.5 Sonnet / Haiku / 3.7)")
    console.write("     [4] groq       (Groq - Ultra-fast Llama 3.3)")
    console.write("     [5] deepseek   (DeepSeek - Chat / Reasoner)")
    console.write("     [6] ollama     (Local offline models - Llama 3.2)")
    console.write("     [7] (Keep current)")

    choice = input("     Choice (1-7) [7]: ").strip()
    backend = config.backend
    if choice == "1":
        backend = "gemini"
    elif choice == "2":
        backend = "openai"
    elif choice == "3":
        backend = "anthropic"
    elif choice == "4":
        backend = "groq"
    elif choice == "5":
        backend = "deepseek"
    elif choice == "6":
        backend = "ollama"

    if backend != config.backend:
        set_config_value("backend", backend)
        config.backend = backend
        console.write(console.paint(f"     -> Backend set to {backend}", "green"))

    # 2. API Keys Management
    console.write(console.paint("\n  2. API Keys Management", "cyan", bold=True))
    supported_providers = ["gemini", "openai", "anthropic", "groq", "deepseek"]
    for provider in supported_providers:
        status = "Configured" if api_keys.get(provider) else "Missing"
        console.write(f"     {provider.capitalize():<10} : {status}")

    # Prompt immediately if active backend key is missing
    if backend in supported_providers and not api_keys.get(backend):
        console.write(console.paint(f"\n     ! API Key for active provider ({backend}) is missing.", "yellow"))
        prov_key = getpass.getpass(f"     Enter API Key for {backend} (or press Enter to skip): ").strip()
        if prov_key:
            api_keys[backend] = prov_key
            stored["api_keys"] = api_keys
            save_stored_config(stored)
            console.write(console.paint(f"     -> Key for {backend} saved!", "green"))

    edit_keys = input("\n     Do you want to add/update another API key? (y/N): ").strip().lower()
    if edit_keys == "y":
        prov = input(f"     Enter provider name ({'/'.join(supported_providers)}): ").strip().lower()
        if prov in supported_providers:
            new_key = getpass.getpass(f"     Enter API Key for {prov} (Press Enter to cancel): ").strip()
            if new_key:
                api_keys[prov] = new_key
                stored["api_keys"] = api_keys
                save_stored_config(stored)
                console.write(console.paint(f"     -> Key for {prov} saved!", "green"))

    # 3. Default Models Configuration
    console.write(console.paint("\n  3. Default Models Configuration", "cyan", bold=True))
    console.write(f"     Auto Model       : {config.model_auto}")
    console.write(f"     Command Model    : {config.model_command}")
    console.write(f"     Pro Model        : {config.model_pro}")
    
    edit_models = input("     Do you want to change default models? (y/N): ").strip().lower()
    if edit_models == "y":
        m_auto = input(f"     Auto Model [{config.model_auto}]: ").strip()
        if m_auto: set_config_value("model_auto", m_auto)
        
        m_cmd = input(f"     Command Model [{config.model_command}]: ").strip()
        if m_cmd: set_config_value("model_command", m_cmd)
        
        m_pro = input(f"     Pro Model [{config.model_pro}]: ").strip()
        if m_pro: set_config_value("model_pro", m_pro)
        
        console.write(console.paint("     -> Models updated!", "green"))

    # 4. Custom Shortcuts & Aliases Management
    console.write(console.paint("\n  4. Custom Shortcuts & Aliases", "cyan", bold=True))
    custom_sc = stored.get("custom_shortcuts", {})
    if not isinstance(custom_sc, dict):
        custom_sc = {}

    if custom_sc:
        for name, target in custom_sc.items():
            console.write(f"     /{name:<8} -> {target}")
    else:
        console.write("     No custom shortcuts configured yet.")

    edit_sc = input("     Do you want to add/edit a custom shortcut? (y/N): ").strip().lower()
    if edit_sc == "y":
        sc_name = input("     Enter shortcut name (e.g. audit, fast, secfix): ").strip().lstrip("/")
        if sc_name:
            sc_target = input(f"     Enter target command for /{sc_name} (e.g. SFB +, SEC --fix): ").strip()
            if sc_target:
                custom_sc[sc_name.lower()] = sc_target
                stored["custom_shortcuts"] = custom_sc
                save_stored_config(stored)
                console.write(console.paint(f"     -> Shortcut /{sc_name} -> {sc_target} saved!", "green"))

    # 5. Interactive Slash Menu Popup Toggle
    console.write(console.paint("\n  5. Interactive Slash Menu Popup", "cyan", bold=True))
    current_menu = stored.get("slash_menu", True)
    console.write(f"     Slash Popup on '/' alone: {'Enabled' if current_menu else 'Disabled'}")
    toggle_menu = input("     Enable popup on typing '/' alone? [Y/n]: ").strip().lower()
    if toggle_menu in ("n", "no", "false"):
        set_config_value("slash_menu", False)
        console.write(console.paint("     -> Popup on '/' alone disabled (use '/?' to view commands).", "yellow"))
    elif toggle_menu in ("y", "yes", "true"):
        set_config_value("slash_menu", True)
        console.write(console.paint("     -> Popup enabled.", "green"))

    # 6. Custom AI Instructions & Guidelines
    console.write(console.paint("\n  6. Custom AI Instructions & Guidelines", "cyan", bold=True))
    current_inst = stored.get("custom_instructions", "")
    if current_inst:
        preview = current_inst.replace("\n", " ")[:60]
        console.write(f"     Current: \"{preview}...\"")
    else:
        console.write("     Current: None (Standard AI guidelines)")

    edit_inst = input("     Do you want to set/edit custom AI instructions? (y/N): ").strip().lower()
    if edit_inst == "y":
        console.write("     Enter custom instructions (e.g. 'Always use type hints, follow PEP 8, avoid recursion'):")
        new_inst = input("     > ").strip()
        set_config_value("custom_instructions", new_inst)
        stored["custom_instructions"] = new_inst
        console.write(console.paint("     -> Custom AI instructions saved!", "green"))

    # 7. Connection Test
    console.write(console.paint("\n  7. Testing Connection", "cyan", bold=True))
    try:
        from .config import reset_config
        config = reset_config()
        res = test_ai_connection(config)
        if res.get("ok"):
            console.write(console.paint(f"  ✓ Connection successful! ({res.get('model')}, {res.get('latency_ms')}ms)", "green", bold=True))
        else:
            console.write(console.paint(f"  ! Warning: {res.get('error')}", "yellow"))
    except Exception as e:
        console.write(console.paint(f"  ! Error during connection test: {e}", "red"))

    try:
        from .terminal_alias import install_terminal_aliases
        install_terminal_aliases()
    except Exception:  # sbpy: ignore=silent-except
        pass

    console.write(console.paint("\n  ✨ Setup Complete! Configuration saved in ~/.sbpy/config.json\n", "green", bold=True))
    return EXIT_OK


def cmd_install_global(args: argparse.Namespace) -> int:
    """Installs global wrappers and aliases for דנפט and טפנד across the system."""
    console = get_console(False if args.no_color else None)
    from .terminal_alias import install_terminal_aliases

    console.write(console.paint("\n  ⌨️ Installing SBpy Global Terminal Aliases...", "cyan", bold=True))
    created = install_terminal_aliases()
    for item in created:
        console.write(f"  ✓ {item}")
    console.write(console.paint(f"\n  ✨ Installed {len(created)} wrapper scripts and PowerShell aliases!", "green", bold=True))
    console.write(console.paint("  You can now type `דנפט`, `טפנד`, or `sbpy` in any terminal.\n", "green"))
    return EXIT_OK


def cmd_check_update(args: argparse.Namespace) -> int:
    from .updater import check_for_updates
    config = _apply_common(args)
    console = get_console(config.color)
    console.write(console.paint("\n  🔍 Checking GitHub for SBpy updates...", "cyan"))
    info = check_for_updates(config=config, force=True, timeout=5.0)
    if info.get("update_available"):
        latest = info.get("latest_version")
        curr = info.get("current_version")
        cmd = info.get("install_cmd")
        console.write(console.paint(f"\n  🔔 New version available: v{curr} -> v{latest}!", "yellow", bold=True))
        console.write(f"  To update, run:\n    {cmd}\n")
        if getattr(args, "install", False):
            console.write(console.paint(f"  Running: {cmd} ...\n", "cyan"))
            import subprocess
            code = subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade", f"git+https://github.com/{info.get('repo')}"])
            return code
    else:
        if info.get("status") == "network_unavailable":
            console.write(console.paint("  ! Could not reach GitHub to check updates (offline or network error).\n", "yellow"))
        else:
            console.write(console.paint(f"  ✓ SBpy is up to date (v{__version__}).\n", "green", bold=True))
    return EXIT_OK


# ======================================================================
# Parser
# ======================================================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sbpy",
        description="SBpy: Gemini inside Python — but only when really needed",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--offline", action="store_true", help="Run completely offline")
    common.add_argument("--lang", choices=["he", "en"], help="Interface language (en/he)")
    common.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    common.add_argument("--no-cache", action="store_true", help="Bypass local cache")
    common.add_argument("--model", help="Custom AI model")
    common.add_argument("--backend", choices=["gemini", "ollama"], help="AI provider (gemini/ollama)")

    scanning = argparse.ArgumentParser(add_help=False)
    scanning.add_argument("paths", nargs="*", default=["."], help="Files or directories to scan")
    scanning.add_argument("--changed", action="store_true", help="Scan only files changed in git")
    scanning.add_argument("--pro", action="store_true", help="Use pro model")
    scanning.add_argument("--deep", action="store_true", help="Force AI escalation")
    scanning.add_argument("--fix", action="store_true", help="Apply auto-fixes immediately")
    scanning.add_argument("-i", "--interactive", action="store_true", help="Interactive fix mode")
    scanning.add_argument("--dry-run", action="store_true", help="Show fixes without writing to file")
    scanning.add_argument("--diff", action="store_true", help="Show unified diff of fixes")
    scanning.add_argument("--no-backup", action="store_true", help="Do not create .sbpy.bak backups")
    scanning.add_argument("--format", choices=list(FORMATS.keys()), help="Output format")
    scanning.add_argument("--json", action="store_true", help="JSON output")
    scanning.add_argument(
        "--profile",
        choices=["quiet", "normal", "strict"],
        help="How much to report: quiet=errors only, normal=warnings up, strict=all",
    )
    scanning.add_argument("--sarif", action="store_true", help="SARIF output for GitHub Security")
    scanning.add_argument("--github", action="store_true", help="GitHub Actions annotations output")
    scanning.add_argument("--fail-on", choices=["info", "warn", "error", "critical"], default="error", help="Severity level to fail on")

    subparsers = parser.add_subparsers(dest="command", help="Additional commands")

    # shell
    shell_parser = subparsers.add_parser("shell", parents=[common], help="Start interactive REPL")
    shell_parser.add_argument("--short", action="store_true", help="Short startup banner")
    shell_parser.add_argument("--force", action="store_true", help="Force execution")

    # run
    run_parser = subparsers.add_parser("run", parents=[common], help="Run script with active diagnostics")
    run_parser.add_argument("script", help="Path to script to run")
    run_parser.add_argument("script_args", nargs=argparse.REMAINDER, help="Arguments for the script")

    # fix
    subparsers.add_parser("fix", parents=[common, scanning], help="Apply automatic fixes")

    # scan
    subparsers.add_parser("scan", parents=[common, scanning], help="Scan for / directives in code")

    # dev
    dev_parser = subparsers.add_parser("dev", parents=[common], help="Run watcher on Python files")
    dev_parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to watch")
    dev_parser.add_argument("--auto-fix", "-f", action="store_true", help="Automatically heal and fix detected bugs on save")

    # explain
    explain_parser = subparsers.add_parser("explain", parents=[common], help="Diagnose pasted error message")
    explain_parser.add_argument("text", help="Error text or traceback")
    explain_parser.add_argument("--file", help="Source file relevant to context")

    # doctor
    subparsers.add_parser("doctor", parents=[common], help="Health check and connections")

    # usage
    subparsers.add_parser("usage", parents=[common], help="Budget and token usage report")

    # cache
    cache_parser = subparsers.add_parser("cache", parents=[common], help="Cache management")
    cache_parser.add_argument("--clear", action="store_true", help="Clear cache")

    # index
    index_parser = subparsers.add_parser("index", parents=[common], help="Project index")
    index_parser.add_argument("--rebuild", action="store_true", help="Rebuild index")
    index_parser.add_argument("path", nargs="?", default=".", help="Project path")

    # learn
    learn_parser = subparsers.add_parser("learn", parents=[common], help="Rules learned from Gemini")
    learn_parser.add_argument("--clear", action="store_true", help="Clear learned rules")

    # shortcuts
    shortcuts_parser = subparsers.add_parser("shortcuts", parents=[common], help="List shortcuts")
    shortcuts_parser.add_argument("code", nargs="?", help="Specific shortcut code for detailed info")
    shortcuts_parser.add_argument(
        "--md", action="store_true", help="Emit the shortcut table as markdown for the README"
    )

    # fullinfo
    subparsers.add_parser("fullinfo", parents=[common], help="Full categorized command directory & reference guide")
    subparsers.add_parser("info", parents=[common], help="Full categorized command directory")

    # lsp
    subparsers.add_parser("lsp", parents=[common], help="Start Language Server Protocol (LSP) server")

    # report
    report_parser = subparsers.add_parser("report", parents=[common], help="Generate project health report")
    report_parser.add_argument("--html", help="Path to output HTML report", default="sbpy_report.html")
    report_parser.add_argument("path", nargs="?", default=".", help="Project path to scan")

    # trace
    trace_parser = subparsers.add_parser("trace", parents=[common], help="Run script with step tracing and Crash Snapshot")
    trace_parser.add_argument("script", help="Path to script to run")
    trace_parser.add_argument("--dump", help="Path to save JSON crash dump", default="crash_dump.json")
    trace_parser.add_argument("--ui", action="store_true", help="Launch visual Time-Travel dashboard in browser")
    trace_parser.add_argument("script_args", nargs=argparse.REMAINDER, help="Arguments for the script")

    # heal
    heal_parser = subparsers.add_parser("heal", parents=[common], help="Autonomous self-healing test runner")
    heal_parser.add_argument("path", nargs="?", default=".", help="Project or test root directory")
    heal_parser.add_argument("--cmd", help="Custom test command (e.g. 'pytest tests/test_api.py')")
    heal_parser.add_argument("--max-iterations", "-n", type=int, default=3, help="Max healing iterations")

    # agent
    agent_parser = subparsers.add_parser("agent", parents=[common], help="Autonomous goal-oriented developer agent")
    agent_parser.add_argument("goal", help="Natural language programming goal")
    agent_parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    agent_parser.add_argument("--max-steps", type=int, default=5, help="Max autonomous planning steps")

    # find
    find_parser = subparsers.add_parser("find", parents=[common], help="Semantic code search")
    find_parser.add_argument("query", help="Natural language search query")
    find_parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    find_parser.add_argument("--limit", "-l", type=int, default=5, help="Max results to return")

    # gen
    gen_parser = subparsers.add_parser("gen", parents=[common], help="Natural language code & project scaffolder")
    gen_parser.add_argument("prompt", help="Description of what architecture or component to build")
    gen_parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    gen_parser.add_argument("--dry-run", action="store_true", help="Preview generated files without writing")

    # migrate
    migrate_parser = subparsers.add_parser("migrate", parents=[common], help="Automatic library and syntax migration")
    migrate_parser.add_argument("file", help="Path to file to migrate")
    migrate_parser.add_argument("--target", choices=["pytest", "httpx", "pydantic"], default="pytest", help="Migration target")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing to file")

    # infer
    infer_parser = subparsers.add_parser("infer", parents=[common], help="Infer Type Hints from script or tests execution")
    infer_parser.add_argument("script", help="Path to script to run")

    # diagram
    diagram_parser = subparsers.add_parser("diagram", parents=[common], help="Generate Mermaid diagram of project")
    diagram_parser.add_argument("path", nargs="?", default=".", help="Project path to scan")
    diagram_parser.add_argument("--type", choices=["class", "flow"], default="class", help="Diagram type")
    diagram_parser.add_argument("--out", default="diagram.md", help="Output file path")

    # config
    config_parser = subparsers.add_parser("config", parents=[common], help="Manage configuration and API keys")
    config_parser.add_argument("action", nargs="?", choices=["list", "set", "get", "set-key", "key", "test", "check", "wizard"], default="list", help="Action to perform")
    config_parser.add_argument("key", nargs="?", default="", help="Config key or API key")
    config_parser.add_argument("value", nargs="?", default=None, help="New value for config")
    config_parser.add_argument("-i", "--interactive", action="store_true", help="Setup wizard mode")

    # setup
    subparsers.add_parser("setup", parents=[common], help="Interactive setup wizard")

    # ui
    ui_parser = subparsers.add_parser("ui", parents=[common], help="Launch local web UI dashboard")
    ui_parser.add_argument("--port", type=int, default=8080, help="Port to bind server (default 8080)")
    ui_parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    # test-gen
    test_gen_parser = subparsers.add_parser("test-gen", parents=[common], help="Generate unit test suite for a file")
    test_gen_parser.add_argument("path", help="Source Python file")
    test_gen_parser.add_argument("--out", "-o", help="Output test file path")

    # install-hook
    hook_parser = subparsers.add_parser("install-hook", parents=[common], help="Install git pre-commit hook")
    hook_parser.add_argument("path", nargs="?", default=".", help="Repository root directory")

    # init-ci
    ci_parser = subparsers.add_parser("init-ci", parents=[common], help="Generate GitHub Actions CI workflow")
    ci_parser.add_argument("path", nargs="?", default=".", help="Repository root directory")

    # install-global
    subparsers.add_parser("install-global", parents=[common], help="Install terminal aliases for דנפט and טפנד across the system")

    # check-update and update
    check_up_p = subparsers.add_parser("check-update", parents=[common], help="Check GitHub for SBpy updates")
    check_up_p.add_argument("--force", action="store_true", help="Bypass cache and force check")

    update_p = subparsers.add_parser("update", parents=[common], help="Check and install SBpy update from GitHub")
    update_p.add_argument("--force", action="store_true", help="Force update even if already on latest")

    # Register all shortcuts as direct commands: sbpy sfb, sbpy sec, sbpy opt...
    for code, sc in SHORTCUTS.items():
        cmd_name = code.lower()
        sub = subparsers.add_parser(
            cmd_name,
            parents=[common, scanning],
            help=sc.title_en,
        )
        if sc.takes_question:
            sub.add_argument("question", nargs="?", default="", help="Free question")
        if code == "TST":
            sub.add_argument(
                "--verify",
                action="store_true",
                help="Run the generated tests with pytest and repair them once if they fail",
            )
            sub.add_argument("--out", default="", help="Write the generated tests to this file")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw = sys.argv[1:] if argv is None else list(argv)

    if raw:
        from .keyboard import normalize_input_command

        raw = [normalize_input_command(arg).lstrip("/") for arg in raw]

    pro_requested = False
    if PRO_TOKEN in raw:
        pro_requested = True
        raw = [arg for arg in raw if arg != PRO_TOKEN]

    if not raw:
        if _is_interactive():
            return cmd_shell(argparse.Namespace(offline=False, lang=None, no_color=False, no_cache=False, model=None, short=False))
        parser.print_help()
        return EXIT_OK

    args = parser.parse_args(raw)
    if pro_requested:
        args.pro = True

    if not args.command:
        parser.print_help()
        return EXIT_OK

    cmd = args.command.lower()
    if cmd == "shell":
        return cmd_shell(args)
    if cmd == "run":
        return cmd_run(args)
    if cmd == "fix":
        return cmd_fix(args)
    if cmd == "scan":
        return cmd_scan(args)
    if cmd == "dev":
        return cmd_dev(args)
    if cmd == "explain":
        return cmd_explain(args)
    if cmd == "doctor":
        return cmd_doctor(args)
    if cmd == "usage":
        return cmd_usage(args)
    if cmd == "cache":
        return cmd_cache(args)
    if cmd == "index":
        return cmd_index(args)
    if cmd == "learn":
        return cmd_learn(args)
    if cmd == "shortcuts":
        return cmd_shortcuts(args)
    if cmd in ("fullinfo", "info"):
        return cmd_fullinfo(args)
    if cmd == "lsp":
        return cmd_lsp(args)
    if cmd == "dead":
        return cmd_dead(args)
    if cmd == "report":
        return cmd_report(args)
    if cmd == "trace":
        return cmd_trace(args)
    if cmd == "migrate":
        return cmd_migrate(args)
    if cmd == "infer":
        return cmd_infer(args)
    if cmd == "diagram":
        return cmd_diagram(args)
    if cmd == "config":
        return cmd_config(args)
    if cmd == "setup":
        return cmd_setup(args)
    if cmd == "ui":
        return cmd_ui(args)
    if cmd in ("test-gen", "testgen"):
        return cmd_test_gen(args)
    if cmd in ("install-hook", "installhook", "hook"):
        return cmd_install_hook(args)
    if cmd in ("init-ci", "initci", "ci"):
        return cmd_init_ci(args)
    if cmd in ("install-global", "installglobal"):
        return cmd_install_global(args)
    if cmd in ("check-update", "checkupdate"):
        return cmd_check_update(args)
    if cmd in ("update", "upgrade"):
        args.install = True
        return cmd_check_update(args)
    if cmd == "heal":
        return cmd_heal(args)
    if cmd == "agent":
        return cmd_agent(args)
    if cmd == "find":
        return cmd_find(args)
    if cmd in ("gen", "scaffold"):
        return cmd_gen(args)

    code = cmd.upper()
    if code in SHORTCUTS:
        return cmd_shortcut(args, code)

    parser.print_help()
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

