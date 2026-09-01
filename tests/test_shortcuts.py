"""בדיקות לקיצורי הדרך ולמדיניות ההסלמה שלהם."""

from __future__ import annotations

import os
import textwrap
import unittest

from sbpy import shortcuts
from sbpy.shortcuts import SHORTCUTS, resolve_target, run, scan_directives
from tests.support import FakeEngine, IsolatedConfigTest

BUGGY = """\
import os


def collect(items=[]):
    total = ""
    for i in range(len(items)):
        total += str(items[i])
    return total
"""

CLEAN = """\
def add(first: int, second: int) -> int:
    \"\"\"מחבר שני מספרים.\"\"\"
    return first + second
"""


class TargetResolutionTest(IsolatedConfigTest):
    def write(self, name: str, source: str) -> str:
        path = os.path.join(self.home, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        return path

    def test_resolve_file(self) -> None:
        path = self.write("a.py", CLEAN)
        target = resolve_target(path)
        self.assertEqual(target.filename, path)
        self.assertIn("def add", target.source)

    def test_resolve_code_string(self) -> None:
        target = resolve_target("def f():\n    return 1\n")
        self.assertEqual(target.filename, "<code>")

    def test_resolve_function(self) -> None:
        def sample(value):
            return value * 2

        target = resolve_target(sample)
        self.assertIn("def sample", target.source)
        self.assertEqual(target.label, "TargetResolutionTest.test_resolve_function.<locals>.sample")
        self.assertGreater(target.start_line, 1)

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            resolve_target("no-such-file.py")


class LocalPassTest(IsolatedConfigTest):
    def test_sfb_finds_local_bugs_without_gemini(self) -> None:
        result = run("SFB", BUGGY, config=self.config)
        found = {finding.rule for finding in result.findings}
        self.assertIn("mutable-default-arg", found)
        self.assertFalse(result.escalated)

    def test_line_numbers_are_offset_for_functions(self) -> None:
        def sample(items=[]):
            return items

        result = run("SFB", sample, config=self.config)
        self.assertTrue(result.findings)
        self.assertGreater(result.findings[0].line, 10)

    def test_cmp_is_local_only(self) -> None:
        self.assertEqual(SHORTCUTS["CMP"].escalate, shortcuts.ESCALATE_NEVER)

    def test_unknown_shortcut_raises(self) -> None:
        with self.assertRaises(KeyError):
            run("NOPE", CLEAN, config=self.config)


class EscalationPolicyTest(IsolatedConfigTest):
    def setUp(self) -> None:
        super().setUp()
        self.engine = FakeEngine(payload={"findings": []})
        self._original = shortcuts.get_engine
        shortcuts.get_engine = lambda config=None: self.engine  # type: ignore[assignment]

    def tearDown(self) -> None:
        shortcuts.get_engine = self._original  # type: ignore[assignment]
        super().tearDown()

    def test_local_findings_prevent_escalation(self) -> None:
        config = self.online_config()
        result = run("SFB", BUGGY, config=config)
        self.assertTrue(result.findings)
        self.assertFalse(result.escalated)
        self.assertEqual(self.engine.calls, [])

    def test_clean_code_escalates(self) -> None:
        config = self.online_config()
        result = run("SFB", CLEAN, config=config)
        self.assertTrue(result.escalated)
        self.assertEqual(result.escalation_reason, "no-local-findings")
        self.assertEqual(len(self.engine.calls), 1)

    def test_deep_forces_escalation_even_with_findings(self) -> None:
        config = self.online_config()
        result = run("SFB", BUGGY, deep=True, config=config)
        self.assertTrue(result.escalated)
        self.assertEqual(result.escalation_reason, "deep")
        self.assertEqual(len(self.engine.calls), 1)

    def test_never_policy_ignores_gemini(self) -> None:
        config = self.online_config()
        run("CMP", CLEAN, config=config)
        self.assertEqual(self.engine.calls, [])

    def test_offline_blocks_escalation(self) -> None:
        result = run("SFB", CLEAN, config=self.config)
        self.assertEqual(self.engine.calls, [])
        self.assertTrue(any("offline" in note for note in result.notes))

    def test_second_run_uses_cache(self) -> None:
        config = self.online_config()
        run("SFB", CLEAN, config=config)
        result = run("SFB", CLEAN, config=config)
        self.assertEqual(len(self.engine.calls), 1)
        self.assertEqual(result.escalation_reason, "cache")

    def test_gemini_findings_are_parsed(self) -> None:
        self.engine.payload = {
            "findings": [
                {
                    "line": 2,
                    "severity": "error",
                    "title": "באג לוגי",
                    "why": "תרחיש",
                    "fix": "תקן",
                    "confidence": 0.8,
                }
            ]
        }
        config = self.online_config()
        result = run("SFB", CLEAN, config=config)
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.source, "gemini")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(finding.message, "באג לוגי")

    def test_explain_mode_returns_text(self) -> None:
        self.engine.payload = {}
        config = self.online_config()
        self.engine.ok = True
        result = run("EXP", CLEAN, config=config)
        self.assertTrue(result.escalated)
        self.assertTrue(result.text)

    def test_code_is_redacted_before_sending(self) -> None:
        config = self.online_config()
        source = 'TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz0123"\n\n\ndef f():\n    return TOKEN\n'
        run("EXP", source, config=config)
        prompt = self.engine.calls[0]["prompt"]
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123", prompt)


class DirectiveTest(IsolatedConfigTest):
    def test_finds_directives_and_scope(self) -> None:
        source = textwrap.dedent(
            """
            # /SFB
            def risky(items=[]):
                return items


            def other():
                # /SEC
                return 1
            """
        )
        path = os.path.join(self.home, "d.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)

        directives = scan_directives(path)
        codes = {d.code for d in directives}
        self.assertEqual(codes, {"SFB", "SEC"})
        by_code = {d.code: d for d in directives}
        self.assertEqual(by_code["SFB"].scope, "risky")
        self.assertEqual(by_code["SEC"].scope, "other")

    def test_unknown_directive_is_ignored(self) -> None:
        path = os.path.join(self.home, "e.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# /NOTAREALCODE\nx = 1\n")
        self.assertEqual(scan_directives(path), [])

    def test_directive_question_is_captured(self) -> None:
        path = os.path.join(self.home, "f.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# /ASK למה זה איטי?\nx = 1\n")
        directives = scan_directives(path)
        self.assertEqual(directives[0].code, "ASK")
        self.assertEqual(directives[0].question, "למה זה איטי?")


class CliHelperTest(IsolatedConfigTest):
    def test_iter_python_files_skips_noise(self) -> None:
        from sbpy.cli import iter_python_files

        os.makedirs(os.path.join(self.home, "pkg"), exist_ok=True)
        os.makedirs(os.path.join(self.home, ".venv"), exist_ok=True)
        os.makedirs(os.path.join(self.home, "__pycache__"), exist_ok=True)
        for path in ("pkg/a.py", ".venv/b.py", "__pycache__/c.py", "d.txt"):
            with open(os.path.join(self.home, path), "w", encoding="utf-8") as handle:
                handle.write("x = 1\n")

        found = [os.path.basename(p) for p in iter_python_files(self.home)]
        self.assertEqual(found, ["a.py"])

    def test_shortcut_list_is_complete(self) -> None:
        codes = {code for code, _, _ in shortcuts.list_shortcuts()}
        self.assertTrue({"SFB", "SEC", "OPT", "CMP", "EXP", "TST", "ASK"} <= codes)


class ShellTest(IsolatedConfigTest):
    def test_startup_file_exists_and_compiles(self) -> None:
        import py_compile
        import sbpy

        startup = os.path.join(os.path.dirname(os.path.abspath(sbpy.__file__)), "_startup.py")
        self.assertTrue(os.path.isfile(startup))
        py_compile.compile(startup, doraise=True)

    def test_no_shell_env_blocks_auto_launch(self) -> None:
        from sbpy import cli

        os.environ["SBPY_NO_SHELL"] = "1"
        self.assertFalse(cli._is_interactive())

    def test_bare_invocation_without_tty_prints_help(self) -> None:
        from sbpy import cli

        os.environ["SBPY_NO_SHELL"] = "1"
        self.assertEqual(cli.main([]), cli.EXIT_OK)

    def test_shell_command_spawns_python_with_startup(self) -> None:
        from sbpy import cli

        captured: dict[str, object] = {}

        def fake_call(command, env=None):  # type: ignore[no-untyped-def]
            captured["command"] = command
            captured["env"] = env or {}
            return 0

        original = cli.subprocess.call
        cli.subprocess.call = fake_call  # type: ignore[assignment]
        try:
            code = cli.main(["shell", "--offline", "--force"])
        finally:
            cli.subprocess.call = original  # type: ignore[assignment]

        self.assertEqual(code, 0)
        command = captured["command"]
        self.assertTrue(str(command[-1]).endswith("_startup.py"))
        environment = captured["env"]
        self.assertEqual(environment["SBPY_OFFLINE"], "1")
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")


if __name__ == "__main__":
    unittest.main()
