"""בדיקות עבור גרף הקריאות הפרויקטלי ואיתור קוד מת."""

from __future__ import annotations

import os
import unittest

from sbpy.graph import build_project_graph, find_dead_code
from tests.support import IsolatedConfigTest


class ProjectGraphTest(IsolatedConfigTest):
    def test_dead_code_detection(self) -> None:
        # ניצור שני קבצים: main.py שמשתמש ב-used_func, ו-utils.py שיש בו used_func וגם dead_function
        main_py = os.path.join(self.home, "main.py")
        with open(main_py, "w", encoding="utf-8") as handle:
            handle.write("from utils import used_func\nused_func()\n")

        utils_py = os.path.join(self.home, "utils.py")
        with open(utils_py, "w", encoding="utf-8") as handle:
            handle.write(
                "def used_func():\n    return 1\n\n"
                "def dead_function():\n    return 2\n\n"
                "class DeadClass:\n    pass\n"
            )

        graph = build_project_graph(self.home)
        self.assertIn("used_func", graph.definitions)
        self.assertIn("dead_function", graph.definitions)
        self.assertIn("DeadClass", graph.definitions)

        findings = find_dead_code(self.home, graph=graph)
        dead_names = [f.message for f in findings]
        
        self.assertTrue(any("dead_function" in msg for msg in dead_names))
        self.assertTrue(any("DeadClass" in msg for msg in dead_names))
        self.assertFalse(any("used_func" in msg for msg in dead_names))


if __name__ == "__main__":
    unittest.main()
