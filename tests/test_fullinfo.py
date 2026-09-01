"""Unit tests for fullinfo module."""

from __future__ import annotations

import unittest
from sbpy.fullinfo import CATEGORIES, render_full_info
from sbpy import shell


class FullInfoTest(unittest.TestCase):
    def test_categories_defined(self) -> None:
        self.assertGreaterEqual(len(CATEGORIES), 6)
        cat_titles = [c["title"] for c in CATEGORIES]
        self.assertTrue(any("Bug Hunting" in t for t in cat_titles))
        self.assertTrue(any("Performance" in t for t in cat_titles))
        self.assertTrue(any("Documentation" in t for t in cat_titles))

    def test_render_full_info_executes(self) -> None:
        # Verify it executes cleanly without throwing exception
        render_full_info()

    def test_parse_at_line_fullinfo(self) -> None:
        for cmd in ("/FULLINFO", "/fullinfo", "/info", "/commands"):
            parsed = shell.parse_at_line(cmd)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed["kind"], "fullinfo")


if __name__ == "__main__":
    unittest.main()
