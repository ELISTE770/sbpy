"""בדיקות ליכולות שנוספו: דרגות מודל, שורות @, תיקון אוטומטי,
אינדקס פרויקט, בסיס ידע, למידה, הקשר חכם, באטץ', עלות ואינטגרציות."""

from __future__ import annotations

import json
import os
import textwrap
import unittest

from sbpy import batch, contextpack, index, knowledge, learn, pricing, shell, testgen, watcher
from sbpy.config import TIER_AUTO, TIER_COMMAND, TIER_PRO, Config
from sbpy.integrations import editor_lines, to_github_annotations, to_sarif
from sbpy.patcher import build_from_diagnosis, build_from_findings
from sbpy.results import Diagnosis, Finding, Report, ScanResult
from sbpy.static.checks import CATEGORY_BUG, CATEGORY_OPT, CATEGORY_STYLE, SourceUnit, analyze
from tests.support import FakeEngine, IsolatedConfigTest


# ======================================================================
# דרגות מודל
# ======================================================================
class ModelTierTest(IsolatedConfigTest):
    def test_three_tiers_are_distinct(self) -> None:
        config = Config()
        models = {config.model_for(t) for t in (TIER_AUTO, TIER_COMMAND, TIER_PRO)}
        self.assertEqual(len(models), 3)

    def test_auto_is_the_cheapest_tier(self) -> None:
        config = Config()
        auto = pricing.price_per_million(config.model_for(TIER_AUTO))
        command = pricing.price_per_million(config.model_for(TIER_COMMAND))
        pro = pricing.price_per_million(config.model_for(TIER_PRO))
        self.assertLess(auto, command)
        self.assertLess(command, pro)

    def test_unknown_tier_falls_back_to_auto(self) -> None:
        config = Config()
        self.assertEqual(config.model_for("nonsense"), config.model_auto)

    def test_legacy_names_still_work(self) -> None:
        config = Config()
        self.assertEqual(config.model_cheap, config.model_auto)
        self.assertEqual(config.model_smart, config.model_command)

    def test_cli_plus_token_becomes_pro(self) -> None:
        from sbpy import cli

        captured: dict[str, object] = {}

        def fake(args, _code="SFB"):  # type: ignore[no-untyped-def]
            captured["pro"] = args.pro
            return 0

        parser_backup = cli.cmd_shortcut
        cli.cmd_shortcut = fake  # type: ignore[assignment]
        try:
            cli.main(["sfb", "--offline", "+"])
        finally:
            cli.cmd_shortcut = parser_backup  # type: ignore[assignment]
        self.assertTrue(captured["pro"])


# ======================================================================
# שורות @ ב-shell
# ======================================================================
class ErrorClassificationTest(unittest.TestCase):
    def test_quota_is_recognised(self) -> None:
        from sbpy.gemini import classify_error

        exc = RuntimeError("Error code: 429 - quota exceeded for gemini-3.1-pro")
        self.assertEqual(classify_error(exc), "quota")

    def test_unavailable_is_recognised(self) -> None:
        from sbpy.gemini import classify_error

        self.assertEqual(classify_error(RuntimeError("404 model not found")), "unavailable")

    def test_network_is_recognised(self) -> None:
        from sbpy.gemini import classify_error

        self.assertEqual(classify_error(TimeoutError("read timeout")), "network")

    def test_friendly_message_is_short(self) -> None:
        from sbpy.gemini import friendly_error

        exc = RuntimeError("x" * 900)
        self.assertLess(len(friendly_error(exc, "other", "m")), 260)

    def test_quota_message_names_the_model(self) -> None:
        from sbpy.gemini import friendly_error

        message = friendly_error(RuntimeError("429"), "quota", "gemini-3.1-pro-preview")
        self.assertIn("gemini-3.1-pro-preview", message)


class AtLineTest(unittest.TestCase):
    def test_shortcut_line(self) -> None:
        parsed = shell.parse_at_line("@SFB app.py")
        self.assertEqual(parsed["kind"], "shortcut")
        self.assertEqual(parsed["code"], "SFB")
        self.assertEqual(parsed["argument"], "app.py")
        self.assertEqual(parsed["tier"], TIER_COMMAND)

    def test_plus_upgrades_to_pro(self) -> None:
        parsed = shell.parse_at_line("@SFB app.py +")
        self.assertEqual(parsed["tier"], TIER_PRO)
        self.assertTrue(parsed["pro"])

    def test_free_question(self) -> None:
        parsed = shell.parse_at_line("@ למה זה איטי?")
        self.assertEqual(parsed["kind"], "ask")
        self.assertEqual(parsed["question"], "למה זה איטי?")
        self.assertEqual(parsed["tier"], TIER_COMMAND)

    def test_free_question_with_pro(self) -> None:
        parsed = shell.parse_at_line("@ תסביר את האלגוריתם +")
        self.assertTrue(parsed["pro"])
        self.assertNotIn("+", parsed["question"])

    def test_real_decorators_pass_through(self) -> None:
        for line in ("@property", "@functools.wraps(func)", "@app.route('/x')", "@sbpy.SFB.on"):
            self.assertIsNone(shell.parse_at_line(line), line)

    def test_plain_code_passes_through(self) -> None:
        self.assertIsNone(shell.parse_at_line("x = 1"))

    def test_lowercase_shortcut_works(self) -> None:
        parsed = shell.parse_at_line("@sfb app.py")
        self.assertEqual(parsed["code"], "SFB")

    def test_strip_pro_marker(self) -> None:
        self.assertEqual(shell.strip_pro_marker("hello +"), ("hello", True))
        self.assertEqual(shell.strip_pro_marker("hello"), ("hello", False))
        self.assertEqual(shell.strip_pro_marker("+"), ("+", False))

    def test_slash_menu_parsed(self) -> None:
        from sbpy.config import configure, reset_config

        configure(slash_menu=True)
        try:
            self.assertEqual(shell.parse_at_line("/")["kind"], "menu")
            self.assertEqual(shell.parse_at_line("/?")["kind"], "menu")
            self.assertEqual(shell.parse_at_line("/help")["kind"], "menu")

            configure(slash_menu=False)
            self.assertIsNone(shell.parse_at_line("/"))
            # Explicit /? still opens menu
            self.assertEqual(shell.parse_at_line("/?")["kind"], "menu")
        finally:
            reset_config()

    def test_shortcut_help_parsed(self) -> None:
        parsed = shell.parse_at_line("/SFB ?")
        self.assertEqual(parsed["kind"], "shortcut_help")
        self.assertEqual(parsed["code"], "SFB")

    def test_custom_shortcut_alias(self) -> None:
        from sbpy.config import configure, reset_config

        configure(custom_shortcuts={"audit": "SFB +", "fast": "SFB"})
        try:
            parsed = shell.parse_at_line("/audit app.py")
            self.assertEqual(parsed["kind"], "shortcut")
            self.assertEqual(parsed["code"], "SFB")
            self.assertEqual(parsed["argument"], "app.py")
            self.assertTrue(parsed["pro"])
        finally:
            reset_config()


# ======================================================================
# תיקון אוטומטי
# ======================================================================
BUGGY_SOURCE = textwrap.dedent(
    '''\
    """דוגמה."""

    import os
    import json


    def check(value, data):
        name = "x"
        print("hello {name}")
        if value == None:
            return 0
        if value is "empty":
            return 1
        if len(data) == 0:
            return 2
        if "k" in data.keys():
            return 3
        try:
            return json.loads(value)
        except:
            return None
    '''
)


class PatcherTest(IsolatedConfigTest):
    def write(self, name: str, source: str) -> str:
        path = os.path.join(self.home, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)
        return path

    def findings_for(self, path: str) -> list[Finding]:
        unit = SourceUnit.from_path(path)
        return analyze(unit, [CATEGORY_BUG, CATEGORY_STYLE, CATEGORY_OPT])

    def test_fixes_everything_fixable(self) -> None:
        path = self.write("a.py", BUGGY_SOURCE)
        patch = build_from_findings(self.findings_for(path))
        self.assertGreaterEqual(len(patch), 7)

        changed = patch.apply(backup=False)
        self.assertEqual(changed, [path])

        with open(path, encoding="utf-8") as handle:
            fixed = handle.read()
        self.assertIn('print(f"hello {name}")', fixed)
        self.assertIn("if value is None:", fixed)
        self.assertIn('if value == "empty":', fixed)
        self.assertIn("if not data:", fixed)
        self.assertIn('if "k" in data:', fixed)
        self.assertIn("except Exception:", fixed)
        self.assertNotIn("import os", fixed)

    def test_result_still_parses(self) -> None:
        import ast

        path = self.write("b.py", BUGGY_SOURCE)
        build_from_findings(self.findings_for(path)).apply(backup=False)
        with open(path, encoding="utf-8") as handle:
            ast.parse(handle.read())

    def test_diff_is_produced_without_writing(self) -> None:
        path = self.write("c.py", BUGGY_SOURCE)
        patch = build_from_findings(self.findings_for(path))
        diff = patch.diff()
        self.assertIn("+++", diff)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), BUGGY_SOURCE)

    def test_backup_is_written(self) -> None:
        path = self.write("d.py", BUGGY_SOURCE)
        build_from_findings(self.findings_for(path)).apply(backup=True)
        self.assertTrue(os.path.exists(path + ".sbpy.bak"))

    def test_stale_line_is_not_touched(self) -> None:
        path = self.write("e.py", BUGGY_SOURCE)
        patch = build_from_findings(self.findings_for(path))
        # מדמים עריכה של המשתמש אחרי הסריקה
        self.write("e.py", "x = 1\ny = 2\n")
        patch.apply(backup=False)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), "x = 1\ny = 2")

    def test_unfixable_rule_is_reported_as_skipped(self) -> None:
        finding = Finding(rule="mutable-default-arg", message="x", line=1, file="nope.py")
        patch = build_from_findings([finding])
        self.assertFalse(patch)
        self.assertTrue(patch.skipped)

    def test_runtime_name_typo_is_renamed(self) -> None:
        path = self.write("f.py", "value = 1\nprint(valeu)\n")
        diagnosis = Diagnosis(
            title="typo", rule="name.typo", meta={"kind": "name_typo", "bad": "valeu", "good": "value"}
        )
        build_from_diagnosis(diagnosis, path, 2).apply(backup=False)
        with open(path, encoding="utf-8") as handle:
            self.assertIn("print(value)", handle.read())

    def test_runtime_key_typo_keeps_quotes(self) -> None:
        path = self.write("g.py", 'd = {"first_name": 1}\nprint(d["frist_name"])\n')
        diagnosis = Diagnosis(
            title="key",
            rule="key.typo",
            meta={"kind": "key_typo", "bad": "frist_name", "good": "first_name"},
        )
        build_from_diagnosis(diagnosis, path, 2).apply(backup=False)
        with open(path, encoding="utf-8") as handle:
            self.assertIn('d["first_name"]', handle.read())

    def test_missing_import_is_inserted_after_imports(self) -> None:
        path = self.write("h.py", '"""doc."""\n\nimport os\n\nprint(math.pi)\n')
        diagnosis = Diagnosis(
            title="import", rule="name.missing-import", meta={"kind": "missing_import", "module": "math"}
        )
        build_from_diagnosis(diagnosis, path, 5).apply(backup=False)
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertIn("import math", lines)
        self.assertLess(lines.index("import math"), lines.index("print(math.pi)"))


# ======================================================================
# אינדקס פרויקט
# ======================================================================
class ProjectIndexTest(IsolatedConfigTest):
    def build_project(self) -> str:
        root = os.path.join(self.home, "proj")
        os.makedirs(os.path.join(root, "lib"), exist_ok=True)
        with open(os.path.join(root, "pyproject.toml"), "w", encoding="utf-8") as handle:
            handle.write("[project]\nname='x'\n")
        with open(os.path.join(root, "lib", "tools.py"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write("def normalize(value):\n    return value\n\n\nLIMIT = 5\n")
        with open(os.path.join(root, "main.py"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write("print(normalize('x'))\n")
        return root

    def test_symbols_are_indexed(self) -> None:
        root = self.build_project()
        built = index.build(root, config=self.config, use_cache=False)
        self.assertIn("normalize", built.symbols)
        self.assertIn("LIMIT", built.symbols)
        self.assertIn("tools", built.symbols)

    def test_import_statement_is_correct(self) -> None:
        root = self.build_project()
        built = index.build(root, config=self.config, use_cache=False)
        symbol = built.lookup("normalize")[0]
        self.assertEqual(symbol.import_statement(root), "from lib.tools import normalize")

    def test_suggest_import_skips_the_same_file(self) -> None:
        root = self.build_project()
        index.reset()
        symbol = index.suggest_import("normalize", os.path.join(root, "main.py"), config=self.config)
        self.assertIsNotNone(symbol)
        self.assertTrue(symbol.file.endswith("tools.py"))

    def test_find_project_root_uses_markers(self) -> None:
        root = self.build_project()
        found = index.find_project_root(os.path.join(root, "lib", "tools.py"))
        self.assertEqual(os.path.normcase(found), os.path.normcase(root))

    def test_index_can_be_disabled(self) -> None:
        root = self.build_project()
        index.reset()
        config = self.config.with_overrides(project_index=False)
        self.assertIsNone(index.suggest_import("normalize", os.path.join(root, "main.py"), config=config))


# ======================================================================
# בסיס ידע
# ======================================================================
class KnowledgeTest(IsolatedConfigTest):
    def test_known_error_is_matched(self) -> None:
        found = knowledge.lookup("RuntimeError", "dictionary changed size during iteration", config=self.config)
        self.assertIsNotNone(found)
        self.assertGreater(found.confidence, 0.8)
        self.assertTrue(found.rule.startswith("kb."))

    def test_unknown_error_is_not_matched(self) -> None:
        self.assertIsNone(knowledge.lookup("ValueError", "משהו לגמרי אחר", config=self.config))

    def test_custom_entries_are_loaded(self) -> None:
        self.config.ensure_home()
        with open(self.config.home / "knowledge.json", "w", encoding="utf-8") as handle:
            json.dump(
                [{"pattern": "MyCustomFailure", "title": "כשל מותאם", "fix": "עשה כך", "confidence": 0.9}],
                handle,
                ensure_ascii=False,
            )
        knowledge._extra_loaded = False
        found = knowledge.lookup("RuntimeError", "MyCustomFailure happened", config=self.config)
        self.assertIsNotNone(found)
        self.assertEqual(found.title, "כשל מותאם")


# ======================================================================
# למידה
# ======================================================================
class LearnTest(IsolatedConfigTest):
    def make_report(self, message: str = "משהו נדיר") -> Report:
        report = Report(exc_type="RuntimeError", exc_message=message)
        report.add(
            Diagnosis(
                title="הסיבה", suggestion="התיקון", confidence=0.9, source="gemini", rule="gemini.diagnose"
            )
        )
        return report

    def test_signature_ignores_numbers(self) -> None:
        first = learn.signature("ValueError", "failed after 12 attempts")
        second = learn.signature("ValueError", "failed after 97 attempts")
        self.assertEqual(first, second)

    def test_learn_and_lookup(self) -> None:
        report = self.make_report()
        self.assertTrue(learn.learn_from(report, config=self.config))
        found = learn.lookup("RuntimeError", "משהו נדיר", config=self.config)
        self.assertIsNotNone(found)
        self.assertEqual(found.title, "הסיבה")
        self.assertEqual(found.rule, "learned")

    def test_local_answers_are_not_learned(self) -> None:
        report = Report(exc_type="KeyError", exc_message="'a'")
        report.add(Diagnosis(title="local", confidence=0.95, source="local"))
        self.assertFalse(learn.learn_from(report, config=self.config))

    def test_low_confidence_is_not_learned(self) -> None:
        report = Report(exc_type="RuntimeError", exc_message="x")
        report.add(Diagnosis(title="לא בטוח", confidence=0.4, source="gemini"))
        self.assertFalse(learn.learn_from(report, config=self.config))

    def test_package_mapping_is_extracted(self) -> None:
        report = Report(exc_type="ModuleNotFoundError", exc_message="No module named 'thingy'")
        report.add(
            Diagnosis(
                title="חסר",
                suggestion="התקן עם pip install thingy-python",
                confidence=0.9,
                source="gemini",
            )
        )
        learn.learn_from(report, config=self.config)
        self.assertEqual(learn.package_for("thingy", config=self.config), "thingy-python")

    def test_clear_removes_everything(self) -> None:
        learn.learn_from(self.make_report(), config=self.config)
        self.assertGreater(learn.clear(self.config), 0)
        self.assertIsNone(learn.lookup("RuntimeError", "משהו נדיר", config=self.config))

    def test_learning_switch(self) -> None:
        config = self.config.with_overrides(learning=False)
        self.assertFalse(learn.learn_from(self.make_report(), config=config))


# ======================================================================
# הקשר חכם
# ======================================================================
class ContextPackTest(IsolatedConfigTest):
    def test_includes_imports_and_enclosing_function(self) -> None:
        source = textwrap.dedent(
            """\
            import json
            import os


            def helper(value):
                return value * 2


            def broken(data):
                return helper(data) + data["missing"]
            """
        )
        path = os.path.join(self.home, "ctx.py")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)

        from sbpy.context import FrameContext

        ctx = FrameContext(filename=path, lineno=10, function="broken", line="")
        pack = contextpack.build(ctx)
        rendered = pack.render()

        self.assertIn("import json", rendered)
        self.assertIn("def broken", rendered)
        self.assertIn(">>", rendered)
        self.assertIn("helper", rendered)

    def test_no_file_returns_empty(self) -> None:
        self.assertFalse(contextpack.build(None))


# ======================================================================
# באטץ'
# ======================================================================
class BatchTest(IsolatedConfigTest):
    def setUp(self) -> None:
        super().setUp()
        self.engine = FakeEngine()
        self._original = batch.get_engine
        batch.get_engine = lambda config=None: self.engine  # type: ignore[assignment]

    def tearDown(self) -> None:
        batch.get_engine = self._original  # type: ignore[assignment]
        super().tearDown()

    def make_reports(self, count: int) -> list[Report]:
        reports = []
        for number in range(count):
            report = Report(exc_type="RuntimeError", exc_message=f"שגיאה {number}")
            report.fingerprint = f"fp{number}"
            reports.append(report)
        return reports

    def test_many_errors_become_one_call(self) -> None:
        self.engine.payload = {
            "answers": [
                {"index": i, "title": f"סיבה {i}", "cause": "c", "fix": "f", "confidence": 0.9}
                for i in range(1, 6)
            ]
        }
        config = self.online_config()
        reports = self.make_reports(5)
        outcome = batch.diagnose_many(reports, config=config)

        self.assertEqual(outcome.calls, 1, "חמש שגיאות היו צריכות להיות קריאה אחת")
        self.assertEqual(outcome.answered, 5)
        for report in reports:
            self.assertTrue(report.escalated)
            self.assertEqual(report.best.source, "gemini")

    def test_nothing_to_escalate(self) -> None:
        config = self.online_config()
        report = Report(exc_type="KeyError", exc_message="'a'")
        report.add(Diagnosis(title="local", confidence=0.99, source="local"))
        outcome = batch.diagnose_many([report], config=config)
        self.assertEqual(outcome.calls, 0)
        self.assertEqual(outcome.skipped_reason, "nothing-to-escalate")

    def test_review_many_maps_findings_back_to_files(self) -> None:
        self.engine.payload = {
            "findings": [
                {"file": "a.py", "line": 1, "severity": "error", "title": "באג", "why": "w", "fix": "f"},
                {"file": "b.py", "line": 2, "severity": "warn", "title": "אזהרה", "why": "w", "fix": "f"},
            ]
        }
        config = self.online_config()
        findings, outcome = batch.review_many(
            "SFB", [("a.py", "x = 1\n"), ("b.py", "y = 2\ny += 1\n")], focus="bugs", config=config
        )
        self.assertEqual(outcome.calls, 1)
        self.assertEqual({f.file for f in findings}, {"a.py", "b.py"})

    def test_batch_respects_budget(self) -> None:
        from sbpy import budget as budget_module

        config = self.online_config(max_calls_per_run=1)
        budget_module.record("other", "m", 1, config=config)  # מיצוי התקציב
        outcome = batch.diagnose_many(self.make_reports(3), config=config)
        self.assertEqual(outcome.calls, 0)
        self.assertEqual(self.engine.calls, [])
        self.assertIn("run-limit", outcome.skipped_reason)


# ======================================================================
# עלות ואינטגרציות
# ======================================================================
class PricingTest(IsolatedConfigTest):
    def test_estimate_scales_with_tokens(self) -> None:
        small = pricing.estimate(1_000, "gemini-3.6-flash", self.config)
        large = pricing.estimate(1_000_000, "gemini-3.6-flash", self.config)
        self.assertAlmostEqual(large, small * 1000, places=6)

    def test_unknown_model_uses_fallback(self) -> None:
        self.assertEqual(
            pricing.price_per_million("totally-unknown", self.config), pricing.FALLBACK_PRICE
        )

    def test_prefix_match(self) -> None:
        self.assertEqual(
            pricing.price_per_million("gemini-3.6-flash-002", self.config),
            pricing.price_per_million("gemini-3.6-flash", self.config),
        )

    def test_format_marks_estimates(self) -> None:
        self.assertTrue(pricing.format_usd(0.5).startswith("~$"))
        self.assertEqual(pricing.format_usd(0), "$0")

    def test_custom_pricing_file(self) -> None:
        self.config.ensure_home()
        with open(self.config.home / "pricing.json", "w", encoding="utf-8") as handle:
            json.dump({"my-model": 1.5}, handle)
        pricing._cache = None
        self.assertEqual(pricing.price_per_million("my-model", self.config), 1.5)


class IntegrationFormatTest(unittest.TestCase):
    def make_results(self) -> list[ScanResult]:
        result = ScanResult(shortcut="SFB", target="app.py")
        result.findings.append(
            Finding(
                rule="bare-except",
                message="except חשוף",
                line=4,
                col=0,
                severity="error",
                file=os.path.join(os.getcwd(), "app.py"),
                hint="השתמש ב-except Exception",
            )
        )
        return [result]

    def test_sarif_structure(self) -> None:
        data = to_sarif(self.make_results())
        self.assertEqual(data["version"], "2.1.0")
        run = data["runs"][0]
        self.assertEqual(run["tool"]["driver"]["name"], "SBpy")
        self.assertEqual(run["results"][0]["level"], "error")
        self.assertEqual(run["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"], 4)

    def test_sarif_is_serializable(self) -> None:
        json.dumps(to_sarif(self.make_results()), ensure_ascii=False)

    def test_github_annotation_format(self) -> None:
        line = to_github_annotations(self.make_results())[0]
        self.assertTrue(line.startswith("::error file=app.py,line=4"))

    def test_editor_format(self) -> None:
        line = editor_lines(self.make_results())[0]
        self.assertIn("app.py:4:1: error:", line)


class WatcherTest(unittest.TestCase):
    def test_detects_added_modified_removed(self) -> None:
        before = {"a.py": 1.0, "b.py": 2.0}
        after = {"a.py": 1.0, "b.py": 3.0, "c.py": 4.0}
        change = watcher.diff_snapshots(before, after)
        self.assertEqual(change.added, ["c.py"])
        self.assertEqual(change.modified, ["b.py"])
        self.assertEqual(change.removed, [])
        self.assertTrue(change)

    def test_no_change_is_falsy(self) -> None:
        snapshot = {"a.py": 1.0}
        self.assertFalse(watcher.diff_snapshots(snapshot, snapshot))


class TestGenTest(unittest.TestCase):
    def test_extract_fenced_code(self) -> None:
        text = "בבקשה:\n```python\ndef test_x():\n    assert True\n```\nזהו"
        self.assertEqual(testgen.extract_code(text), "def test_x():\n    assert True")

    def test_extract_plain_code(self) -> None:
        self.assertEqual(testgen.extract_code("def test_x():\n    pass"), "def test_x():\n    pass")

    def test_empty(self) -> None:
        self.assertEqual(testgen.extract_code(""), "")


if __name__ == "__main__":
    unittest.main()
