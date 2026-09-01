"""בדיקות עבור ניתוח זרימת מידע סטטי (sbpy/taint.py)."""

from __future__ import annotations

import unittest

from sbpy.static.checks import SourceUnit
from sbpy.taint import scan_taint
from tests.support import IsolatedConfigTest


class TaintTest(IsolatedConfigTest):
    def test_taint_flows_from_input_to_system(self) -> None:
        source = """
import os

def handle_request():
    user_data = input("Enter command: ")
    cmd = "echo " + user_data
    os.system(cmd)
"""
        unit = SourceUnit.from_source(source)
        findings = scan_taint(unit)
        self.assertGreater(len(findings), 0)
        self.assertEqual(findings[0].rule, "taint-vulnerability")
        self.assertIn("cmd", findings[0].message)
        self.assertIn("os.system", findings[0].message)

    def test_clean_constant_is_not_tainted(self) -> None:
        source = """
import os

def safe():
    cmd = "echo hello"
    os.system(cmd)
"""
        unit = SourceUnit.from_source(source)
        findings = scan_taint(unit)
        self.assertEqual(len(findings), 0)


if __name__ == "__main__":
    unittest.main()
