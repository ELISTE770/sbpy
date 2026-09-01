"""Unit tests for SBpy enterprise features."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from sbpy.config import load_project_toml, reset_config, configure
from sbpy.static.checks import SourceUnit, analyze
from sbpy.spinner import Spinner, render_progress_bar
from sbpy.git_ops import install_git_pre_commit_hook, generate_github_ci_workflow
from sbpy.graph import build_file_dependency_graph
from sbpy.rules import load_directory_rules, check_project_rules


class EnterpriseFeaturesTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_config()

    def tearDown(self) -> None:
        reset_config()

    def test_load_project_toml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / "pyproject.toml"
            toml_path.write_text("""[tool.sbpy]
backend = "openai"
model = "gpt-4o"
exclude = ["build", "dist"]
ignore_rules = ["unused-import"]
custom_instructions = "Enterprise clean code"
""", encoding="utf-8")
            data = load_project_toml(td)
            self.assertEqual(data.get("backend"), "openai")
            self.assertEqual(data.get("model"), "gpt-4o")
            self.assertEqual(data.get("custom_instructions"), "Enterprise clean code")
            self.assertIn("build", data.get("exclude", []))
            self.assertIn("unused-import", data.get("ignore_rules", []))

    def test_bracket_ignore_directive(self) -> None:
        code = """def calc():
    x = 1 / 0  # sbpy: ignore[zero-division, bug]
    return x
"""
        unit = SourceUnit.from_source(code, filename="test_calc.py")
        findings = analyze(unit)
        # zero-division should be ignored by the bracket ignore
        self.assertFalse(any(f.rule == "zero-division" for f in findings))

    def test_file_level_ignore(self) -> None:
        code = """# sbpy: ignore-file
def calc():
    x = 1 / 0
    return x
"""
        unit = SourceUnit.from_source(code, filename="test_ignored.py")
        findings = analyze(unit)
        self.assertEqual(len(findings), 0)

    def test_spinner_and_progress_bar(self) -> None:
        with Spinner("Testing spinner..."):
            pass
        bar = render_progress_bar(5, 10, prefix="Testing", length=20)
        self.assertIn("50%", bar)
        self.assertIn("Testing", bar)
        self.assertIn("5/10", bar)

    def test_custom_directory_rules(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rules_dir = Path(td) / ".sbpy" / "rules"
            rules_dir.mkdir(parents=True)
            rule_file = rules_dir / "my_custom_rule.py"
            rule_file.write_text("""from sbpy.static.checks import Finding
def check(unit):
    findings = []
    if "FORBIDDEN_KEYWORD" in unit.source:
        findings.append(Finding(file=unit.filename, line=1, col=0, rule="custom-forbidden", message="Forbidden keyword used", severity="error"))
    return findings
""", encoding="utf-8")
            callables = load_directory_rules(td)
            self.assertGreaterEqual(len(callables), 1)

            unit = SourceUnit.from_source("FORBIDDEN_KEYWORD = 1", filename=str(Path(td) / "app.py"))
            findings = check_project_rules(unit)
            self.assertTrue(any(f.rule == "custom-forbidden" for f in findings))

    def test_git_hook_and_ci_generator(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # Fake git repo
            git_dir = Path(td) / ".git"
            git_dir.mkdir()
            ok = install_git_pre_commit_hook(td)
            self.assertTrue(ok)
            hook_path = git_dir / "hooks" / "pre-commit"
            self.assertTrue(hook_path.is_file())

            ci_file = generate_github_ci_workflow(td)
            self.assertIsNotNone(ci_file)
            self.assertTrue(os.path.isfile(ci_file))

    def test_dependency_graph_builder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            f1 = Path(td) / "module_a.py"
            f2 = Path(td) / "module_b.py"
            f1.write_text("def run(): pass\n", encoding="utf-8")
            f2.write_text("import module_a\n", encoding="utf-8")

            graph = build_file_dependency_graph(td)
            self.assertIn("nodes", graph)
            self.assertIn("edges", graph)
            self.assertEqual(len(graph["nodes"]), 2)
            self.assertEqual(len(graph["edges"]), 1)


if __name__ == "__main__":
    unittest.main()
