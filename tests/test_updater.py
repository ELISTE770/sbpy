"""בדיקות יחידה עבור מנגנון עדכוני GitHub של SBpy."""

from __future__ import annotations

import pathlib
import unittest
from unittest.mock import MagicMock, patch

from sbpy.config import Config
from sbpy import updater


class UpdaterTest(unittest.TestCase):
    def test_parse_version_tuple(self) -> None:
        self.assertEqual(updater._parse_version_tuple("0.1.0"), (0, 1, 0))
        self.assertEqual(updater._parse_version_tuple("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater._parse_version_tuple("10.0.1b"), (10, 0, 1))
        self.assertGreater(updater._parse_version_tuple("0.2.0"), updater._parse_version_tuple("0.1.9"))

    @patch("sbpy.updater.fetch_remote_version")
    def test_check_for_updates_newer_available(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = "9.9.9"
        cfg = Config(home=pathlib.Path("tmp_test_sbpy_updater"))
        res = updater.check_for_updates(config=cfg, force=True)
        self.assertTrue(res.get("update_available"))
        self.assertEqual(res.get("latest_version"), "9.9.9")

    @patch("sbpy.updater.fetch_remote_version")
    def test_check_for_updates_already_latest(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = "0.0.1"
        cfg = Config(home=pathlib.Path("tmp_test_sbpy_updater"))
        res = updater.check_for_updates(config=cfg, force=True)
        self.assertFalse(res.get("update_available"))

    @patch("sbpy.updater.read_cached_update")
    def test_get_update_notification(self, mock_read: MagicMock) -> None:
        mock_read.return_value = {
            "update_available": True,
            "current_version": "0.1.0",
            "latest_version": "0.2.0",
            "install_cmd": "pip install -U sbpy",
        }
        cfg_en = Config(language="en")
        msg_en = updater.get_update_notification(cfg_en)
        self.assertIsNotNone(msg_en)
        self.assertIn("update available", msg_en.lower())
        self.assertIn("0.2.0", msg_en)

        cfg_he = Config(language="he")
        msg_he = updater.get_update_notification(cfg_he)
        self.assertIsNotNone(msg_he)
        self.assertIn("עדכון חדש", msg_he)

    @patch("sbpy.updater.read_cached_update")
    def test_suggestions_include_update_option(self, mock_read: MagicMock) -> None:
        from sbpy.results import Report
        from sbpy.suggestions import register_options_from_report, execute_option

        mock_read.return_value = {
            "update_available": True,
            "current_version": "0.1.0",
            "latest_version": "0.2.0",
            "install_cmd": "pip install -U git+https://github.com/eliste770-cmyk/sbpy",
        }
        report = Report(exc_type="ValueError", exc_message="test")
        options = register_options_from_report(report)
        update_opt = next((o for o in options if o.command == "/UPDATE"), None)
        self.assertIsNotNone(update_opt)
        self.assertIn("v0.2.0", update_opt.title)

        with patch("sbpy.updater.run_upgrade", return_value=0) as mock_upgrade:
            res = execute_option(update_opt.index)
            self.assertEqual(res, 0)
            mock_upgrade.assert_called_once()


if __name__ == "__main__":
    unittest.main()
