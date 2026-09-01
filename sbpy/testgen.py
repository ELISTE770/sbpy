"""‎@TST שמאמת את עצמו.

מודל שכותב בדיקות הוא שימושי; מודל שכותב בדיקות **שרצות** הוא כלי.
הזרימה: מייצרים -> מריצים pytest -> אם נכשל, סבב תיקון אחד -> מריצים שוב.

סבב אחד בלבד, בכוונה: אחרי זה עדיף שהמפתח יסתכל בעצמו מאשר שנשרוף
טוקנים על ניחושים.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

from . import budget
from .config import TIER_COMMAND, TIER_PRO, Config, get_config
from .gemini import get_engine
from .prompts import SYSTEM_WRITE, _language
from .results import ScanResult

FENCE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)
PYTEST_TIMEOUT = 120


@dataclass
class VerifyOutcome:
    ran: bool = False
    passed: bool = False
    attempts: int = 0
    output: str = ""
    code: str = ""
    path: str = ""
    tokens: int = 0
    notes: list[str] = field(default_factory=list)


def extract_code(text: str) -> str:
    """מוציא את הקוד מתשובת המודל, עם או בלי גדר markdown."""
    if not text:
        return ""
    blocks = FENCE.findall(text)
    if blocks:
        return "\n\n".join(block.strip() for block in blocks)
    return text.strip()


def pytest_available() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def run_pytest(path: str, *, cwd: str) -> tuple[bool, str]:
    """מריץ pytest על קובץ אחד. מחזיר (עבר, פלט)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q", "--no-header", "-x"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PYTEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "pytest לא סיים בזמן"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"לא הצלחתי להריץ pytest: {exc}"
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output.strip()


def _tail(text: str, limit: int = 40) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


def verify(
    result: ScanResult,
    *,
    target_path: str,
    config: Config | None = None,
    pro: bool = False,
    keep: str = "",
) -> VerifyOutcome:
    """מריץ את הבדיקות שנוצרו, ומנסה סבב תיקון אחד אם הן נכשלו."""
    config = config or get_config()
    outcome = VerifyOutcome(code=extract_code(result.text))

    if not outcome.code:
        outcome.notes.append("לא התקבל קוד בדיקות")
        return outcome
    if not pytest_available():
        outcome.notes.append("pytest לא מותקן - הבדיקות נוצרו אבל לא הורצו (pip install pytest)")
        return outcome

    directory = os.path.dirname(os.path.abspath(target_path)) if target_path else os.getcwd()
    module_name = os.path.splitext(os.path.basename(target_path or "code"))[0]

    if keep:
        test_path = os.path.abspath(keep)
    else:
        handle = tempfile.NamedTemporaryFile(
            prefix=f"test_sbpy_{module_name}_", suffix=".py", dir=directory, delete=False
        )
        handle.close()
        test_path = handle.name

    try:
        for attempt in (1, 2):
            outcome.attempts = attempt
            with open(test_path, "w", encoding="utf-8", newline="\n") as file:
                file.write(outcome.code + "\n")

            outcome.ran = True
            passed, output = run_pytest(test_path, cwd=directory)
            outcome.output = output
            if passed:
                outcome.passed = True
                break
            if attempt == 2:
                outcome.notes.append("הבדיקות עדיין נכשלות אחרי סבב תיקון אחד")
                break

            repaired = _repair(outcome.code, output, target_path, config, pro)
            if repaired is None:
                outcome.notes.append("לא הצלחתי לתקן את הבדיקות")
                break
            outcome.code, extra_tokens = repaired
            outcome.tokens += extra_tokens
    finally:
        if not keep:
            outcome.path = test_path
        else:
            outcome.path = test_path

    if not keep and not outcome.passed:
        # קובץ זמני שנכשל - לא משאירים לכלוך בפרויקט
        try:
            os.unlink(test_path)
            outcome.path = ""
        except OSError:  # sbpy: ignore=silent-except
            pass

    return outcome


def _repair(
    code: str, output: str, target_path: str, config: Config, pro: bool
) -> tuple[str, int] | None:
    """סבב תיקון אחד: מוסרים למודל את פלט הכישלון."""
    allowed, _ = budget.check("@TST-verify", config)
    if not allowed:
        budget.note_blocked()
        return None

    source = ""
    if target_path and os.path.isfile(target_path):
        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as handle:
                source = handle.read()[: config.max_context_chars // 2]
        except OSError:
            source = ""

    prompt = "\n".join(
        [
            _language(config.language),
            "",
            "הבדיקות שכתבת נכשלו. תקן אותן והחזר קוד בלבד.",
            "אם הכישלון מצביע על באג אמיתי בקוד הנבדק - השאר את הבדיקה ותוסיף הערה `# BUG:`.",
            "",
            "הבדיקות:",
            "```python",
            code,
            "```",
            "",
            "פלט pytest:",
            "```",
            _tail(output),
            "```",
        ]
        + (["", "הקוד הנבדק:", "```python", source, "```"] if source else [])
    )

    response = get_engine(config).generate(
        prompt, system=SYSTEM_WRITE, tier=TIER_PRO if pro else TIER_COMMAND
    )
    budget.record(
        "@TST-verify", response.model, response.tokens, tier=response.tier,
        ok=response.ok, config=config,
    )
    if not response.ok:
        return None
    repaired = extract_code(response.text)
    if not repaired:
        return None
    return repaired, response.tokens


def describe(outcome: VerifyOutcome) -> dict[str, Any]:
    return {
        "ran": outcome.ran,
        "passed": outcome.passed,
        "attempts": outcome.attempts,
        "tokens": outcome.tokens,
        "path": outcome.path,
        "notes": outcome.notes,
    }


def extract_branches_and_boundaries(source: str) -> dict[str, Any]:
    """מחלץ את ענפי ה-AST וערכי הגבול מהקוד הנבדק לצורך בדיקות Fuzzing וכיסוי מקרי קצה."""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"functions": [], "total_branches": 0}

    functions_info: list[dict[str, Any]] = []
    total_branches = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_branches = 0
            raised: list[str] = []
            boundaries: list[Any] = []
            args = [a.arg for a in node.args.args if a.arg != "self"]

            for sub in ast.walk(node):
                if isinstance(sub, (ast.If, ast.While, ast.For)):
                    fn_branches += 1
                elif isinstance(sub, ast.Try):
                    fn_branches += len(sub.handlers) + (1 if sub.orelse else 0)
                elif isinstance(sub, ast.Raise):
                    if isinstance(sub.exc, ast.Call) and isinstance(sub.exc.func, ast.Name):
                        raised.append(sub.exc.func.id)
                    elif isinstance(sub.exc, ast.Name):
                        raised.append(sub.exc.id)
                elif isinstance(sub, ast.Constant):
                    if sub.value in (0, 1, -1, "", None, False, True):
                        boundaries.append(sub.value)

            total_branches += fn_branches
            functions_info.append(
                {
                    "name": node.name,
                    "args": args,
                    "branches": fn_branches,
                    "raises": list(set(raised)),
                    "boundaries": list(set(str(b) for b in boundaries)),
                }
            )

    return {"functions": functions_info, "total_branches": total_branches}


def build_smart_test_prompt(
    source: str,
    target_name: str = "code.py",
    *,
    hypothesis: bool = False,
    language: str = "he",
) -> str:
    """בונה הנחיית יצירת בדיקות עשירה הדורשת כיסוי מלא של ענפי AST ומקרי קצה."""
    branch_meta = extract_branches_and_boundaries(source)
    parts = [
        _language(language),
        "",
        f"כתוב בדיקות יחידה מקיפות ומקצועיות ב-pytest עבור הקובץ `{target_name}`.",
        "החזר קוד פייתון בלבד.",
        "",
    ]

    if hypothesis:
        parts.extend(
            [
                "דרישה מיוחדת: השתמש בספריית `hypothesis` (`from hypothesis import given, strategies as st`)",
                "כדי לבצע Property-Based Testing ו-Fuzzing עם קלטים שנוצרים אוטומטית.",
                "",
            ]
        )

    parts.extend(
        [
            "הנחיות קריטיות לאיכות הבדיקות:",
            "1. כסה 100% מענפי התנאים (Branch Coverage) - כולל תנאי if, elif, else ומקרי קצה.",
            "2. בדוק במפורש ערכי גבול: None, מחרוזות ריקות, רשימות ריקות, מספרים שליליים ואפס.",
            "3. עבור שגיאות וחריגות צפויות - השתמש ב-`with pytest.raises(...)`.",
            "4. שמור על בדיקות נקיות ללא mock מיותר - בדוק התנהגות אמיתית.",
            "",
            "הקוד הנבדק:",
            "```python",
            source,
            "```",
        ]
    )

    if branch_meta.get("functions"):
        parts.append("\nמיפוי ענפים ומקרי קצה שחובה לכסות:")
        for fn in branch_meta["functions"]:
            raises_str = f", זורקת {', '.join(fn['raises'])}" if fn["raises"] else ""
            parts.append(
                f"- פונקציה `{fn['name']}({', '.join(fn['args'])})`: {fn['branches']} ענפים{raises_str}."
            )

    return "\n".join(parts)

