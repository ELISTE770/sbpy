"""מחולל קוד וארכיטקטורה בשפה טבעית (Natural Language Scaffolding & Code Generation).

מייצר מבני פרויקטים, מודלים, מסדי נתונים, ראוטרים ובדיקות יחידה מלאות
היישר מתיאור בשפה חופשית.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .config import TIER_PRO, Config, get_config
from .console import Console, get_console
from .gemini import get_engine
from .git_ops import snapshot
from .spinner import Spinner


@dataclass
class ScaffoldResult:
    prompt: str
    files: dict[str, str] = field(default_factory=dict)
    written_files: list[str] = field(default_factory=list)
    summary: str = ""


def generate_scaffold(
    prompt: str,
    root_dir: str = ".",
    apply: bool = True,
    config: Config | None = None,
    console: Console | None = None,
) -> ScaffoldResult:
    """מייצר קבצים וקוד מלא לפי תיאור שפה טבעית."""
    config = config or get_config()
    console = console or get_console()

    console.write(console.paint(f"\n  🏗️ SBpy Architecture & Code Scaffolder", "yellow", bold=True))
    console.write(console.paint(f"  Description: \"{prompt}\"\n", "white"))

    if config.offline:
        console.write(console.paint("  ! Cannot scaffold project in offline mode.", "red"))
        return ScaffoldResult(prompt=prompt, summary="Offline mode active")

    system_prompt = """You are an expert Python Software Architect.
Given a user requirement, generate the complete file structure and implementation code.
Provide modern, clean Python 3.12+ code with type hints, docstrings, and robust error handling.

You MUST respond strictly with a JSON object where keys are relative file paths, and values are the complete file contents:
{
  "src/app/models.py": "from dataclasses import dataclass\\n...",
  "src/app/routes.py": "from fastapi import APIRouter\\n...",
  "tests/test_routes.py": "import pytest\\n..."
}
"""

    engine = get_engine(config)
    with Spinner("AI Architect synthesizing files and structure..."):
        resp = engine.generate(
            f"Build scaffolding for: {prompt}",
            system=system_prompt,
            tier=TIER_PRO,
        )

    files_dict: dict[str, str] = {}
    if resp.ok and resp.text:
        # Extract JSON
        try:
            # Clean possible markdown blocks
            clean_text = resp.text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            parsed = json.loads(clean_text.strip())
            if isinstance(parsed, dict):
                files_dict = {str(k): str(v) for k, v in parsed.items()}
        except Exception:  # sbpy: ignore=silent-except
            # Fallback regex search
            matches = re.findall(r"FILE:\s*([^\n]+)\s*```(?:python)?\s*\n(.*?)\n```", resp.text, re.DOTALL)
            for fpath, code in matches:
                files_dict[fpath.strip()] = code

    if not files_dict:
        console.write(console.paint("  ! Could not extract files from AI output.", "red"))
        return ScaffoldResult(prompt=prompt, summary="Failed to generate files")

    written: list[str] = []
    if apply:
        # Snapshot existing files
        existing = [os.path.join(root_dir, p) for p in files_dict.keys() if os.path.exists(os.path.join(root_dir, p))]
        if existing:
            snapshot(existing)

        for rel_path, content in files_dict.items():
            full_path = os.path.join(root_dir, rel_path)
            os.makedirs(os.path.dirname(os.path.abspath(full_path)), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            written.append(rel_path)
            console.write(console.paint(f"  ✓ Created/Updated: {rel_path} ({len(content.splitlines())} lines)", "green"))

        console.write(console.paint(f"\n  🎉 Successfully scaffolded {len(written)} file(s)!", "green", bold=True))

    return ScaffoldResult(
        prompt=prompt,
        files=files_dict,
        written_files=written,
        summary=f"Scaffolded {len(files_dict)} files",
    )
