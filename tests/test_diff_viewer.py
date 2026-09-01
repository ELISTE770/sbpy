"""Unit tests for diff_viewer module."""

from __future__ import annotations

import unittest
from sbpy.diff_viewer import render_side_by_side


class DiffViewerTest(unittest.TestCase):
    def test_render_side_by_side_basic(self) -> None:
        original = ["def add(a, b):", "    return a - b"]
        updated = ["def add(a, b):", "    return a + b"]

        # Just verify it executes without error and prints formatted diff
        render_side_by_side("test.py", original, updated, width=100)


if __name__ == "__main__":
    unittest.main()
