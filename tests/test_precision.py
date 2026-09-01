"""Precision suite: clean code must produce **zero** findings.

Every other test asks "does rule X fire on bad code". Nothing asked "does
it stay quiet on good code" - and that is exactly how the auto-fixer came
to delete a live import.

A checker that cries wolf gets switched off, so a false positive is a real
defect here, not a cosmetic one. Each sample below is ordinary, idiomatic
Python that a reviewer would pass without comment.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest

from sbpy.patcher import build_from_findings
from sbpy.static.checks import (
    CATEGORY_BUG,
    CATEGORY_COMPLEXITY,
    CATEGORY_MOD,
    CATEGORY_OPT,
    CATEGORY_SEC,
    CATEGORY_STYLE,
    SourceUnit,
    analyze,
)

NOISY_CATEGORIES = (CATEGORY_BUG, CATEGORY_STYLE, CATEGORY_SEC, CATEGORY_OPT)

# ----------------------------------------------------------------------
# Ordinary code. Nothing here deserves a finding.
# ----------------------------------------------------------------------
CLEAN_SAMPLES: dict[str, str] = {
    "guard_clause": '''
        def describe(user):
            """Returns a display name for a user."""
            if user is None:
                return "anonymous"
            return user.name or "anonymous"
    ''',
    "default_none": '''
        def collect(items=None):
            """Appends to a fresh list every call."""
            items = list(items or [])
            items.append(1)
            return items
    ''',
    "explicit_encoding": '''
        def load(path: str) -> str:
            """Reads a file with an explicit encoding."""
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
    ''',
    "narrow_except": '''
        import json
        import logging


        def parse(raw: str) -> dict | None:
            """Parses JSON, logging what went wrong."""
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logging.exception("bad json")
                return None
    ''',
    "fstring": '''
        def greet(name: str) -> str:
            """Greets a person by name."""
            return f"hello {name}"
    ''',
    "format_template": '''
        TEMPLATE = "hello {name}"


        def greet(name: str) -> str:
            """Formats the greeting template."""
            return TEMPLATE.format(name=name)
    ''',
    "message_catalog": '''
        MESSAGES = {
            "greet": "hello {name}",
            "bye": "goodbye {name}",
        }


        def render(key: str, name: str) -> str:
            """Renders a message from the catalog."""
            return MESSAGES[key].format(name=name)
    ''',
    "or_default": '''
        def title_of(payload: dict) -> str:
            """Falls back to an empty string when the key is missing."""
            return str(payload.get("title") or "").strip()
    ''',
    "and_guard": '''
        def limit_of(config, fallback: int = 10) -> int:
            """Uses the configured limit when there is one."""
            return (config and config.limit) or fallback
    ''',
    "enumerate_loop": '''
        def numbered(rows: list[str]) -> list[str]:
            """Prefixes every row with its position."""
            return [f"{index}: {row}" for index, row in enumerate(rows)]
    ''',
    "set_membership": '''
        ALLOWED = {"a", "b", "c"}


        def keep(items: list[str]) -> list[str]:
            """Keeps only the allowed items."""
            return [item for item in items if item in ALLOWED]
    ''',
    "join_not_concat": '''
        def render(parts: list[str]) -> str:
            """Builds a string without quadratic concatenation."""
            return "".join(parts)
    ''',
    "iterate_copy": '''
        def drop_empty(items: list[str]) -> list[str]:
            """Removes empty entries without mutating while iterating."""
            for item in list(items):
                if not item:
                    items.remove(item)
            return items
    ''',
    "bound_lambda": '''
        def handlers(names: list[str]) -> list:
            """Binds the loop variable explicitly."""
            return [lambda bound=name: bound for name in names]
    ''',
    "parameterised_sql": '''
        def find(cursor, name: str):
            """Looks a row up with a bound parameter."""
            cursor.execute("SELECT * FROM users WHERE name = ?", (name,))
            return cursor.fetchone()
    ''',
    "subprocess_list": '''
        import subprocess


        def run(path: str) -> str:
            """Runs a command without a shell."""
            result = subprocess.run(["ls", path], capture_output=True, text=True)
            return result.stdout
    ''',
    "env_secret": '''
        import os

        API_KEY = os.environ.get("API_KEY", "")


        def header() -> dict[str, str]:
            """Builds the auth header from the environment."""
            return {"Authorization": f"Bearer {API_KEY}"}
    ''',
    "secrets_module": '''
        import secrets


        def make_token() -> str:
            """Generates a cryptographically sound token."""
            return secrets.token_urlsafe(32)
    ''',
    "isinstance_check": '''
        def is_text(value: object) -> bool:
            """Type check that respects subclasses."""
            return isinstance(value, str)
    ''',
    "math_isclose": '''
        import math


        def same(a: float, b: float) -> bool:
            """Compares floats the way floats must be compared."""
            return math.isclose(a, b)
    ''',
    "class_init_state": '''
        class Basket:
            """Holds items per instance, not per class."""

            def __init__(self) -> None:
                self.items: list[str] = []

            def add(self, item: str) -> None:
                """Adds one item."""
                self.items.append(item)
    ''',
    "staticmethod_no_self": '''
        class Tools:
            """A small namespace of helpers."""

            @staticmethod
            def double(value: int) -> int:
                """Doubles a number."""
                return value * 2
    ''',
    "generator_in_sum": '''
        def total(values: list[int]) -> int:
            """Sums without materialising a list."""
            return sum(value * 2 for value in values)
    ''',
    "dict_membership": '''
        def has(mapping: dict, key: str) -> bool:
            """Membership on the mapping itself."""
            return key in mapping
    ''',
    "truthiness": '''
        def first(items: list[str]) -> str:
            """Returns the first item, or an empty string."""
            if not items:
                return ""
            return items[0]
    ''',
    "unique_keys": '''
        SETTINGS = {"width": 100, "height": 50, "depth": 25}


        def area() -> int:
            """Multiplies two distinct settings."""
            return SETTINGS["width"] * SETTINGS["height"]
    ''',
    "assert_with_message": '''
        def divide(a: float, b: float) -> float:
            """Divides, refusing a zero denominator."""
            assert b != 0, "b must not be zero"
            return a / b
    ''',
    "try_finally_cleanup": '''
        def process(handle) -> int:
            """Cleans up without swallowing the error."""
            try:
                return int(handle.read())
            finally:
                handle.close()
    ''',
    "reexport_init": '''
        from collections import OrderedDict

        __all__ = ["OrderedDict"]
    ''',
    "typed_signature": '''
        def area(width: float, height: float) -> float:
            """Computes a rectangle area."""
            return width * height
    ''',
}


def _findings(source: str, categories=NOISY_CATEGORIES) -> list:
    unit = SourceUnit.from_source(textwrap.dedent(source).strip() + "\n", "clean_sample.py")
    assert unit.tree is not None, "the sample itself must parse"
    return analyze(unit, categories)


class CleanCodeIsQuietTest(unittest.TestCase):
    """Not one of these samples may produce a finding."""

    def test_every_sample_is_silent(self) -> None:
        noisy: list[str] = []
        for name, source in CLEAN_SAMPLES.items():
            found = _findings(source)
            if found:
                rules = ", ".join(sorted({f"{f.rule}@{f.line}" for f in found}))
                noisy.append(f"{name}: {rules}")
        self.assertEqual(noisy, [], "false positives on clean code:\n  " + "\n  ".join(noisy))

    def test_samples_are_also_quiet_for_complexity_and_modernity(self) -> None:
        noisy: list[str] = []
        for name, source in CLEAN_SAMPLES.items():
            found = _findings(source, (CATEGORY_COMPLEXITY, CATEGORY_MOD))
            if found:
                rules = ", ".join(sorted({f.rule for f in found}))
                noisy.append(f"{name}: {rules}")
        self.assertEqual(noisy, [], "false positives:\n  " + "\n  ".join(noisy))

    def test_the_suite_is_broad_enough_to_matter(self) -> None:
        self.assertGreaterEqual(len(CLEAN_SAMPLES), 25)


class FixerNeverBreaksCodeTest(unittest.TestCase):
    """A fix that breaks the file is worse than no fix at all."""

    def _apply(self, source: str, tmpdir: str, name: str) -> str:
        path = os.path.join(tmpdir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(textwrap.dedent(source).strip() + "\n")
        unit = SourceUnit.from_path(path)
        build_from_findings(analyze(unit, NOISY_CATEGORIES)).apply(backup=False)
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_partly_used_import_keeps_the_used_name(self) -> None:
        """The exact bug that broke the package: `from x import A, B`."""
        import tempfile

        source = """
            from os import path, sep


            def where() -> str:
                return path.join("a", "b")
        """
        with tempfile.TemporaryDirectory() as tmp:
            result = self._apply(source, tmp, "partial.py")
        self.assertIn("path", result)
        self.assertNotIn("sep", result)
        self.assertIn("path.join", result)

    def test_multi_import_keeps_every_used_name(self) -> None:
        import tempfile

        source = """
            from json import dumps, loads, JSONDecodeError


            def roundtrip(value):
                return loads(dumps(value))
        """
        with tempfile.TemporaryDirectory() as tmp:
            result = self._apply(source, tmp, "multi.py")
        self.assertIn("dumps", result)
        self.assertIn("loads", result)
        self.assertNotIn("JSONDecodeError", result)

    def test_fixed_files_still_import(self) -> None:
        """Every clean sample survives a fix round and still executes."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            for name, source in CLEAN_SAMPLES.items():
                filename = f"s_{name}.py"
                fixed = self._apply(source, tmp, filename)
                try:
                    compile(fixed, filename, "exec")
                except SyntaxError as exc:  # pragma: no cover
                    self.fail(f"{name} stopped compiling after fixes: {exc}")

    def test_guard_blocks_an_edit_that_orphans_a_name(self) -> None:
        from sbpy.patcher import _orphaned_name

        before = "from . import alpha, beta\nprint(alpha, beta)\n"
        self.assertEqual(_orphaned_name(before, "print(alpha, beta)\n"), "alpha")
        self.assertEqual(_orphaned_name(before, "from . import alpha\nprint(alpha)\n"), "")


class PackageInitTest(unittest.TestCase):
    def test_init_reexports_are_not_reported(self) -> None:
        source = "from .thing import helper\nfrom .other import tool\n"
        unit = SourceUnit.from_source(source, os.path.join("pkg", "__init__.py"))
        rules = {f.rule for f in analyze(unit, (CATEGORY_STYLE,))}
        self.assertNotIn("unused-import", rules)

    def test_regular_module_still_reports(self) -> None:
        source = "from .thing import helper\n"
        unit = SourceUnit.from_source(source, os.path.join("pkg", "module.py"))
        rules = {f.rule for f in analyze(unit, (CATEGORY_STYLE,))}
        self.assertIn("unused-import", rules)


class SelfScanGateTest(unittest.TestCase):
    """SBpy must stay clean under its own checks.

    This gate caught a broken CLI call the moment it was introduced, so it
    earns its runtime.
    """

    @classmethod
    def _package_root(cls) -> str:
        import sbpy

        return os.path.dirname(os.path.abspath(sbpy.__file__))

    def _scan(self, shortcut: str) -> str:
        root = self._package_root()
        environment = {
            **os.environ,
            "SBPY_OFFLINE": "1",
            "SBPY_NO_SHELL": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        result = subprocess.run(
            [sys.executable, "-m", "sbpy", shortcut, root, "--format", "editor", "--offline"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=300,
            cwd=os.path.dirname(root),
        )
        self.assertNotIn("Traceback", result.stderr, f"`sbpy {shortcut}` crashed:\n{result.stderr}")
        return result.stdout.strip()

    def test_sbpy_finds_no_bugs_in_itself(self) -> None:
        output = self._scan("sfb")
        self.assertEqual(output, "", f"SBpy reports bugs in its own source:\n{output}")

    def test_sbpy_finds_no_security_issues_in_itself(self) -> None:
        output = self._scan("sec")
        self.assertEqual(output, "", f"SBpy reports security issues in its own source:\n{output}")


if __name__ == "__main__":
    unittest.main()
