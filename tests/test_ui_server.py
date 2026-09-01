"""Unit tests for ui_server module."""

from __future__ import annotations

import unittest
from sbpy.ui_server import DASHBOARD_HTML


class UIServerTest(unittest.TestCase):
    def test_dashboard_html_contains_components(self) -> None:
        self.assertIn("SBpy Live Dashboard", DASHBOARD_HTML)
        self.assertIn("Project Health Score", DASHBOARD_HTML)
        self.assertIn("Token Usage & Budget", DASHBOARD_HTML)
        self.assertIn("/api/status", DASHBOARD_HTML)
        self.assertIn("/assets/icon.jpg", DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
