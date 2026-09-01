"""אינטגרציה ל-Jupyter / IPython.

    %load_ext sbpy

    %sbpy status                 מצב
    %sbpy SFB app.py             קיצור דרך
    %sbpy ask why is it slow?        שאלה חופשית
    %sbpy SFB app.py +           דרגת pro

    %%sbpy
    <תא שלם שנבדק לפני ההרצה>

בנוסף, ``load_ipython_extension`` מתקין את ה-hook כך שכל שגיאה בתא
מאובחנת אוטומטית - בדיוק כמו בטרמינל.
"""

from __future__ import annotations

from typing import Any

from .config import get_config
from .shell import parse_at_line
from .shortcuts import SHORTCUTS
from .shortcuts import run as run_shortcut


def _display(text: str) -> None:
    try:
        from IPython.display import Markdown, display  # type: ignore

        display(Markdown(text))
    except Exception:
        print(text)


def _run_line(line: str, namespace: dict[str, Any]) -> Any:
    from .render import render_scan

    line = line.strip()
    if not line:
        _print_help()
        return None

    if line.split()[0].lower() in {"status", "usage", "doctor"}:
        return _run_builtin(line.split()[0].lower())

    parsed = parse_at_line(line if line.startswith("@") else f"@{line}")
    if parsed is None:
        _print_help()
        return None

    config = get_config()
    if parsed["kind"] == "shortcut":
        argument = parsed["argument"].strip()
        target: Any = argument or None
        question = ""
        shortcut = SHORTCUTS[parsed["code"]]
        if shortcut.takes_question:
            question, target = argument, None
        elif argument and argument in namespace:
            target = namespace[argument]
        result = run_shortcut(
            parsed["code"], target, question=question, pro=parsed["pro"], config=config
        )
    else:
        result = run_shortcut(
            "ASK", None, question=parsed["question"], pro=parsed["pro"], config=config, _depth=3
        )

    render_scan(result, config=config)
    return result


def _run_builtin(name: str) -> Any:
    import json

    from . import budget, status

    if name == "status":
        data = status()
    elif name == "usage":
        data = budget.summary()
    else:
        from .gemini import get_engine

        data = get_engine().status()
    _display(f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```")
    return data


def _print_help() -> None:
    codes = " / ".join(sorted(SHORTCUTS))
    _display(
        "**SBpy**\n\n"
        "- `%sbpy /SFB app.py` — Shortcuts: " + codes + "\n"
        "- `%sbpy /ASK why is it slow?` — Free-text question\n"
        "- `+` at the end upgrades to pro model\n"
        "- `%%sbpy` at cell top — checks the cell before running\n"
        "- `%sbpy status` / `%sbpy usage`"
    )


def load_ipython_extension(ipython: Any) -> None:  # pragma: no cover
    """Called by ``%load_ext sbpy``."""
    from . import hooks

    def sbpy_line_magic(line: str) -> Any:
        return _run_line(line, ipython.user_ns)

    def sbpy_cell_magic(line: str, cell: str) -> Any:
        from .render import render_scan

        config = get_config()
        code = (line + "\n" + cell) if line.strip().startswith("#") else cell
        result = run_shortcut("SFB", code, config=config)
        render_scan(result, config=config)
        if not any(f.severity in {"error", "critical"} for f in result.findings):
            ipython.run_cell(cell)
        else:
            _display("**SBpy blocked cell execution** — found error-level findings. Run without `%%sbpy` to force.")
        return None

    ipython.register_magic_function(sbpy_line_magic, "line", "sbpy")
    ipython.register_magic_function(sbpy_cell_magic, "cell", "sbpy")
    hooks.install()
    _display("SBpy loaded. Run `%sbpy` for help.")


def unload_ipython_extension(ipython: Any) -> None:  # pragma: no cover
    from . import hooks

    hooks.uninstall()
