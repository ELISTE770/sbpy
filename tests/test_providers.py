"""בדיקות עבור ספקי AI שונים ושרשרת Fallback."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sbpy.config import Config
from sbpy.gemini import GeminiEngine
from sbpy.providers import call_anthropic, call_openai_compatible
from tests.support import IsolatedConfigTest


class ProvidersTest(IsolatedConfigTest):
    def test_missing_api_key_returns_error(self) -> None:
        ret_openai = call_openai_compatible(prompt="test", api_key="")
        self.assertFalse(ret_openai.get("ok"))
        self.assertEqual(ret_openai.get("error"), "missing-api-key")

        ret_anthropic = call_anthropic(prompt="test", api_key="")
        self.assertFalse(ret_anthropic.get("ok"))
        self.assertEqual(ret_anthropic.get("error"), "missing-api-key")

    def test_engine_fallback_chain(self) -> None:
        cfg = Config(backend="openai,ollama", offline=False)
        engine = GeminiEngine(cfg)
        status = engine.status()
        self.assertTrue(status.get("available"))

        # נבדוק שפנייה עם שרשרת Fallback מנסה את הספקים
        with patch("sbpy.providers.call_openai_compatible", return_value={"ok": False, "error": "quota-exceeded"}):
            with patch.object(engine, "_generate_ollama") as mock_ollama:
                from sbpy.gemini import GeminiResult
                mock_ollama.return_value = GeminiResult(ok=True, text="Ollama answer", tokens=15, model="llama3.2")
                
                res = engine.generate("Hello test")
                self.assertTrue(res.ok)
                self.assertEqual(res.text, "Ollama answer")


if __name__ == "__main__":
    unittest.main()
