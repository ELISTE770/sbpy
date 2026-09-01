"""The contract every AI backend must honour.

SBpy now speaks to Gemini, Ollama and OpenAI/Anthropic-compatible APIs.
Without a written contract, adding a provider breaks the others quietly,
so these tests pin down what the engine promises regardless of who answers:

* a result object, never an exception;
* failure reported in ``error``, never raised;
* fallback down the backend list rather than a hard failure;
* stored API keys actually reaching the provider.
"""

from __future__ import annotations

import unittest

from sbpy.config import TIER_AUTO, TIER_COMMAND, TIER_PRO, Config
from sbpy.gemini import GeminiEngine, GeminiResult, classify_error, friendly_error
from tests.support import IsolatedConfigTest


class BackendKeyResolutionTest(IsolatedConfigTest):
    def engine(self, **overrides) -> GeminiEngine:
        return GeminiEngine(self.config.with_overrides(**overrides))

    def test_stored_key_reaches_the_backend(self) -> None:
        engine = self.engine(api_keys={"openai": "sk-stored"})
        self.assertEqual(engine.key_for("openai"), "sk-stored")

    def test_openai_key_serves_compatible_providers(self) -> None:
        engine = self.engine(api_keys={"openai": "sk-stored"})
        self.assertEqual(engine.key_for("groq"), "sk-stored")
        self.assertEqual(engine.key_for("deepseek"), "sk-stored")

    def test_claude_and_anthropic_are_the_same_provider(self) -> None:
        engine = self.engine(api_keys={"anthropic": "sk-ant"})
        self.assertEqual(engine.key_for("claude"), "sk-ant")

    def test_unknown_backend_has_no_key(self) -> None:
        engine = self.engine(api_keys={"openai": "sk"})
        self.assertEqual(engine.key_for("nonesuch"), "")

    def test_missing_key_is_empty_not_none(self) -> None:
        """Providers take a string; None would blow up inside the SDK."""
        engine = self.engine(api_keys={})
        self.assertIsInstance(engine.key_for("openai"), str)


class EngineContractTest(IsolatedConfigTest):
    """What every caller may rely on, whichever backend answers."""

    def test_offline_returns_a_result_not_an_exception(self) -> None:
        engine = GeminiEngine(self.config.with_overrides(offline=True))
        result = engine.generate("hello")
        self.assertIsInstance(result, GeminiResult)
        self.assertFalse(result.ok)
        self.assertTrue(result.error)

    def test_missing_key_is_reported_not_raised(self) -> None:
        engine = GeminiEngine(self.config.with_overrides(offline=False, api_key=None, api_keys={}))
        result = engine.generate("hello")
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error, str)

    def test_result_is_falsy_when_it_failed(self) -> None:
        self.assertFalse(GeminiResult(ok=False))
        self.assertTrue(GeminiResult(ok=True))

    def test_status_never_raises_for_any_backend(self) -> None:
        for backend in ("gemini", "ollama", "openai", "groq", "anthropic", "claude", "nonsense"):
            engine = GeminiEngine(self.config.with_overrides(backend=backend, offline=False))
            status = engine.status()
            self.assertIn("available", status)
            self.assertIsInstance(status["available"], bool)

    def test_backend_list_is_parsed(self) -> None:
        engine = GeminiEngine(
            self.config.with_overrides(backend="ollama, openai", offline=False, api_key="k")
        )
        self.assertTrue(engine.status()["available"])

    def test_every_tier_resolves_to_a_model(self) -> None:
        config = Config()
        for tier in (TIER_AUTO, TIER_COMMAND, TIER_PRO):
            self.assertTrue(config.model_for(tier))


class ErrorClassificationContractTest(unittest.TestCase):
    """Failures must be classified the same way whoever produced them."""

    def test_quota_from_any_provider(self) -> None:
        for message in (
            "Error code: 429 - quota exceeded",
            "RESOURCE_EXHAUSTED",
            "rate limit reached for gpt-4o-mini",
            "too_many_requests",
        ):
            self.assertEqual(classify_error(RuntimeError(message)), "quota", message)

    def test_unavailable_from_any_provider(self) -> None:
        for message in ("404 model not found", "permission_denied", "403 forbidden"):
            self.assertEqual(classify_error(RuntimeError(message)), "unavailable", message)

    def test_network_failures(self) -> None:
        for message in ("read timeout", "connection refused", "SSL handshake failed"):
            self.assertEqual(classify_error(RuntimeError(message)), "network", message)

    def test_messages_stay_short_and_actionable(self) -> None:
        long_error = RuntimeError("x" * 5000)
        for kind in ("quota", "unavailable", "network", "other"):
            message = friendly_error(long_error, kind, "some-model")
            self.assertLess(len(message), 300, kind)
            self.assertTrue(message.strip())


class FallbackContractTest(IsolatedConfigTest):
    def test_pro_falls_back_when_the_tier_is_blocked(self) -> None:
        """A free-tier key cannot use pro; the answer must still arrive."""
        calls: list[str] = []

        engine = GeminiEngine(self.config.with_overrides(offline=False, api_key="k"))

        def fake_client():
            class Interactions:
                @staticmethod
                def create(**payload):
                    model = payload["model"]
                    calls.append(model)
                    if model == engine.config.model_pro:
                        raise RuntimeError("Error code: 429 - quota exceeded, limit: 0")

                    class Interaction:
                        output_text = "answer"
                        usage = None

                    return Interaction()

            class Client:
                interactions = Interactions()

            return Client()

        engine._get_client = fake_client  # type: ignore[assignment]
        result = engine.generate("hi", tier=TIER_PRO)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.downgraded_from, engine.config.model_pro)
        self.assertEqual(calls, [engine.config.model_pro, engine.config.model_command])

    def test_fallback_can_be_disabled(self) -> None:
        engine = GeminiEngine(
            self.config.with_overrides(offline=False, api_key="k", pro_fallback=False)
        )

        def fake_client():
            class Interactions:
                @staticmethod
                def create(**payload):
                    raise RuntimeError("Error code: 429 - quota exceeded")

            class Client:
                interactions = Interactions()

            return Client()

        engine._get_client = fake_client  # type: ignore[assignment]
        result = engine.generate("hi", tier=TIER_PRO)
        self.assertFalse(result.ok)
        self.assertIn("מכסה", result.error + " ")


if __name__ == "__main__":
    unittest.main()
