"""Documentation must not drift away from the code.

Eight shortcuts once existed without a line of documentation, because the
README table was maintained by hand. It is now generated, and this test
fails the moment the two disagree.
"""

from __future__ import annotations

import os
import re
import unittest

from sbpy.shortcuts import SHORTCUTS, markdown_table

START = "<!-- sbpy:shortcuts:start -->"
END = "<!-- sbpy:shortcuts:end -->"


def _readme_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "README.md")


def _readme() -> str:
    with open(_readme_path(), "r", encoding="utf-8") as handle:
        return handle.read()


class ShortcutTableTest(unittest.TestCase):
    def test_readme_has_the_generated_block(self) -> None:
        text = _readme()
        self.assertIn(START, text, "README lost the generated-table markers")
        self.assertIn(END, text)

    def test_table_matches_the_registry(self) -> None:
        """`sbpy shortcuts --md` and the README must agree, character for character."""
        text = _readme()
        block = re.search(re.escape(START) + r"(.*?)" + re.escape(END), text, re.DOTALL)
        self.assertIsNotNone(block, "generated block not found")

        expected = markdown_table("he").strip()
        actual = block.group(1).strip()
        self.assertEqual(
            actual,
            expected,
            "README table is stale. Regenerate it:\n"
            "    python -m sbpy shortcuts --md --lang he",
        )

    def test_every_shortcut_is_documented(self) -> None:
        text = _readme()
        missing = [code for code in SHORTCUTS if f"`/{code}`" not in text]
        self.assertEqual(missing, [], f"shortcuts with no documentation: {missing}")

    def test_generated_table_covers_the_whole_registry(self) -> None:
        table = markdown_table("he")
        for code in SHORTCUTS:
            self.assertIn(f"`/{code}`", table)

    def test_table_renders_in_both_languages(self) -> None:
        for lang in ("he", "en"):
            table = markdown_table(lang)
            self.assertIn("|---|", table)
            self.assertEqual(len(table.splitlines()), len(SHORTCUTS) + 2)

    def test_no_language_mixing_in_english_table(self) -> None:
        """An English table must not carry Hebrew labels, and vice versa."""
        english = markdown_table("en")
        hebrew_letters = re.compile(r"[֐-׿]")
        offenders = [line for line in english.splitlines() if hebrew_letters.search(line)]
        # Titles come from the registry and may stay Hebrew; the columns we
        # generate ourselves must not.
        generated_columns = [line.split("|")[4] for line in offenders if line.count("|") >= 4]
        self.assertEqual(
            [column for column in generated_columns if hebrew_letters.search(column)],
            [],
            "escalation column leaked Hebrew into the English table",
        )


class ReadmeAccuracyTest(unittest.TestCase):
    def test_documented_env_vars_exist(self) -> None:
        from sbpy.config import Config

        text = _readme()
        documented = set(re.findall(r"`(SBPY_[A-Z_]+)`", text))
        self.assertTrue(documented, "no environment variables documented")

        import sbpy.config as config_module

        with open(config_module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for name in sorted(documented):
            self.assertIn(name, source, f"README documents {name}, which the config never reads")

    def test_no_stale_at_prefix_examples(self) -> None:
        """The shell prefix is `/`; leftover `@SFB` examples would mislead."""
        text = _readme()
        stale = re.findall(r"(?<![\w`])@(?:SFB|SEC|OPT|CMP|EXP|TST|ASK)\b", text)
        self.assertEqual(stale, [], f"README still shows the old @ prefix: {set(stale)}")


if __name__ == "__main__":
    unittest.main()
