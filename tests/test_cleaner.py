"""Unit tests for multi-line and pasted code cleaner."""

from __future__ import annotations

import unittest

from sbpy.cleaner import clean_pasted_code


class CleanerTest(unittest.TestCase):
    def test_clean_repl_prompts(self) -> None:
        raw = ">>> def add(a, b):\n...     return a + b\n>>> add(1, 2)"
        expected = "def add(a, b):\n    return a + b\nadd(1, 2)"
        self.assertEqual(clean_pasted_code(raw), expected)

    def test_clean_line_numbers(self) -> None:
        raw = "1 | def greet():\n2 |     print('hello')\n3 |     return True"
        expected = "def greet():\n    print('hello')\n    return True"
        self.assertEqual(clean_pasted_code(raw), expected)

    def test_clean_bracketed_line_numbers(self) -> None:
        raw = "[1] x = 10\n[2] y = 20\n[3] z = x + y"
        expected = "x = 10\ny = 20\nz = x + y"
        self.assertEqual(clean_pasted_code(raw), expected)

    def test_clean_tab_normalization(self) -> None:
        raw = "\tdef foo():\n\t\treturn 42"
        cleaned = clean_pasted_code(raw)
        self.assertNotIn("\t", cleaned)
        self.assertIn("return 42", cleaned)

    def test_empty_or_clean_code_unchanged(self) -> None:
        code = "def hello():\n    return 'world'"
        self.assertEqual(clean_pasted_code(code), code)
        self.assertEqual(clean_pasted_code(""), "")


if __name__ == "__main__":
    unittest.main()
