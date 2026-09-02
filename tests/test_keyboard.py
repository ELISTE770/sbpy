"""Tests for keyboard transliteration and normalization."""

from __future__ import annotations

import unittest
from sbpy.keyboard import is_hebrew_text, normalize_input_command, transliterate_keyboard
from sbpy.shell import parse_at_line


class KeyboardTransliterationTest(unittest.TestCase):
    def test_transliterate_sbpy(self) -> None:
        self.assertEqual(transliterate_keyboard("דנפט"), "sbpy")
        self.assertTrue(is_hebrew_text("דנפט"))
        self.assertFalse(is_hebrew_text("sbpy"))

    def test_normalize_slash_commands(self) -> None:
        self.assertEqual(normalize_input_command(".דכנ"), "/sfb")
        self.assertEqual(normalize_input_command(".דקאופ"), "/setup")
        self.assertEqual(normalize_input_command(".וי"), "/ui")

    def test_parse_at_line_with_hebrew_layout(self) -> None:
        parsed_sfb = parse_at_line(".דכנ app.py")
        self.assertIsNotNone(parsed_sfb)
        self.assertEqual(parsed_sfb.get("code"), "SFB")
        self.assertEqual(parsed_sfb.get("argument"), "app.py")

        parsed_setup = parse_at_line(".דקאופ")
        self.assertIsNotNone(parsed_setup)
        self.assertEqual(parsed_setup.get("kind"), "setup")

        parsed_ui = parse_at_line(".וי")
        self.assertIsNotNone(parsed_ui)
        self.assertEqual(parsed_ui.get("kind"), "ui")

        parsed_direct_sbpy1 = parse_at_line("דנפט")
        self.assertIsNotNone(parsed_direct_sbpy1)
        self.assertEqual(parsed_direct_sbpy1.get("kind"), "fullinfo")

        parsed_direct_sbpy2 = parse_at_line("טפנד")
        self.assertIsNotNone(parsed_direct_sbpy2)
        self.assertEqual(parsed_direct_sbpy2.get("kind"), "fullinfo")

        parsed_direct_sfb = parse_at_line("דכנ main.py")
        self.assertIsNotNone(parsed_direct_sfb)
        self.assertEqual(parsed_direct_sfb.get("code"), "SFB")
        self.assertEqual(parsed_direct_sfb.get("argument"), "main.py")

    def test_hebrew_name_error_diagnosis(self) -> None:
        from sbpy.local.fixers import ErrorInfo, fix_name_error

        exc_tpnd = NameError("name 'טפנד' is not defined")
        info_tpnd = ErrorInfo(exc=exc_tpnd, exc_type=NameError, message=str(exc_tpnd), lang="he")
        diags_tpnd = fix_name_error(info_tpnd)
        self.assertTrue(len(diags_tpnd) > 0)
        self.assertEqual(diags_tpnd[0].patch, "sbpy")
        self.assertGreaterEqual(diags_tpnd[0].confidence, 0.95)

        exc_dnpt = NameError("name 'דנפט' is not defined")
        info_dnpt = ErrorInfo(exc=exc_dnpt, exc_type=NameError, message=str(exc_dnpt), lang="he")
        diags_dnpt = fix_name_error(info_dnpt)
        self.assertTrue(len(diags_dnpt) > 0)
        self.assertEqual(diags_dnpt[0].patch, "sbpy")

        exc_print = NameError("name 'פרןמא' is not defined")
        info_print = ErrorInfo(exc=exc_print, exc_type=NameError, message=str(exc_print), lang="he")
        diags_print = fix_name_error(info_print)
        self.assertTrue(len(diags_print) > 0)
        self.assertEqual(diags_print[0].patch, "print")

    def test_transliterate_full_line_and_multilingual(self) -> None:
        from sbpy.keyboard import transliterate_line

        # Hebrew QWERTY full line
        self.assertEqual(transliterate_line('פרןמא("hello")'), 'print("hello")')

        # Hebrew Semantic pseudo-code
        self.assertEqual(transliterate_line('הדפס("hello")'), 'print("hello")')
        self.assertEqual(transliterate_line('אם a == 1:'), 'if a == 1:')
        self.assertEqual(transliterate_line('החזר 42'), 'return 42')

        # Russian JCUKEN -> QWERTY
        self.assertEqual(transliterate_line('вуа фвв():'), 'def add():')

    def test_syntax_error_foreign_keyboard(self) -> None:
        from sbpy.local.fixers import ErrorInfo, fix_syntax

        exc = SyntaxError("invalid syntax")
        exc.text = 'אם f == 1:\n'
        exc.lineno = 1
        info = ErrorInfo(exc=exc, exc_type=SyntaxError, message="invalid syntax", lang="he")
        diags = fix_syntax(info)
        self.assertTrue(len(diags) > 0)
        self.assertEqual(diags[0].patch, 'if f == 1:')
        self.assertGreaterEqual(diags[0].confidence, 0.95)


if __name__ == "__main__":
    unittest.main()
