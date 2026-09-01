"""בדיקות לשכבה המקומית: מנוע הדמיון והתיקונים לכל סוג שגיאה."""

from __future__ import annotations

import json
import os
import unittest

from sbpy.config import get_config
from sbpy.ladder import diagnose
from sbpy.local import typo
from tests.support import IsolatedConfigTest


class TypoEngineTest(unittest.TestCase):
    def test_identical_is_perfect(self) -> None:
        self.assertEqual(typo.similarity("value", "value"), 1.0)

    def test_case_only_difference_is_near_certain(self) -> None:
        self.assertGreater(typo.similarity("name", "Name"), 0.95)

    def test_style_difference_matches(self) -> None:
        self.assertGreater(typo.similarity("userName", "user_name"), 0.9)

    def test_transposition_scores_high(self) -> None:
        self.assertGreater(typo.similarity("teh", "the"), 0.9)

    def test_short_words_are_less_certain(self) -> None:
        long_pair = typo.similarity("printer", "printex")
        short_pair = typo.similarity("ab", "ac")
        self.assertGreater(long_pair, short_pair)

    def test_unrelated_words_score_low(self) -> None:
        self.assertLess(typo.similarity("elephant", "socket"), 0.5)

    def test_best_match_picks_closest(self) -> None:
        best, score = typo.best_match("valeu", ["value", "values", "total"])
        self.assertEqual(best, "value")
        self.assertGreater(score, 0.7)

    def test_ambiguous_candidates_lower_confidence(self) -> None:
        _, clear = typo.best_match("colr", ["color"])
        _, ambiguous = typo.best_match("colr", ["color", "coler"])
        self.assertGreater(clear, ambiguous)

    def test_no_match_returns_none(self) -> None:
        best, score = typo.best_match("zzzz", ["alpha", "beta"])
        self.assertIsNone(best)
        self.assertEqual(score, 0.0)

    def test_levenshtein_early_exit(self) -> None:
        self.assertEqual(typo.levenshtein("kitten", "sitting"), 3)
        self.assertGreater(typo.levenshtein("a", "abcdefghij", max_distance=2), 2)


class LocalFixerTest(IsolatedConfigTest):
    """כל מקרה כאן חייב להיפתר מקומית, בלי הסלמה."""

    def diagnose_of(self, func) -> tuple:
        try:
            func()
        except Exception as exc:  # noqa: BLE001 - זו בדיוק המטרה
            report = diagnose(exc, config=self.config)
            best = report.best
            self.assertIsNotNone(best, "לא נוצרה אבחנה")
            return report, best
        raise AssertionError("הפונקציה לא זרקה שגיאה")

    def assertLocal(self, report, best, rule: str) -> None:
        self.assertEqual(best.rule, rule, f"ציפיתי לחוק {rule}, קיבלתי {best.rule}")
        self.assertEqual(best.source, "local")
        self.assertFalse(report.escalated, "אסור להסלים ל-Gemini במקרה הזה")
        self.assertGreaterEqual(best.confidence, get_config().escalate_threshold)

    def test_name_typo(self) -> None:
        def case():
            value = 1  # noqa: F841
            return valeu  # noqa: F821

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "name.typo")
        self.assertEqual(best.meta["good"], "value")

    def test_module_name_typo(self) -> None:
        def case():
            return maht.sqrt(4)  # noqa: F821

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "name.module-typo")
        self.assertEqual(best.meta["good"], "math")

    def test_unbound_local(self) -> None:
        def case():
            counter += 1  # noqa: F821
            return counter

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "name.unbound-local")

    def test_attribute_typo(self) -> None:
        def case():
            text = "hello"
            return text.uppercse()

        report, best = self.diagnose_of(case)
        self.assertEqual(best.rule, "attr.typo")
        self.assertEqual(best.meta["good"], "upper")

    def test_none_attribute(self) -> None:
        def case():
            result = [3, 1].sort()
            return result.index(1)

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "attr.none")

    def test_module_not_installed_maps_to_pip_name(self) -> None:
        def case():
            import definitely_not_a_real_module_xyz  # noqa: F401

        report, best = self.diagnose_of(case)
        self.assertEqual(best.rule, "import.not-installed")

    def test_module_typo_suggests_stdlib(self) -> None:
        def case():
            import jsno  # noqa: F401

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "import.typo")
        self.assertEqual(best.meta["good"], "json")

    def test_key_typo(self) -> None:
        def case():
            person = {"first_name": "a", "last_name": "b"}
            return person["first_nmae"]

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "key.typo")
        self.assertEqual(best.meta["good"], "first_name")

    def test_key_case_mismatch(self) -> None:
        def case():
            data = {"Width": 1}
            return data["width"]

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "key.case")
        self.assertEqual(best.meta["good"], "Width")

    def test_index_out_of_range_reports_length(self) -> None:
        def case():
            items = [1, 2, 3]
            return items[9]

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "index.out-of-range")
        self.assertEqual(best.meta["length"], 3)

    def test_empty_sequence(self) -> None:
        def case():
            rows = []
            return rows[0]

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "index.empty")

    def test_kwarg_typo_is_retryable(self) -> None:
        def target(label, color="blue"):
            return label + color

        def case():
            return target("x", colour="red")

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "type.kwarg-typo")
        self.assertEqual(best.meta["good"], "color")
        self.assertTrue(best.meta["retryable"])

    def test_missing_arguments_shows_signature(self) -> None:
        def target(first, second):
            return first + second

        def case():
            return target()

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "type.missing-args")
        self.assertIn("first", best.title)

    def test_operand_mismatch(self) -> None:
        def case():
            return 1 + "2"

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "type.operand")

    def test_int_parse(self) -> None:
        def case():
            return int("12.5")

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "value.int")

    def test_unpack_mismatch(self) -> None:
        def case():
            a, b, c = [1, 2]  # noqa: F841

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "value.unpack")
        self.assertEqual(best.meta["want"], 3)

    def test_zero_division(self) -> None:
        def case():
            return 1 / 0

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "zero.division")

    def test_json_decode(self) -> None:
        def case():
            return json.loads("{'a': 1}")

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "value.json")

    def test_file_typo_finds_neighbour(self) -> None:
        real = os.path.join(self.home, "settings.json")
        with open(real, "w", encoding="utf-8") as handle:
            handle.write("{}")

        def case():
            open(os.path.join(self.home, "setings.json"), encoding="utf-8")

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "file.typo")
        self.assertTrue(best.meta["good"].endswith("settings.json"))

    def test_recursion(self) -> None:
        def case():
            def loop(n):
                return loop(n + 1)

            return loop(0)

        report, best = self.diagnose_of(case)
        self.assertLocal(report, best, "recursion.limit")

    def test_unknown_name_stays_low_confidence(self) -> None:
        def case():
            return qwertyuiopasdfgh  # noqa: F821

        report, best = self.diagnose_of(case)
        self.assertEqual(best.rule, "name.unknown")
        self.assertLess(best.confidence, self.config.escalate_threshold)


class SyntaxFixerTest(IsolatedConfigTest):
    def diagnose_source(self, source: str):
        try:
            compile(source, "<test>", "exec")
        except SyntaxError as exc:
            return diagnose(exc, config=self.config)
        raise AssertionError("הקוד לא היה שגוי")

    def test_python2_print(self) -> None:
        report = self.diagnose_source('print "hello"\n')
        rules = {d.rule for d in report.diagnoses}
        self.assertIn("syntax.python2", rules)

    def test_missing_colon(self) -> None:
        report = self.diagnose_source("if True\n    pass\n")
        rules = {d.rule for d in report.diagnoses}
        self.assertIn("syntax.colon", rules)


class NewFixersTest(IsolatedConfigTest):
    def test_async_loop_running(self) -> None:
        exc = RuntimeError("This event loop is already running")
        report = diagnose(exc, config=self.config)
        self.assertEqual(report.best.rule, "async.loop_running")

    def test_async_not_awaitable(self) -> None:
        exc = TypeError("object int can't be used in 'await' expression")
        report = diagnose(exc, config=self.config)
        self.assertEqual(report.best.rule, "async.not_awaitable")

    def test_database_no_table(self) -> None:
        import sqlite3
        exc = sqlite3.OperationalError("no such table: users")
        report = diagnose(exc, config=self.config)
        self.assertEqual(report.best.rule, "db.no_table")
        self.assertIn("users", report.best.title)

    def test_database_locked(self) -> None:
        import sqlite3
        exc = sqlite3.OperationalError("database is locked")
        report = diagnose(exc, config=self.config)
        self.assertEqual(report.best.rule, "db.locked")

    def test_pydantic_validation_error(self) -> None:
        class ValidationError(ValueError):
            pass
        exc = ValidationError("1 validation error for User\nemail: field required")
        report = diagnose(exc, config=self.config)
        self.assertEqual(report.best.rule, "pydantic.validation")


if __name__ == "__main__":
    unittest.main()

