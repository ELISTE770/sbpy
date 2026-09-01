"""בדיקות לתשתית: ניקוי סודות, תצורה, תקציב, תרגום ותצוגה."""

from __future__ import annotations

import io
import os
import unittest

from sbpy import budget
from sbpy.config import reset_config
from sbpy.console import Console
from sbpy.gemini import parse_json
from sbpy.i18n import CATALOG, available_languages, t
from sbpy.redact import redact, redact_paths, scan_secrets
from sbpy.render import render_compact, render_report, render_scan
from sbpy.results import Diagnosis, Finding, Report, ScanResult
from tests.support import IsolatedConfigTest


class RedactTest(unittest.TestCase):
    def test_google_key_is_masked(self) -> None:
        text = redact("key = AIzaSyA1234567890abcdefghijklmnopqrstuvw")
        self.assertNotIn("AIzaSyA1234567890abcdefghijklmnopqrstuvw", text)

    def test_openai_key_is_masked(self) -> None:
        self.assertNotIn("sk-abcdefghij1234567890", redact("sk-abcdefghij1234567890abcdef"))

    def test_github_token_is_masked(self) -> None:
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123", redact("ghp_abcdefghijklmnopqrstuvwxyz0123"))

    def test_password_assignment_is_masked(self) -> None:
        text = redact('password = "hunter2secret"')
        self.assertNotIn("hunter2secret", text)
        self.assertIn("password", text)

    def test_connection_string_is_masked(self) -> None:
        text = redact("postgres://admin:supersecret@db.internal:5432/app")
        self.assertNotIn("supersecret", text)

    def test_home_path_becomes_tilde(self) -> None:
        home = os.path.expanduser("~")
        self.assertIn("~", redact_paths(os.path.join(home, "project", "app.py")))

    def test_email_is_masked(self) -> None:
        self.assertNotIn("someone@example.com", redact("contact someone@example.com now"))

    def test_ordinary_code_survives(self) -> None:
        code = "def add(a, b):\n    return a + b\n"
        self.assertEqual(redact(code), code)

    def test_scan_secrets_reports_lines(self) -> None:
        source = 'x = 1\nAPI_KEY = "sk-abcdefghij1234567890abcdef"\ny = 2\n'
        found = scan_secrets(source)
        self.assertTrue(found)
        self.assertEqual(found[0][1], 2)

    def test_env_placeholder_is_not_a_secret(self) -> None:
        source = 'import os\nAPI_KEY = os.environ["KEY"]\n'
        self.assertEqual(scan_secrets(source), [])

    def test_ellipsis_placeholder_is_not_a_secret(self) -> None:
        self.assertEqual(scan_secrets('# password = "..." לדוגמה'), [])

    def test_template_placeholder_is_not_a_secret(self) -> None:
        self.assertEqual(scan_secrets('token = "${TOKEN}"'), [])

    def test_changeme_is_not_a_secret(self) -> None:
        self.assertEqual(scan_secrets('secret = "changeme"'), [])

    def test_commented_out_real_key_is_still_a_secret(self) -> None:
        self.assertEqual(len(scan_secrets('# API_KEY = "sk-abcdefghij1234567890abcdef"')), 1)

    def test_one_finding_per_secret(self) -> None:
        found = scan_secrets('API_KEY = "sk-abcdefghij1234567890abcdef"')
        self.assertEqual(len(found), 1)


class ConfigTest(IsolatedConfigTest):
    def test_env_overrides_are_read(self) -> None:
        os.environ["SBPY_THRESHOLD"] = "0.5"
        os.environ["SBPY_MAX_CALLS_RUN"] = "3"
        config = reset_config()
        self.assertEqual(config.escalate_threshold, 0.5)
        self.assertEqual(config.max_calls_per_run, 3)

    def test_bad_env_value_falls_back(self) -> None:
        os.environ["SBPY_THRESHOLD"] = "not-a-number"
        self.assertEqual(reset_config().escalate_threshold, 0.72)

    def test_unknown_override_raises(self) -> None:
        with self.assertRaises(TypeError):
            self.config.with_overrides(nonexistent=1)

    def test_can_call_gemini_requires_key_and_online(self) -> None:
        self.assertFalse(self.config.can_call_gemini)
        self.assertTrue(self.config.with_overrides(offline=False, api_key="k").can_call_gemini)
        self.assertFalse(self.config.with_overrides(offline=True, api_key="k").can_call_gemini)

    def test_home_paths(self) -> None:
        self.assertTrue(str(self.config.cache_dir).endswith("cache"))
        self.assertTrue(str(self.config.usage_file).endswith("usage.jsonl"))


class BudgetTest(IsolatedConfigTest):
    def test_offline_is_blocked(self) -> None:
        allowed, reason = budget.check("t", self.config)
        self.assertFalse(allowed)
        self.assertEqual(reason, "offline")

    def test_missing_key_is_blocked(self) -> None:
        config = self.config.with_overrides(offline=False, api_key=None)
        allowed, reason = budget.check("t", config)
        self.assertFalse(allowed)
        self.assertEqual(reason, "no-api-key")

    def test_run_limit(self) -> None:
        config = self.online_config(max_calls_per_run=2)
        self.assertTrue(budget.check("t", config)[0])
        budget.record("t", "m", 10, config=config)
        budget.record("t", "m", 10, config=config)
        allowed, reason = budget.check("t", config)
        self.assertFalse(allowed)
        self.assertIn("run-limit", reason)

    def test_day_limit(self) -> None:
        config = self.online_config(max_calls_per_day=1, max_calls_per_run=100)
        budget.record("t", "m", 1, config=config)
        allowed, reason = budget.check("t", config)
        self.assertFalse(allowed)
        self.assertIn("day-limit", reason)

    def test_cached_calls_do_not_consume_budget(self) -> None:
        config = self.online_config(max_calls_per_run=1)
        budget.record("t", "m", 0, cached=True, config=config)
        self.assertTrue(budget.check("t", config)[0])
        self.assertEqual(budget.summary(config)["cached_hits"], 1)

    def test_summary_shape(self) -> None:
        config = self.online_config()
        budget.record("diagnose", "m", 7, config=config)
        summary = budget.summary(config)
        self.assertEqual(summary["tokens_total"], 7)
        self.assertEqual(summary["by_task"]["diagnose"], 1)
        self.assertEqual(summary["run"]["calls"], 1)


class I18nTest(unittest.TestCase):
    def test_both_languages_exist(self) -> None:
        self.assertEqual(set(available_languages()), {"he", "en"})

    def test_every_entry_has_both_languages(self) -> None:
        missing = [key for key, entry in CATALOG.items() if not (entry.get("he") and entry.get("en"))]
        self.assertEqual(missing, [])

    def test_formatting(self) -> None:
        self.assertIn("print", t("name.typo.suggestion", "he", best="print"))
        self.assertIn("Did you mean", t("name.typo.suggestion", "en", best="print"))

    def test_unknown_key_returns_key(self) -> None:
        self.assertEqual(t("no.such.key", "he"), "no.such.key")

    def test_missing_placeholder_does_not_crash(self) -> None:
        self.assertIsInstance(t("name.typo.suggestion", "he"), str)

    def test_key_named_key_does_not_collide(self) -> None:
        self.assertIn("age", t("key.typo.title", "he", key="age"))


class JsonParsingTest(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(parse_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self) -> None:
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_with_surrounding_text(self) -> None:
        self.assertEqual(parse_json('בבקשה:\n{"a": 1}\nזהו'), {"a": 1})

    def test_broken_json_returns_none(self) -> None:
        self.assertIsNone(parse_json("not json at all"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(parse_json(""))


class RenderTest(IsolatedConfigTest):
    def make_report(self) -> Report:
        report = Report(exc_type="KeyError", exc_message="'name'", where="app.py:10")
        report.add(
            Diagnosis(
                title="המפתח לא קיים",
                suggestion="האם התכוונת ל-Name?",
                confidence=0.94,
                source="local",
                rule="key.typo",
            )
        )
        report.skipped_reason = "local-confident"
        return report

    def test_report_render_is_plain_without_color(self) -> None:
        stream = io.StringIO()
        console = Console(stream=stream, color=False)
        render_report(self.make_report(), config=self.config, console=console)
        text = stream.getvalue()
        self.assertIn("KeyError", text)
        self.assertIn("המפתח לא קיים", text)
        self.assertNotIn("\x1b[", text)

    def test_compact_render(self) -> None:
        line = render_compact(self.make_report(), self.config)
        self.assertIn("local", line)
        self.assertIn("המפתח לא קיים", line)

    def test_empty_report_compact(self) -> None:
        report = Report(exc_type="X", exc_message="y", skipped_reason="offline")
        self.assertIn("offline", render_compact(report, self.config))

    def test_scan_render(self) -> None:
        stream = io.StringIO()
        console = Console(stream=stream, color=False)
        result = ScanResult(shortcut="SFB", target="app.py")
        result.findings.append(
            Finding(rule="bare-except", message="except חשוף", line=4, severity="error", file="app.py")
        )
        render_scan(result, config=self.config, console=console)
        text = stream.getvalue()
        self.assertIn("SFB", text)
        self.assertIn("bare-except", text)
        self.assertIn("1 error", text)

    def test_scan_render_empty(self) -> None:
        stream = io.StringIO()
        console = Console(stream=stream, color=False)
        render_scan(ScanResult(shortcut="SFB", target="clean.py"), config=self.config, console=console)
        self.assertIn("לא נמצאו ממצאים", stream.getvalue())


class ResultsTest(unittest.TestCase):
    def test_best_prefers_confidence(self) -> None:
        report = Report()
        report.add(Diagnosis(title="a", confidence=0.4, source="gemini"))
        report.add(Diagnosis(title="b", confidence=0.9, source="local"))
        self.assertEqual(report.best.title, "b")

    def test_add_ignores_none(self) -> None:
        report = Report()
        report.add(None)
        self.assertEqual(report.diagnoses, [])

    def test_to_dict_is_serializable(self) -> None:
        import json

        report = Report(exc_type="X")
        report.add(Diagnosis(title="a", confidence=0.5))
        json.dumps(report.to_dict(), ensure_ascii=False)

    def test_scan_result_len_and_bool(self) -> None:
        result = ScanResult(shortcut="SFB", target="x")
        self.assertFalse(result)
        result.findings.append(Finding(rule="r", message="m", line=1))
        self.assertTrue(result)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
