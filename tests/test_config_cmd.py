"""בדיקות עבור ניהול הגדרות ומפתחות API (sbpy config / setup)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from sbpy import cli
from sbpy.config import (
    Config,
    load_stored_config,
    save_stored_config,
    set_config_value,
    test_ai_connection,
)
from tests.support import IsolatedConfigTest


class ConfigCmdTest(IsolatedConfigTest):
    def test_save_and_load_stored_config(self) -> None:
        home = Path(self.home)
        data = {"language": "en", "backend": "openai", "timeout": 45.0}
        save_stored_config(data, home=home)

        loaded = load_stored_config(home=home)
        self.assertEqual(loaded.get("language"), "en")
        self.assertEqual(loaded.get("backend"), "openai")
        self.assertEqual(loaded.get("timeout"), 45.0)

    def test_set_config_value(self) -> None:
        home = Path(self.home)
        set_config_value("backend", "ollama", home=home)
        loaded = load_stored_config(home=home)
        self.assertEqual(loaded.get("backend"), "ollama")

    def test_cli_config_list(self) -> None:
        self.assertEqual(cli.main(["config"]), cli.EXIT_OK)

    def test_cli_config_set_and_get(self) -> None:
        self.assertEqual(cli.main(["config", "set", "language", "en"]), cli.EXIT_OK)
        self.assertEqual(cli.main(["config", "get", "language"]), cli.EXIT_OK)

    def test_cli_config_set_key(self) -> None:
        self.assertEqual(cli.main(["config", "set-key", "my-secret-test-api-key-12345"]), cli.EXIT_OK)
        loaded = load_stored_config(home=Path(self.home))
        self.assertEqual(loaded.get("api_key"), "my-secret-test-api-key-12345")

    def test_test_ai_connection_in_offline(self) -> None:
        cfg = Config(offline=True)
        res = test_ai_connection(cfg)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error"), "offline")


if __name__ == "__main__":
    unittest.main()
