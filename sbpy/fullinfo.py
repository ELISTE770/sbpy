"""Full categorized command directory and detailed reference guide for SBpy."""

from __future__ import annotations

import shutil
from typing import Any

from .config import Config, get_config
from .console import get_console
from .shortcuts import SHORTCUTS

CATEGORIES = [
    {
        "title": "1. 🐞 Bug Hunting & Vulnerabilities",
        "color": "red",
        "codes": ["SFB", "SEC", "TAINT", "SQL", "DEAD"],
    },
    {
        "title": "2. ⚡ Performance & Modern Python",
        "color": "yellow",
        "codes": ["OPT", "MOD", "ASYNC", "CMP"],
    },
    {
        "title": "3. 🧹 Code Quality, Architecture & Refactoring",
        "color": "cyan",
        "codes": ["REVIEW", "CLEAN", "REF", "SOLID", "ARCH", "CLONE", "NAM"],
    },
    {
        "title": "4. 📝 Documentation, Testing & API",
        "color": "green",
        "codes": ["DOC", "TYP", "TST", "MOCK", "EXP", "DEBUG", "API", "TODO"],
    },
    {
        "title": "5. 🤖 AI Models, Settings & Free Questions",
        "color": "bright_blue",
        "special": [
            {
                "code": "ASK",
                "title": "Ask Free Question to AI",
                "focus": "Ask any programming question, algorithm design, or architecture advice",
                "usage": "/ASK What is the cleanest way to handle errors here?",
            },
            {
                "code": "MODELS",
                "title": "Manage AI Models & Multi-Provider Keys",
                "focus": "Interactive configuration for Gemini, OpenAI, Claude, Ollama, and API keys",
                "usage": "/MODELS",
            },
            {
                "code": "SETUP",
                "title": "Full Setup Wizard & Custom Preferences",
                "focus": "Configure models, custom instructions, aliases, and popup preferences",
                "usage": "/SETUP",
            },
        ],
    },
    {
        "title": "6. 🛠️ Development, Git & Live Tools",
        "color": "magenta",
        "special": [
            {
                "code": "HEAL",
                "title": "Autonomous Self-Healing Test Runner",
                "focus": "Runs pytest/unittest, detects failing test cases, and iteratively applies AI patches until green",
                "usage": "/HEAL  (or sbpy heal)",
            },
            {
                "code": "AGENT",
                "title": "Autonomous Goal-Driven Developer Agent",
                "focus": "Plans and executes multi-step refactorings, feature implementations, and test validations",
                "usage": "/AGENT \"refactor models.py to use dataclasses\"",
            },
            {
                "code": "FIND",
                "title": "Semantic Code & Architecture Search",
                "focus": "Locates code functions, classes, and logic by conceptual meaning rather than exact keywords",
                "usage": "/FIND \"where are retry policies and network errors handled?\"",
            },
            {
                "code": "GEN",
                "title": "Natural Language Code & Project Scaffolder",
                "focus": "Synthesizes complete multi-file project skeletons, routers, models, and tests from text",
                "usage": "/GEN \"fastapi crud for items with pydantic schemas\"",
            },
            {
                "code": "UNDO",
                "title": "Undo / Rollback Last Patch",
                "focus": "Instantly restores modified files to their previous backup state",
                "usage": "/UNDO  (or undo() in REPL)",
            },
            {
                "code": "COMMIT",
                "title": "Create Automated Semantic Git Commit",
                "focus": "Stages changed files and creates clean conventional commit message",
                "usage": "/COMMIT \"fix: resolve ZeroDivisionError in calc\"",
            },
            {
                "code": "UI",
                "title": "Launch Local Web Dashboard",
                "focus": "Opens browser dashboard with health score, token costs, and 1-click actions",
                "usage": "/UI",
            },
            {
                "code": "1, 2, /1",
                "title": "Execute Numbered AI Suggestions",
                "focus": "Instantly executes numbered action from error diagnoses or scans",
                "usage": "1  or  /1  or  apply(1)",
            },
        ],
    },
]


def render_full_info(console: Any = None, config: Config | None = None) -> None:
    """Renders the comprehensive categorized SBpy reference guide."""
    config = config or get_config()
    console = console or get_console(config.color)

    width = shutil.get_terminal_size((100, 24)).columns
    width = max(80, min(width, 120))
    bar = "═" * (width - 4)
    sub_bar = "─" * (width - 4)

    console.write()
    console.write(console.paint(f"  ╔{bar}╗", "cyan", bold=True))
    console.write(console.paint(f"  ║  🚀 SBpy Full Command Directory & Reference Guide{' ' * max(0, width - 53)}║", "cyan", bold=True))
    console.write(console.paint(f"  ╚{bar}╝", "cyan", bold=True))

    for cat in CATEGORIES:
        console.write()
        console.write(console.paint(f"  {cat['title']}", cat.get("color", "cyan"), bold=True))
        console.write(console.paint(f"  {sub_bar}", "grey"))

        codes = cat.get("codes", [])
        for code in codes:
            if code in SHORTCUTS:
                sc = SHORTCUTS[code]
                desc = sc.title_he if config.language == "he" else sc.title_en
                console.write(f"  {console.paint(f'/{sc.code:<8}', 'bright_yellow', bold=True)} {console.paint(desc, 'bold')}")
                if sc.focus:
                    console.write(f"            {console.paint('Focus:', 'grey')}       {sc.focus}")
                console.write(f"            {console.paint('Model Tier:', 'grey')}  {sc.tier} model ({sc.escalate} escalation)")
                if sc.takes_question:
                    console.write(f"            {console.paint('Usage:', 'grey')}       /{sc.code} <context/question>")
                else:
                    console.write(f"            {console.paint('Usage:', 'grey')}       /{sc.code} [path]  (add '+' for Pro)")
                console.write()

        for item in cat.get("special", []):
            code_label = f"/{item['code']:<8}" if not item["code"].startswith("1") else f"{item['code']:<9}"
            console.write(f"  {console.paint(code_label, 'bright_yellow', bold=True)} {console.paint(item['title'], 'bold')}")
            console.write(f"            {console.paint('Focus:', 'grey')}       {item['focus']}")
            console.write(f"            {console.paint('Usage:', 'grey')}       {item['usage']}")
            console.write()

    # Section 7: Custom Shortcuts & Aliases
    custom_sc = config.custom_shortcuts
    console.write(console.paint("  7. ⚙️ User Custom Shortcuts (Aliases)", "blue", bold=True))
    console.write(console.paint(f"  {sub_bar}", "grey"))
    if custom_sc:
        for name, target in custom_sc.items():
            console.write(f"  {console.paint(f'/{name:<8}', 'bright_yellow', bold=True)} -> {console.paint(target, 'green')}")
    else:
        console.write("  No custom shortcuts defined yet. (Add them via /SETUP or ~/.sbpy/config.json)")
    console.write()

    console.write(console.paint(f"  💡 Tip: Add '+' to any command to escalate to the high-intelligence Pro Model (e.g. `/SFB app.py +`).\n", "green"))
