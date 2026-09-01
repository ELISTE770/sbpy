"""Unit tests for AI Custom Instructions."""

from __future__ import annotations

import unittest
from sbpy.config import configure, get_config, reset_config
from sbpy.gemini import GeminiEngine


class CustomInstructionsTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_config()

    def tearDown(self) -> None:
        reset_config()

    def test_custom_instructions_config(self) -> None:
        configure(custom_instructions="Always follow PEP 8 and write docstrings")
        config = get_config()
        self.assertEqual(config.custom_instructions, "Always follow PEP 8 and write docstrings")

    def test_custom_instructions_injected_offline(self) -> None:
        configure(offline=True, custom_instructions="Use snake_case always")
        config = get_config()
        client = GeminiEngine(config)
        res = client.generate("hello", system="System message")
        # Offline mode returns False, but config and client are initialized properly
        self.assertFalse(res.ok)
        self.assertEqual(config.custom_instructions, "Use snake_case always")


if __name__ == "__main__":
    unittest.main()
