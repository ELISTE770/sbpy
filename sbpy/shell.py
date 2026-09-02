"""ה-REPL של SBpy: פייתון רגיל, ועוד שורות שמתחילות ב-``/``.

    >>> /SFB app.py           קיצור דרך על קובץ או על אובייקט
    >>> / why is it slow?         שאלה חופשית ל-Gemini
    >>> /EXP my_func +        ה-`+` בסוף מעלה דרגה ל-pro

דרגות המודל:
    הסלמה אוטומטית (שגיאה בריצה)  ->  flash-lite   (זול, לא ביקשו אותו)
    שורת `/` או פקודת CLI          ->  flash        (ביקשו במפורש)
    `+` בסוף השורה / `--pro`       ->  pro          (סימנו במפורש)
"""

from __future__ import annotations

import ast
import code as code_module
import os
import re
import sys
from typing import Any

from .config import TIER_COMMAND, TIER_PRO, Config, get_config
from .console import get_console
from .shortcuts import SHORTCUTS
from .shortcuts import run as run_shortcut

PRO_SUFFIX = "+"


def strip_pro_marker(line: str) -> tuple[str, bool]:
    """מוריד ``+`` מסוף השורה ומחזיר (השורה, האם pro)."""
    stripped = line.rstrip()
    if stripped.endswith(PRO_SUFFIX) and not stripped.endswith("++"):
        body = stripped[: -len(PRO_SUFFIX)].rstrip()
        if body:
            return body, True
    return line, False


def looks_like_decorator(rest: str) -> bool:
    """Whether ``@rest`` is a valid Python decorator and not an SBpy directive."""
    rest = rest.strip()
    if not rest or " " in rest.split("(")[0]:
        return False
    try:
        ast.parse(f"@{rest}\ndef _sbpy_probe(): pass\n")
    except SyntaxError:
        return False
    return True


def parse_at_line(line: str) -> dict[str, Any] | None:
    """Parses a ``/`` or ``@`` line. Returns None if it should be passed to standard Python."""
    from .keyboard import normalize_input_command

    line = normalize_input_command(line)
    raw = line.strip()

    if raw.upper() in ("/UPDATE", "/UPGRADE", "UPDATE", "UPGRADE", "/עדכן", "עדכן"):
        return {"kind": "update"}
    if raw in ("++", "/++"):
        return {"kind": "ai_escalate", "tier": TIER_PRO}
    if raw in ("+", "/+", "/ai", "/ask_ai", "/ai_escalate") or raw.lower() in ("ai", "ask_ai", "שאל"):
        return {"kind": "ai_escalate", "tier": TIER_COMMAND}

    if not (raw.startswith("/") or raw.startswith("@")):
        from .keyboard import transliterate_keyboard

        head, _, rest = raw.partition(" ")
        trans_head = transliterate_keyboard(head).lower()
        rev_head = transliterate_keyboard(head[::-1]).lower()

        if trans_head == "sbpy" or rev_head == "sbpy":
            if rest.strip():
                return parse_at_line(f"/{rest.strip()}")
            return {"kind": "fullinfo"}
        if trans_head in ("models", "providers", "setup") or rev_head in ("models", "providers", "setup"):
            return {"kind": "setup"}
        if trans_head in ("fullinfo", "info", "help", "shortcuts") or rev_head in ("fullinfo", "info", "help", "shortcuts"):
            return {"kind": "fullinfo"}
        if trans_head in ("undo", "revert") or rev_head in ("undo", "revert"):
            return {"kind": "undo"}
        if trans_head == "ui" or rev_head == "ui":
            return {"kind": "ui"}
        if trans_head.upper() in SHORTCUTS or rev_head.upper() in SHORTCUTS:
            code = trans_head.upper() if trans_head.upper() in SHORTCUTS else rev_head.upper()
            return parse_at_line(f"/{code} {rest}".strip())
        return None

    prefix = raw[0]
    body, pro = strip_pro_marker(raw[1:])
    body = body.strip()
    if not body:
        if get_config().slash_menu:
            return {"kind": "menu"}
        return None

    if body.upper() in ("?", "HELP", "SHORTCUTS"):
        return {"kind": "menu"}

    if body.isdigit():
        return {"kind": "option", "index": int(body)}

    head, _, rest = body.partition(" ")
    code = head.upper().rstrip(":")
    tier = TIER_PRO if pro else TIER_COMMAND

    if code in ("MODELS", "PROVIDERS", "SETUP"):
        return {"kind": "setup"}

    if code in ("FULLINFO", "FULL_INFO", "INFO", "COMMANDS"):
        return {"kind": "fullinfo"}

    if code in ("UNDO", "REVERT"):
        return {"kind": "undo"}

    if code == "COMMIT":
        return {"kind": "commit", "argument": rest.strip()}

    if code in ("HEAL", "AUTO_HEAL"):
        return {"kind": "heal", "argument": rest.strip()}

    if code == "AGENT":
        return {"kind": "agent", "argument": rest.strip()}

    if code in ("FIND", "SEARCH"):
        return {"kind": "find", "argument": rest.strip()}

    if code in ("GEN", "SCAFFOLD"):
        return {"kind": "gen", "argument": rest.strip()}

    if code == "UI":
        return {"kind": "ui"}

    if rest.strip() in ("?", "--help", "-h", "help") and (code in SHORTCUTS or code.lower() in get_config().custom_shortcuts):
        return {"kind": "shortcut_help", "code": code}

    # Check custom shortcuts / aliases
    custom_sc = get_config().custom_shortcuts
    if code.lower() in custom_sc:
        target_template = custom_sc[code.lower()]
        template_body, template_pro = strip_pro_marker(target_template)
        expanded = f"{template_body} {rest}".strip()
        if template_pro or pro:
            expanded += " +"
        return parse_at_line(f"/{expanded}")

    if code in SHORTCUTS:
        return {"kind": "shortcut", "code": code, "argument": rest.strip(), "tier": tier, "pro": pro}

    # If it was entered with @, check if it's a real python decorator
    if prefix == "@" and looks_like_decorator(body):
        return None

    return {"kind": "ask", "question": body, "tier": tier, "pro": pro}


class SBpyConsole(code_module.InteractiveConsole):
    """קונסולה שמזהה שורות ``/`` לפני שהיא מוסרת אותן לפייתון."""

    def __init__(self, namespace: dict[str, Any] | None = None, config: Config | None = None) -> None:
        super().__init__(locals=namespace)
        self.config = config or get_config()
        self.console = get_console(self.config.color)

    # ------------------------------------------------------------------
    def push(self, line, filename=None, _symbol="single"):  # type: ignore[no-untyped-def]
        # Clean pasted code with >>> prompts or line number prefixes
        if line.lstrip().startswith((">>>", "...")) or re.match(r"^\s*(?:\d+\s*[|:]|\[\d+\])", line):
            from .cleaner import clean_pasted_code

            cleaned = clean_pasted_code(line)
            if cleaned != line:
                lines = cleaned.splitlines()
                more = 0
                for sub_line in lines:
                    more = super().push(sub_line, filename, _symbol)
                return more

        # רק בתחילת משפט. באמצע בלוק רב-שורתי `/` הוא קוד רגיל.
        if not self.buffer:
            raw = line.strip()
            if raw == "/":
                if self.config.slash_menu:
                    self.show_slash_menu()
                    return 0
            elif raw.lower() in ("/?", "/help", "/shortcuts"):
                self.show_slash_menu()
                return 0

            if raw.isdigit():
                from .suggestions import get_options

                idx = int(raw)
                if 1 <= idx <= len(get_options()):
                    self.handle_at({"kind": "option", "index": idx})
                    return 0

            if raw.lower() in ("choose", "choose()", "opt", "opt()", "apply", "apply()", "בחר", "אפשרויות"):
                self.handle_at({"kind": "option", "index": None})
                return 0

            parsed = parse_at_line(line)
            if parsed is not None:
                self.handle_at(parsed)
                return 0
        return super().push(line, filename, _symbol)

    # ------------------------------------------------------------------
    def show_slash_menu(self) -> None:
        from .keyboard import run_interactive_arrow_picker

        console = self.console
        lang = self.config.language
        custom = self.config.custom_shortcuts

        indexed_commands: list[tuple[str, str, str]] = []

        # 1. Management, Settings & Docs
        admin_cmds = [
            ("SETUP", "Interactive Setup: Keys, Instructions, Preferences" if lang != "he" else "אשף הגדרות: מפתחות, הנחיות אישיות והעדפות"),
            ("MODELS", "Manage AI Providers & API Keys" if lang != "he" else "ניהול ספקי AI ומפתחות (Gemini, OpenAI, Claude, Ollama)"),
            ("FULLINFO", "Full Categorized Command Directory & Guide" if lang != "he" else "ספריית פקודות מלאה ומחולקת לקטגוריות עם הסברים"),
        ]
        for code, desc in admin_cmds:
            idx = len(indexed_commands) + 1
            indexed_commands.append((str(idx), code, desc))

        # 2. Autonomous Agent & Live Tools
        dev_cmds = [
            ("UI", "Launch Local Web Dashboard & AI Pair Chat" if lang != "he" else "דשבורד Web וצ'אט AI עם החלת קוד בקליק בדפדפן"),
            ("HEAL", "Self-Healing Test Runner (loops until green)" if lang != "he" else "מנגנון ריפוי עצמי של טסטים עד 100% הצלחה"),
            ("AGENT", "Goal-Driven Autonomous Developer Agent" if lang != "he" else "סוכן מפתח אוטונומי לתכנון וביצוע משימות"),
            ("FIND", "Semantic Code & Architecture Search" if lang != "he" else "חיפוש קוד סמנטי בשפה חופשית לפי משמעות"),
            ("GEN", "Natural Language Project & Code Scaffolder" if lang != "he" else "מחולל פרויקטים וארכיטקטורה מאפס"),
            ("UNDO", "Rollback / Revert Last Modified File" if lang != "he" else "ביטול ושחזור קובץ ששונה מגיבוי"),
            ("COMMIT", "Create Automated Semantic Git Commit" if lang != "he" else "יצירת קומיט סמנטי אוטומטי"),
        ]
        for code, desc in dev_cmds:
            idx = len(indexed_commands) + 1
            indexed_commands.append((str(idx), code, desc))

        # 3. Code Analysis Shortcuts
        for code, sc in sorted(SHORTCUTS.items()):
            idx = len(indexed_commands) + 1
            title = sc.title_en if lang != "he" else sc.title_he
            indexed_commands.append((str(idx), code, title))

        # 4. Custom Shortcuts
        if custom:
            for name, target in sorted(custom.items()):
                idx = len(indexed_commands) + 1
                indexed_commands.append((str(idx), name.upper(), target))

        # 1. Try interactive arrow-key picker (real-time arrow navigation)
        if getattr(sys.stdin, "isatty", lambda: False)():
            try:
                picked = run_interactive_arrow_picker(indexed_commands, console=self.console)
                if picked is not None:
                    selected_code, _ = picked
                    full_cmd = f"/{selected_code}"
                    console.write(console.paint(f"\n  ▶ Selected: {full_cmd}\n", "green", bold=True))
                    parsed = parse_at_line(full_cmd)
                    if parsed:
                        self.handle_at(parsed)
                    return
                return
            except Exception:  # sbpy: ignore=silent-except
                pass

        # 2. Fallback for non-interactive / redirection environments
        console.write()
        console.write(console.paint("  ┌── 🛠️ SBpy Command Directory ──────────────────────────────────────────────┐", "cyan", bold=True))
        for idx_str, code, desc in indexed_commands:
            act_str = f"({desc})"
            if len(act_str) > 42:
                act_str = act_str[:39] + "...)"
            idx_badge = console.paint(f"[{idx_str:>2}]", "bright_yellow", bold=True)
            cmd_badge = console.paint('/' + code.ljust(8), "bright_cyan")
            desc_text = console.paint(act_str.ljust(44), "grey")
            console.write(f"  │  {idx_badge} {cmd_badge} {desc_text} │")
        console.write(console.paint("  └────────────────────────────────────────────────────────────────────────┘", "cyan", bold=True))
        console.write()

    # ------------------------------------------------------------------
    def resolve_argument(self, argument: str) -> Any:
        """הופך את מה שאחרי הקיצור לקובץ / אובייקט / None."""
        argument = argument.strip().strip("'\"")
        if not argument:
            return None
        if os.path.exists(argument):
            return argument

        namespace = self.locals if isinstance(self.locals, dict) else {}
        parts = argument.split(".")
        if not all(part.isidentifier() for part in parts):
            return argument
        if parts[0] not in namespace:
            return argument

        value = namespace[parts[0]]
        for part in parts[1:]:
            try:
                value = getattr(value, part)
            except Exception:
                return argument
        return value

    def handle_at(self, parsed: dict[str, Any]) -> None:
        from .render import render_scan

        try:
            if parsed["kind"] == "menu":
                self.show_slash_menu()
                return

            if parsed["kind"] == "shortcut_help":
                from .cli import cmd_shortcuts
                import argparse

                cmd_shortcuts(
                    argparse.Namespace(
                        code=parsed["code"],
                        lang=self.config.language,
                        offline=self.config.offline,
                        no_color=not self.config.color,
                        no_cache=not self.config.cache_enabled,
                        model=None,
                        backend=None,
                    )
                )
                return

            if parsed["kind"] == "fullinfo":
                from .fullinfo import render_full_info

                render_full_info(console=self.console, config=self.config)
                return

            if parsed["kind"] == "undo":
                from .git_ops import undo_last_patch

                undo_last_patch(console=self.console)
                return

            if parsed["kind"] == "commit":
                from .git_ops import git_commit_changes

                git_commit_changes(message=parsed.get("argument", ""), console=self.console)
                return

            if parsed["kind"] == "heal":
                from .agent import run_self_healing_tests

                run_self_healing_tests(test_cmd=parsed.get("argument") or None, config=self.config, console=self.console)
                return

            if parsed["kind"] == "agent":
                from .agent import run_autonomous_agent

                run_autonomous_agent(goal=parsed.get("argument", ""), config=self.config, console=self.console)
                return

            if parsed["kind"] == "find":
                from .search import render_search_results, semantic_code_search

                q = parsed.get("argument", "")
                res = semantic_code_search(q, config=self.config)
                render_search_results(res, q, console=self.console)
                return

            if parsed["kind"] == "gen":
                from .scaffold import generate_scaffold

                generate_scaffold(prompt=parsed.get("argument", ""), config=self.config, console=self.console)
                return

            if parsed["kind"] == "ui":
                from .ui_server import start_dashboard_server

                start_dashboard_server(console=self.console)
                return

            if parsed["kind"] == "update":
                from .updater import run_upgrade

                run_upgrade(self.config, console=self.console)
                return

            if parsed["kind"] == "ai_escalate":
                from .hooks import last_error, last_report
                from .ladder import diagnose, diagnose_text
                from .render import render_report

                tier = parsed.get("tier", TIER_COMMAND)
                label = "Pro" if tier == TIER_PRO else "Flash"
                err = last_error()
                rep = last_report()
                if err is not None:
                    self.console.write()
                    self.console.write(self.console.paint(f"  🧠 Sending full error context to AI ({label})...", "cyan", bold=True))
                    new_report = diagnose(err, force_gemini=True, tier=tier, config=self.config)
                    render_report(new_report, config=self.config, console=self.console)
                    return
                elif rep is not None:
                    self.console.write()
                    self.console.write(self.console.paint(f"  🧠 Sending full error context to AI ({label})...", "cyan", bold=True))
                    new_report = diagnose_text(f"{rep.exc_type}: {rep.exc_message}\n{rep.where}", force_gemini=True, tier=tier, config=self.config)
                    render_report(new_report, config=self.config, console=self.console)
                    return
                else:
                    self.console.write(self.console.paint("  No recent error found to send to AI.", "yellow"))
                    return

            if parsed["kind"] == "option":
                from .suggestions import execute_option

                execute_option(parsed["index"], namespace=self.locals, console=self.console)
                return

            if parsed["kind"] == "setup":
                from .cli import cmd_setup
                import argparse

                cmd_setup(
                    argparse.Namespace(
                        lang=self.config.language,
                        offline=self.config.offline,
                        no_color=not self.config.color,
                        no_cache=not self.config.cache_enabled,
                        model=None,
                        backend=None,
                    )
                )
                return

            if parsed["kind"] == "shortcut":
                target = self.resolve_argument(parsed["argument"])
                question = ""
                if SHORTCUTS[parsed["code"]].takes_question and isinstance(target, str):
                    question, target = target, None
                result = run_shortcut(
                    parsed["code"],
                    target,
                    question=question,
                    pro=parsed["pro"],
                    config=self.config,
                )
            else:
                result = run_shortcut(
                    "ASK",
                    None,
                    question=parsed["question"],
                    pro=parsed["pro"],
                    config=self.config,
                    _depth=3,
                )
            render_scan(result, config=self.config, root=os.getcwd())
        except (ValueError, FileNotFoundError, KeyError) as exc:
            self.console.write(self.console.paint(f"  {exc}", "yellow"))
        except Exception as exc:  # pragma: no cover
            self.console.write(self.console.paint(f"  Error executing command: {exc}", "red"))


def setup_readline_completer(namespace: dict[str, Any] | None = None) -> None:
    """Configures readline & pyrepl autocompletion for slash commands and custom aliases."""
    modules = []
    try:
        import readline

        modules.append(readline)
    except Exception:  # sbpy: ignore=silent-except
        pass

    try:
        import _pyrepl.readline as pyrepl_readline

        if pyrepl_readline not in modules:
            modules.append(pyrepl_readline)
    except Exception:  # sbpy: ignore=silent-except
        pass

    if not modules:
        return

    import rlcompleter

    base_completer = rlcompleter.Completer(namespace)

    def custom_complete(text: str, state: int) -> str | None:
        custom = get_config().custom_shortcuts
        all_codes = (
            list(SHORTCUTS.keys())
            + [
                "SETUP",
                "MODELS",
                "PROVIDERS",
                "FULLINFO",
                "INFO",
                "UI",
                "HEAL",
                "AGENT",
                "FIND",
                "GEN",
                "UNDO",
                "COMMIT",
                "HELP",
                "DOCTOR",
                "USAGE",
                "REPORT",
                "CONFIG",
            ]
            + [k.upper() for k in custom.keys()]
        )

        if text.startswith("/") or text.startswith("@"):
            prefix = text[0]
            query = text[1:].upper()
            matches = [f"{prefix}{code}" for code in sorted(set(all_codes)) if code.startswith(query)]
            if state < len(matches):
                return matches[state]
            return None

        # Check line buffer if text delimiter split it
        for mod in modules:
            if hasattr(mod, "get_line_buffer"):
                try:
                    buf = mod.get_line_buffer()
                    if buf.startswith("/") or buf.startswith("@"):
                        prefix = buf[0]
                        query = buf[1:].upper().strip()
                        matches = [f"{prefix}{code}" for code in sorted(set(all_codes)) if code.startswith(query)]
                        if state < len(matches):
                            return matches[state]
                        return None
                except Exception:  # sbpy: ignore=silent-except
                    pass

        return base_completer.complete(text, state)

    try:
        import _pyrepl.completing_reader as cr
        from _pyrepl.completing_reader import build_menu, prefix

        def instant_complete_do(self: Any) -> None:
            r = self.reader
            stem = r.get_stem()
            r.cmpltn_menu_choices = r.get_completions(stem)
            completions = r.cmpltn_menu_choices
            if not completions:
                r.error("no matches")
            elif len(completions) == 1:
                r.insert(completions[0][len(stem):])
            else:
                p = prefix(completions, len(stem))
                if p:
                    r.insert(p)
                r.cmpltn_menu_visible = True
                r.cmpltn_message_visible = False
                r.cmpltn_menu, r.cmpltn_menu_end = build_menu(
                    r.console, completions, r.cmpltn_menu_end,
                    r.use_brackets, r.sort_in_column)
                r.dirty = True

        cr.complete.do = instant_complete_do
    except Exception:  # sbpy: ignore=silent-except
        pass

    for mod in modules:
        try:
            mod.set_completer(custom_complete)
            mod.parse_and_bind("tab: complete")
            if hasattr(mod, "get_completer_delims") and hasattr(mod, "set_completer_delims"):
                delims = mod.get_completer_delims()
                delims = delims.replace("/", "").replace("@", "")
                mod.set_completer_delims(delims)
        except Exception:  # sbpy: ignore=silent-except
            pass


def run_console(namespace: dict[str, Any], config: Config | None = None) -> None:
    """Runs interactive console with pyrepl or fallback."""
    console = SBpyConsole(namespace, config)

    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    if interactive:
        try:
            from _pyrepl.readline import _setup as pyrepl_setup
            pyrepl_setup(namespace)
        except Exception:  # sbpy: ignore=silent-except
            pass
        setup_readline_completer(namespace)
        try:
            from _pyrepl.simple_interact import run_multiline_interactive_console

            run_multiline_interactive_console(console)
            return
        except Exception:  # sbpy: ignore=silent-except
            pass

    setup_readline_completer(namespace)
    try:
        console.interact(banner="", exitmsg="")
    except SystemExit:  # sbpy: ignore=silent-except
        pass


def main(namespace: dict[str, Any] | None = None) -> int:
    run_console(namespace if namespace is not None else {}, get_config())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
