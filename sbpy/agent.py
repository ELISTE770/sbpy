"""סוכן אוטונומי ומערכת ריפוי עצמי של בדיקות (Autonomous Agent & Self-Healing Tests).

מריץ בדיקות יחידה, מאתר כשלים אוטומטית, מייצר תיקונים ומחיל אותם בלולאה
סגורה עד שהטסטים עוברים, או מוציא לפועל משימות תכנות רב-שלביות שלמות.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

from .config import TIER_COMMAND, TIER_PRO, Config, get_config
from .console import Console, get_console
from .gemini import get_engine
from .git_ops import snapshot
from .spinner import Spinner


@dataclass
class HealResult:
    success: bool
    iterations: int
    initial_failures: list[str] = field(default_factory=list)
    fixed_files: list[str] = field(default_factory=list)
    output: str = ""
    error_summary: str = ""


@dataclass
class AgentStep:
    thought: str
    action: str
    target_file: str
    code_diff: str = ""
    observation: str = ""


@dataclass
class AgentResult:
    goal: str
    success: bool
    steps: list[AgentStep] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    summary: str = ""


def _detect_test_runner(root_dir: str = ".") -> list[str]:
    """מזהה האם הפרויקט משתמש ב-pytest או ב-unittest."""
    if os.path.exists(os.path.join(root_dir, "pytest.ini")) or os.path.exists(os.path.join(root_dir, "conftest.py")):
        return [sys.executable, "-m", "pytest"]
    # Default to pytest if available, else unittest
    try:
        import pytest  # noqa: F401  # sbpy: ignore=unused-import

        return [sys.executable, "-m", "pytest"]
    except ImportError:  # sbpy: ignore=silent-except
        return [sys.executable, "-m", "unittest", "discover"]


def run_tests_command(cmd: list[str] | str, cwd: str = ".") -> tuple[int, str]:
    """מריץ את פקודת הבדיקות ומחזיר (returncode, combined_output)."""
    if isinstance(cmd, str):
        args = cmd.split()
    else:
        args = cmd

    proc = subprocess.run(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


def _extract_failing_files_and_tracebacks(test_output: str, root_dir: str = ".") -> list[tuple[str, str]]:
    """מחלץ קבצים שנכשלו וה-traceback מתוך פלט הבדיקות."""
    failures: list[tuple[str, str]] = []

    # Check for pytest style FAILURES
    pytest_sections = re.split(r"_{3,}\s+([^\n]+)\s+_{3,}", test_output)
    if len(pytest_sections) > 1:
        for i in range(1, len(pytest_sections), 2):
            test_name = pytest_sections[i].strip()
            tb = pytest_sections[i + 1] if i + 1 < len(pytest_sections) else ""
            # find file path in tb
            file_match = re.search(r"([\w\-./\\]+\.py):(\d+):", tb)
            file_path = file_match.group(1) if file_match else ""
            failures.append((file_path or test_name, tb.strip()[:2000]))

    # Check for unittest style FAIL/ERROR
    unittest_matches = re.findall(
        r"(FAIL|ERROR):\s+([^\n]+)\s*\n-+\s*\n(.*?)(?=\n={5,}|\nFAIL:|\nERROR:|\n-{5,}|\Z)",
        test_output,
        re.DOTALL,
    )
    for _, test_name, tb in unittest_matches:
        file_match = re.search(r'File "([^"]+\.py)", line (\d+)', tb)
        file_path = file_match.group(1) if file_match else ""
        failures.append((file_path or test_name.strip(), tb.strip()[:2000]))

    if not failures and ("FAILED" in test_output or "FAIL" in test_output or "ERROR" in test_output):
        # Fallback: capture general failure snippet
        failures.append(("<general>", test_output[-2000:]))

    return failures


def run_self_healing_tests(
    test_cmd: list[str] | str | None = None,
    max_iterations: int = 3,
    root_dir: str = ".",
    config: Config | None = None,
    console: Console | None = None,
) -> HealResult:
    """מריץ בדיקות בלולאת ריפוי עצמי אוטונומית עד להצלחה או הגעה למקסימום איטרציות."""
    config = config or get_config()
    console = console or get_console()

    cmd = test_cmd or _detect_test_runner(root_dir)
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd

    console.write(console.paint(f"\n  🩺 SBpy Self-Healing Test Runner", "cyan", bold=True))
    console.write(console.paint(f"  Command: {cmd_str} (Max iterations: {max_iterations})\n", "grey"))

    fixed_files: set[str] = set()
    initial_failures: list[str] = []

    for i in range(1, max_iterations + 1):
        with Spinner(f"Running test suite (Iteration {i}/{max_iterations})..."):
            code, output = run_tests_command(cmd, cwd=root_dir)

        if code == 0:
            console.write(console.paint(f"\n  ✓ All tests passed successfully! (Iteration {i})", "green", bold=True))
            return HealResult(
                success=True,
                iterations=i,
                initial_failures=initial_failures,
                fixed_files=sorted(fixed_files),
                output=output,
            )

        failures = _extract_failing_files_and_tracebacks(output, root_dir)
        if not initial_failures:
            initial_failures = [f[0] for f in failures]

        console.write(console.paint(f"  ✗ Detected {len(failures)} failing test case(s).", "yellow"))

        if config.offline:
            console.write(console.paint("  ! Offline mode is active; AI self-healing patch skipped.", "red"))
            return HealResult(
                success=False,
                iterations=i,
                initial_failures=initial_failures,
                fixed_files=sorted(fixed_files),
                output=output,
                error_summary="Offline mode active",
            )

        # Generate and apply patches
        patched_any = False
        for target_ref, traceback_text in failures:
            # Locate actual source file to inspect
            target_path = target_ref if os.path.isfile(os.path.join(root_dir, target_ref)) else ""
            if not target_path and target_ref.endswith(".py") and os.path.isfile(target_ref):
                target_path = target_ref

            file_content = ""
            if target_path and os.path.exists(target_path):
                try:
                    with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                        file_content = f.read()
                except OSError:  # sbpy: ignore=silent-except
                    pass

            prompt = f"""You are SBpy's Autonomous Self-Healing Test Engine.
A Python test failed. Analyze the failure and provide the EXACT corrected full file content.

FAILING TEST / TRACEBACK:
{traceback_text}

TARGET FILE: {target_path or 'unknown'}
CURRENT CONTENT:
```python
{file_content}
```

Respond in the following format:
FILE: <relative_path_to_fix>
```python
<complete fixed file code>
```
"""
            engine = get_engine(config)
            with Spinner(f"AI synthesizing fix for {os.path.basename(target_path or 'failure')}..."):
                response = engine.generate(prompt, tier=TIER_COMMAND)

            if response.ok and response.text:
                # Extract file and code
                code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", response.text, re.DOTALL)
                file_match = re.search(r"FILE:\s*([^\n]+)", response.text)

                dest_file = (file_match.group(1).strip() if file_match else target_path) or target_path
                if dest_file and code_match:
                    fixed_code = code_match.group(1)
                    # Snapshot before overwrite
                    if os.path.exists(dest_file):
                        snapshot([dest_file])
                    with open(dest_file, "w", encoding="utf-8") as f:
                        f.write(fixed_code)
                    fixed_files.add(dest_file)
                    patched_any = True
                    console.write(console.paint(f"  ⚡ Applied self-healing patch to: {dest_file}", "green"))

        if not patched_any:
            console.write(console.paint("  ! AI could not deduce a confident patch for this failure.", "red"))
            break

    # Final run to check status
    with Spinner("Verifying final status..."):
        code, output = run_tests_command(cmd, cwd=root_dir)

    success = code == 0
    if success:
        console.write(console.paint(f"\n  🎉 Successfully healed all failing tests! ({len(fixed_files)} file(s) patched)", "green", bold=True))
    else:
        console.write(console.paint("\n  ✗ Self-healing loop reached max iterations without full resolution.", "red"))

    return HealResult(
        success=success,
        iterations=max_iterations,
        initial_failures=initial_failures,
        fixed_files=sorted(fixed_files),
        output=output,
    )


def run_autonomous_agent(
    goal: str,
    root_dir: str = ".",
    max_steps: int = 5,
    config: Config | None = None,
    console: Console | None = None,
) -> AgentResult:
    """מריץ סוכן אוטונומי מונחה-מטרה המבצע שינויים מורכבים בפרויקט."""
    config = config or get_config()
    console = console or get_console()

    console.write(console.paint(f"\n  🤖 SBpy Autonomous Coding Agent", "purple", bold=True))
    console.write(console.paint(f"  Goal: {goal}\n", "white"))

    steps: list[AgentStep] = []
    modified_files: set[str] = set()

    if config.offline:
        console.write(console.paint("  ! Cannot run autonomous agent in offline mode.", "red"))
        return AgentResult(goal=goal, success=False, summary="Offline mode active")

    engine = get_engine(config)

    for step_num in range(1, max_steps + 1):
        prompt = f"""You are SBpy Autonomous Developer Agent.
GOAL: {goal}
CURRENT STEP: {step_num}/{max_steps}
PREVIOUS ACTIONS:
{chr(10).join(f'- Step {i+1}: {s.thought} -> {s.action} on {s.target_file}' for i, s in enumerate(steps))}

Decide the next action. If the goal is completely achieved, respond with ACTION: DONE.
Otherwise respond with:
THOUGHT: <explain your reasoning>
ACTION: <EDIT_FILE | CREATE_FILE | RUN_TESTS | DONE>
TARGET: <file path>
CODE:
```python
<full file contents if editing/creating>
```
"""
        with Spinner(f"Agent planning step {step_num}..."):
            resp = engine.generate(prompt, tier=TIER_PRO)

        if not resp.ok or not resp.text:
            break

        text = resp.text
        thought_match = re.search(r"THOUGHT:\s*([^\n]+)", text)
        action_match = re.search(r"ACTION:\s*([^\n]+)", text)
        target_match = re.search(r"TARGET:\s*([^\n]+)", text)
        code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)

        thought = thought_match.group(1).strip() if thought_match else "Proceeding with task"
        action = action_match.group(1).strip().upper() if action_match else "DONE"
        target = target_match.group(1).strip() if target_match else ""

        console.write(console.paint(f"  [Step {step_num}] {thought}", "cyan"))

        if "DONE" in action:
            steps.append(AgentStep(thought=thought, action="DONE", target_file=target))
            console.write(console.paint(f"\n  ✓ Agent finished goal successfully!", "green", bold=True))
            return AgentResult(
                goal=goal,
                success=True,
                steps=steps,
                modified_files=sorted(modified_files),
                summary="Goal achieved successfully",
            )

        if code_match and target:
            new_code = code_match.group(1)
            target_full = os.path.join(root_dir, target)
            os.makedirs(os.path.dirname(os.path.abspath(target_full)), exist_ok=True)
            if os.path.exists(target_full):
                snapshot([target_full])
            with open(target_full, "w", encoding="utf-8") as f:
                f.write(new_code)
            modified_files.add(target)
            console.write(console.paint(f"    ⚡ Updated {target}", "green"))

        steps.append(AgentStep(thought=thought, action=action, target_file=target))

    return AgentResult(
        goal=goal,
        success=len(modified_files) > 0,
        steps=steps,
        modified_files=sorted(modified_files),
        summary="Agent execution completed",
    )
