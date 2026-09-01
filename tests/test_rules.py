"""בדיקות עבור ניהול חוקי הפרויקט (.sbpyrules)."""

from __future__ import annotations

import json
import os
import unittest

from sbpy.rules import ProjectRules, check_project_rules, format_rules_for_prompt, load_rules
from sbpy.static.checks import SourceUnit
from tests.support import IsolatedConfigTest


class ProjectRulesTest(IsolatedConfigTest):
    def test_banned_imports_and_calls(self) -> None:
        rules = ProjectRules(
            banned_imports={"requests": "Use httpx instead"},
            banned_calls={"eval": "No eval allowed"},
            class_name_pattern=r"^[A-Z][a-zA-Z0-9]+$",
            func_name_pattern=r"^[a-z_][a-z0-9_]*$",
        )

        source = """
import requests
import json

def BadFunction():
    eval("1+1")
    return requests.get("http://example.com")

class lowercase_class:
    pass
"""
        unit = SourceUnit.from_source(source)
        findings = check_project_rules(unit, rules=rules)
        rule_names = {f.rule for f in findings}

        self.assertIn("banned-import", rule_names)
        self.assertIn("banned-call", rule_names)
        self.assertIn("function-naming", rule_names)
        self.assertIn("class-naming", rule_names)

    def test_load_rules_from_file(self) -> None:
        rules_path = os.path.join(self.home, ".sbpyrules")
        data = {
            "banned_imports": {"urllib": "Use requests/httpx"},
            "banned_calls": {"print": "Use logging"},
        }
        with open(rules_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

        loaded = load_rules(self.home)
        self.assertEqual(loaded.banned_imports.get("urllib"), "Use requests/httpx")
        self.assertEqual(loaded.banned_calls.get("print"), "Use logging")

        prompt_rules = format_rules_for_prompt(loaded)
        self.assertIn("urllib", prompt_rules)
        self.assertIn("print", prompt_rules)


if __name__ == "__main__":
    unittest.main()
