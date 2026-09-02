"""נקודת הכניסה של ``sbpy shell``.

בונה את מרחב השמות, מדפיס באנר, ומוסר לקונסולה של SBpy
(שהיא ה-REPL של פייתון + שורות ``@``). הקובץ הזה לא מיועד לייבוא.
"""

from __future__ import annotations

import os
import sys

import sbpy
from sbpy.console import get_console
from sbpy.shell import run_console

_console = get_console(sbpy.get_config().color)


def _p(text: str, color: str = "", bold: bool = False) -> str:
    return _console.paint(text, color, bold=bold)


# ----------------------------------------------------------------------
# הפעלת האבחון האוטומטי בתוך ה-REPL
sbpy.install()

# הזרקת כל הקיצורים כפונקציות זמינות ישירות:  SFB("app.py")
for _code, _callable in sbpy.build_callables().items():
    globals()[_code] = _callable
    globals()[_code.lower()] = _callable

# שמות נוחים נוספים
ask = sbpy.ask
configure = sbpy.configure
status = sbpy.status
explain = sbpy.explain
watch = sbpy.watch
smart = sbpy.smart
diagnose = sbpy.diagnose


def err():
    """החריגה האחרונה שקרתה כאן."""
    return sbpy.last_error()


def report():
    """הדוח האחרון של SBpy."""
    return sbpy.last_report()


def apply(index: int | None = None):
    """Executes a numbered suggestion/action from the last report or scan."""
    return sbpy.execute_option(index, globals(), _console)


opt = apply
choose = apply


def options():
    """Lists the current active suggestions."""
    opts = sbpy.get_options()
    if not opts:
        print(_p("No active suggestions.", "grey"))
        return []
    print(_p("\nActive Suggestions:", "cyan", bold=True))
    for o in opts:
        print(f"  {_p(f'[{o.index}]', 'bright_yellow', bold=True)} {o.title}")
    print()
    return opts


def undo():
    """Reverts the last applied fix or restored file from backup."""
    from sbpy.git_ops import undo_last_patch

    return undo_last_patch(_console)


def commit(message: str = ""):
    """Creates a semantic Git commit with changed files."""
    from sbpy.git_ops import git_commit_changes

    return git_commit_changes(message=message, console=_console)


def clean(text: str = "") -> str:
    """Cleans pasted code snippets from REPL prompts (>>>) and line numbers."""
    from sbpy.cleaner import clean_pasted_code

    if not text:
        print(_p("Usage: clean('''pasted code''')", "yellow"))
        return ""
    res = clean_pasted_code(text)
    print(res)
    return res


def update():
    """Checks and installs updates from GitHub."""
    from sbpy.updater import run_upgrade

    return run_upgrade(sbpy.get_config(), console=_console)


def fullinfo():
    """Prints the comprehensive categorized command directory and reference guide."""
    from sbpy.fullinfo import render_full_info

    return render_full_info(_console)


info = fullinfo


def heal(cmd: str | None = None, max_iterations: int = 3):
    """Runs autonomous self-healing test runner until tests pass."""
    from sbpy.agent import run_self_healing_tests

    return run_self_healing_tests(test_cmd=cmd, max_iterations=max_iterations, console=_console)


def agent(goal: str, max_steps: int = 5):
    """Runs autonomous developer agent for multi-step goals."""
    from sbpy.agent import run_autonomous_agent

    return run_autonomous_agent(goal=goal, max_steps=max_steps, console=_console)


def find(query: str, limit: int = 5):
    """Performs semantic code search on project functions and classes."""
    from sbpy.search import render_search_results, semantic_code_search

    res = semantic_code_search(query, max_results=limit)
    render_search_results(res, query, console=_console)
    return res


def gen(prompt: str, dry_run: bool = False):
    """Generates project components and scaffolding from natural language."""
    from sbpy.scaffold import generate_scaffold

    return generate_scaffold(prompt, apply=not dry_run, console=_console)


def ui(port: int = 8080):
    """Launches the interactive local web dashboard."""
    from sbpy.ui_server import start_dashboard_server

    return start_dashboard_server(port=port, console=_console)


def fix(apply: bool = False):
    """אבחון של Gemini על השגיאה האחרונה. ``fix(apply=True)`` גם מתקן בקובץ."""
    exception = sbpy.last_error()
    if exception is None:
        print(_p("No recent error to diagnose.", "grey"))
        return None
    result = sbpy.diagnose(exception, exception.__traceback__, force_gemini=True)
    sbpy.render_report(result)
    if apply:
        changed = sbpy.apply_report(result)
        if changed:
            print(_p(f"Fixed: {', '.join(changed)}", "green"))
        else:
            print(_p("No safe auto-fix for this error.", "grey"))
    return result


def offline(value: bool = True):
    """מכבה או מדליק את שכבת Gemini באמצע העבודה."""
    sbpy.configure(offline=bool(value))
    state = "offline - all local" if value else "online - escalation enabled"
    print(_p(f"SBpy: {state}", "yellow" if value else "green"))


def usage():
    """דוח שימוש קצר, כולל עלות מוערכת."""
    data = sbpy.budget.summary()
    print(
        _p(
            f"Calls today: {data['calls_today']} · Total tokens: {data['tokens_total']:,} · Est. cost: ~${data['cost_usd']:.4f}",
            "grey",
        )
    )


def status():
    """מציג את סטטוס התצורה והחיבור ל-Gemini."""
    config = sbpy.get_config()
    engine = sbpy.get_engine(config).status()
    print(f"Backend:     {config.backend}")
    print(f"Status:      {'Ready' if engine['available'] else engine['reason']}")
    print(f"Model:       {config.model_command} (pro: {config.model_pro})")
    print(f"Offline:     {config.offline}")
    print(f"Cache:       {config.cache_enabled}")


def run(path: str):
    """מריץ קובץ פייתון בתוך הסשן הזה, עם האבחון פעיל."""
    import runpy

    directory = os.path.dirname(os.path.abspath(path))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    return runpy.run_path(path, run_name="__main__")


def sb_help():
    """מדפיס שוב את מסך העזרה."""
    _banner(short=False)


# ----------------------------------------------------------------------
def _banner(short: bool = False) -> None:
    config = sbpy.get_config()
    engine = sbpy.get_engine(config).status()

    if engine["available"]:
        state = _p(f"{config.backend.capitalize()} Ready", "green")
    elif config.offline:
        state = _p("Offline", "yellow")
    else:
        state = _p(f"Local only ({engine['reason']})", "yellow")

    print()
    print(f"  {_p('SBpy', 'bright_cyan', bold=True)} {_p('v' + sbpy.__version__, 'grey')}   {state}")
    print(f"  {_p('Built by Smart Binary', 'cyan', bold=True)} {_p('• https://smartbinary.org', 'grey')}")
    print(f"  {_p('GitHub: https://github.com/ELISTE770/sbpy', 'grey')}")
    print(f"  {_p('python ' + sys.version.split()[0], 'grey')}")
    print()

    if short:
        print(_p("  sb_help()  for list of commands", "grey"))
        print()
        return

    print(f"  {_p('Lines starting with / go directly to AI:', 'white', bold=True)}")
    at_rows = [
        ("/ why is this function slow?", "Free-text question to AI"),
        ("/SFB app.py", "Shortcut on file · also SEC/OPT/CMP/EXP/TST/REF/etc"),
        ("/EXP my_func", "Shortcut on session object"),
        ("/SETUP", "Setup wizard: AI keys, custom instructions & aliases"),
        ("/FULLINFO", "Full categorized command directory & guide"),
        ("/UI", "Launch local web dashboard & AI chat"),
        ("/HEAL  /  /AGENT", "Autonomous self-healing tests & coding agent"),
        ("/FIND  /  /GEN", "Semantic search & natural language scaffolder"),
        ("/", "Pop up all slash commands with actions & shortcuts"),
    ]
    for command, description in at_rows:
        print(f"    {_p(command.ljust(30), 'bright_yellow')} {_p(description, 'grey')}")

    print()
    print(f"  {_p('And regular python, with helper functions:', 'white', bold=True)}")
    rows = [
        ("SFB('app.py')", "Same as shortcut, but as a function"),
        ("run('app.py')", "Run script with active diagnostics"),
        ("apply(1) / 1 / /1", "Execute numbered AI / fix suggestion"),
        ("heal()  /  agent()", "Self-healing tests and autonomous agent"),
        ("find()  /  gen()", "Semantic code search and scaffolding"),
        ("ui()", "Launch local web dashboard"),
        ("err()  /  report()", "Last error and report"),
        ("fix()  /  fix(True)", "Force AI on last error · and fix in file"),
        ("offline(True)", "Disconnect AI on the fly"),
        ("usage()  /  status()", "Cost and configuration"),
    ]
    for command, description in rows:
        print(f"    {_p(command.ljust(30), 'bright_yellow')} {_p(description, 'grey')}")

    print()
    print(
        _p(
            f"  Tiers: Auto={config.model_auto} · /={config.model_command} · +={config.model_pro}",
            "grey",
        )
    )
    print(_p("  Any exception here will be automatically diagnosed. exit() to quit.", "grey"))
    print()


if __name__ == "__main__":
    _banner(short=os.environ.get("SBPY_SHORT_BANNER") == "1")
    run_console(globals(), sbpy.get_config())
