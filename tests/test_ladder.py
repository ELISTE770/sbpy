"""בדיקות לסולם ההסלמה - מתי פונים ל-Gemini ומתי בשום אופן לא."""

from __future__ import annotations

import unittest

from sbpy import budget, hooks, ladder
from sbpy.cache import Cache, fingerprint, normalize
from sbpy.results import Report
from tests.support import FakeEngine, IsolatedConfigTest


class EscalationTest(IsolatedConfigTest):
    def setUp(self) -> None:
        super().setUp()
        self.engine = FakeEngine()
        self._original = ladder.get_engine
        ladder.get_engine = lambda config=None: self.engine  # type: ignore[assignment]

    def tearDown(self) -> None:
        ladder.get_engine = self._original  # type: ignore[assignment]
        super().tearDown()

    def raise_typo(self) -> Exception:
        try:
            value = 1  # noqa: F841
            return valeu  # noqa: F821
        except Exception as exc:  # noqa: BLE001
            return exc

    def raise_obscure(self) -> Exception:
        try:
            raise RuntimeError("משהו מוזר קרה בתוך הפייפליין")
        except Exception as exc:  # noqa: BLE001
            return exc

    # ------------------------------------------------------------------
    def test_confident_local_answer_never_calls_gemini(self) -> None:
        config = self.online_config()
        report = ladder.diagnose(self.raise_typo(), config=config)
        self.assertEqual(report.skipped_reason, "local-confident")
        self.assertFalse(report.escalated)
        self.assertEqual(self.engine.calls, [])

    def test_offline_never_calls_gemini(self) -> None:
        report = ladder.diagnose(self.raise_obscure(), config=self.config)
        self.assertEqual(report.skipped_reason, "offline")
        self.assertEqual(self.engine.calls, [])

    def test_missing_key_never_calls_gemini(self) -> None:
        config = self.config.with_overrides(offline=False, api_key=None)
        report = ladder.diagnose(self.raise_obscure(), config=config)
        self.assertEqual(report.skipped_reason, "no-api-key")
        self.assertEqual(self.engine.calls, [])

    def test_low_confidence_escalates_once(self) -> None:
        config = self.online_config()
        report = ladder.diagnose(self.raise_obscure(), config=config)
        self.assertTrue(report.escalated)
        self.assertEqual(len(self.engine.calls), 1)
        best = report.best
        self.assertIsNotNone(best)
        self.assertEqual(best.source, "gemini")
        self.assertEqual(report.tokens, 42)

    def test_second_identical_error_hits_the_cache(self) -> None:
        # מכבים למידה כדי לבודד את שכבת המטמון עצמה
        config = self.online_config(learning=False)
        ladder.diagnose(self.raise_obscure(), config=config)
        report = ladder.diagnose(self.raise_obscure(), config=config)
        self.assertEqual(len(self.engine.calls), 1, "הקריאה השנייה הייתה צריכה לבוא מהמטמון")
        self.assertEqual(report.skipped_reason, "cache-hit")
        self.assertEqual(report.best.source, "cache")

    def test_cache_can_be_disabled(self) -> None:
        config = self.online_config(cache_enabled=False, learning=False)
        ladder.diagnose(self.raise_obscure(), config=config)
        ladder.diagnose(self.raise_obscure(), config=config)
        self.assertEqual(len(self.engine.calls), 2)

    def test_learned_rule_answers_the_same_error_elsewhere(self) -> None:
        """אותה שגיאה בקובץ אחר - נענית מהכלל שנלמד, בלי קריאה נוספת."""
        config = self.online_config(cache_enabled=False)
        ladder.diagnose(self.raise_obscure(), config=config)
        self.assertEqual(len(self.engine.calls), 1)

        try:
            raise RuntimeError("משהו מוזר קרה בתוך הפייפליין")
        except RuntimeError as exc:
            report = ladder.diagnose(exc, config=config)

        self.assertEqual(len(self.engine.calls), 1, "הכלל שנלמד היה צריך לחסוך את הקריאה")
        self.assertEqual(report.skipped_reason, "learned")
        self.assertEqual(report.best.rule, "learned")

    def test_learning_can_be_disabled(self) -> None:
        config = self.online_config(cache_enabled=False, learning=False)
        ladder.diagnose(self.raise_obscure(), config=config)
        ladder.diagnose(self.raise_obscure(), config=config)
        self.assertEqual(len(self.engine.calls), 2)

    def test_knowledge_base_answers_without_gemini(self) -> None:
        config = self.online_config()
        try:
            raise RuntimeError("dictionary changed size during iteration")
        except RuntimeError as exc:
            report = ladder.diagnose(exc, config=config)
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(report.skipped_reason, "knowledge-base")
        self.assertTrue(report.best.rule.startswith("kb."))

    def test_pip_package_is_learned(self) -> None:
        from sbpy import learn

        self.engine.payload = {
            "title": "החבילה חסרה",
            "cause": "לא מותקנת",
            "fix": "התקן עם pip install super-widget",
            "confidence": 0.9,
        }
        # סף גבוה מאלץ הסלמה, כדי שיהיה ממה ללמוד
        config = self.online_config(escalate_threshold=0.95)
        try:
            raise ModuleNotFoundError("No module named 'superwidget'")
        except ModuleNotFoundError as exc:
            ladder.diagnose(exc, config=config)
        self.assertEqual(learn.package_for("superwidget", config=config), "super-widget")

    def test_run_budget_blocks_further_calls(self) -> None:
        config = self.online_config(max_calls_per_run=1, cache_enabled=False)
        ladder.diagnose(self.raise_obscure(), config=config)
        try:
            raise RuntimeError("שגיאה אחרת לגמרי")
        except RuntimeError as exc:
            report = ladder.diagnose(exc, config=config)
        self.assertEqual(len(self.engine.calls), 1)
        self.assertIn("run-limit", report.skipped_reason)

    def test_force_gemini_overrides_confidence(self) -> None:
        config = self.online_config()
        report = ladder.diagnose(self.raise_typo(), config=config, force_gemini=True)
        self.assertEqual(len(self.engine.calls), 1)
        self.assertTrue(report.escalated)

    def test_engine_failure_is_reported_not_raised(self) -> None:
        self.engine.ok = False
        config = self.online_config()
        report = ladder.diagnose(self.raise_obscure(), config=config)
        self.assertEqual(report.skipped_reason, "fake-failure")
        self.assertIsInstance(report, Report)

    def test_prompt_is_redacted(self) -> None:
        config = self.online_config()
        try:
            secret_token = "sk-abcdefghij1234567890abcdef"  # noqa: F841
            raise RuntimeError("כשל לא מזוהה")
        except RuntimeError as exc:
            ladder.diagnose(exc, config=config)
        prompt = self.engine.calls[0]["prompt"]
        self.assertNotIn("sk-abcdefghij1234567890abcdef", prompt)

    def test_usage_is_recorded(self) -> None:
        config = self.online_config()
        ladder.diagnose(self.raise_obscure(), config=config)
        summary = budget.summary(config)
        self.assertEqual(summary["calls_today"], 1)
        self.assertEqual(summary["tokens_total"], 42)


class FingerprintTest(unittest.TestCase):
    def test_normalize_removes_addresses_and_paths(self) -> None:
        text = normalize("object at 0x7f9c1234 in C:\\Users\\eli\\app.py")
        self.assertNotIn("0x7f9c1234", text)
        self.assertIn("<addr>", text)
        self.assertIn("<path>", text)

    def test_same_error_same_fingerprint(self) -> None:
        a = fingerprint("KeyError", "'name'", "d['name']", "main")
        b = fingerprint("KeyError", "'name'", "d['name']", "main")
        self.assertEqual(a, b)

    def test_different_error_different_fingerprint(self) -> None:
        a = fingerprint("KeyError", "'name'", "d['name']", "main")
        b = fingerprint("KeyError", "'age'", "d['age']", "main")
        self.assertNotEqual(a, b)


class CacheTest(IsolatedConfigTest):
    def test_roundtrip(self) -> None:
        cache = Cache(self.config)
        cache.set("abc", {"title": "כותרת"})
        self.assertEqual(cache.get("abc")["title"], "כותרת")

    def test_missing_key_returns_none(self) -> None:
        self.assertIsNone(Cache(self.config).get("nope"))

    def test_clear_and_stats(self) -> None:
        cache = Cache(self.config)
        cache.set("a", {"title": "x"})
        cache.set("b", {"title": "y"})
        self.assertEqual(cache.stats()["entries"], 2)
        self.assertEqual(cache.clear(), 2)
        self.assertEqual(cache.stats()["entries"], 0)

    def test_disabled_cache_stores_nothing(self) -> None:
        cache = Cache(self.config.with_overrides(cache_enabled=False))
        cache.set("a", {"title": "x"})
        self.assertIsNone(cache.get("a"))


class HookTest(IsolatedConfigTest):
    def test_watch_swallows_when_asked(self) -> None:
        with hooks.watch(show=False, reraise=False) as watcher:
            raise ValueError("בדיקה")
        self.assertIsNotNone(watcher.report)
        self.assertEqual(watcher.report.exc_type, "ValueError")

    def test_watch_reraises_by_default(self) -> None:
        with self.assertRaises(ValueError):
            with hooks.watch(show=False):
                raise ValueError("בדיקה")

    def test_smart_auto_retries_kwarg_typo(self) -> None:
        def target(label, color="blue"):
            return f"{label}-{color}"

        @hooks.smart(show=False)
        def build(label, **options):
            return target(label, **options)

        self.assertEqual(build("ok", colour="red"), "ok-red")

    def test_smart_does_not_retry_unrelated_errors(self) -> None:
        @hooks.smart(show=False)
        def boom():
            return 1 / 0

        with self.assertRaises(ZeroDivisionError):
            boom()

    def test_smart_can_return_default_instead_of_raising(self) -> None:
        @hooks.smart(show=False, reraise=False, default=[])
        def boom():
            raise RuntimeError("x")

        self.assertEqual(boom(), [])

    def test_last_error_is_recorded(self) -> None:
        with hooks.watch(show=False, reraise=False):
            raise KeyError("missing")
        exception = hooks.last_error()
        self.assertIsInstance(exception, KeyError)
        self.assertIsNotNone(hooks.last_report())
        self.assertEqual(hooks.last_report().exc_type, "KeyError")

    def test_builtin_names_need_a_higher_bar(self) -> None:
        """`pritn` -> `print` כן, אבל שם אקראי לא "יתאים" לאיזה builtin."""
        try:
            pritn("x")  # noqa: F821
        except NameError as exc:
            report = ladder.diagnose(exc, config=self.config)
        self.assertEqual(report.best.meta.get("good"), "print")

        try:
            qzweru  # noqa: F821
        except NameError as exc:
            report = ladder.diagnose(exc, config=self.config)
        self.assertEqual(report.best.rule, "name.unknown")

    def test_install_and_uninstall_restore_excepthook(self) -> None:
        import sys

        original = sys.excepthook
        hooks.install()
        self.assertTrue(hooks.is_installed())
        self.assertIsNot(sys.excepthook, original)
        hooks.uninstall()
        self.assertFalse(hooks.is_installed())
        self.assertIs(sys.excepthook, original)


if __name__ == "__main__":
    unittest.main()
