"""עטיפה דקה סביב Gemini Interactions API.

עקרונות:
* יבוא עצל - אם ``google-genai`` לא מותקן, שאר SBpy עובד רגיל.
* לעולם לא זורק שגיאה לקוד של המשתמש; מחזיר ``GeminiResult(ok=False)``.
* ברירת המחדל היא ``store=False`` כדי לא לשמור את הקוד בשרת.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from .config import TIER_AUTO, TIER_COMMAND, TIER_PRO, Config, get_config

_FENCE = re.compile(r"^\s*```(?:json|JSON)?\s*|\s*```\s*$")


@dataclass
class GeminiResult:
    ok: bool = False
    text: str = ""
    data: dict[str, Any] | None = None
    tokens: int = 0
    model: str = ""
    tier: str = ""
    error: str = ""
    elapsed_ms: int = 0
    downgraded_from: str = ""
    """אם המודל המבוקש לא היה זמין וירדנו דרגה - שמו נשמר כאן."""

    def __bool__(self) -> bool:
        return self.ok


def build_ssl_context(mode: str = "auto") -> Any:
    """בונה הקשר TLS שסומך על מאגר התעודות של מערכת ההפעלה.

    ה-SDK משתמש ב-httpx, ש-מאמת מול ``certifi`` בלבד. במחשבים שמאחורי
    פרוקסי או תוכנת סינון שמפענחת TLS, התעודה של המסנן קיימת רק במאגר
    של Windows - ובלי זה כל קריאה נכשלת ב-CERTIFICATE_VERIFY_FAILED.
    """
    mode = (mode or "auto").strip().lower()
    if mode == "certifi":
        return None
    if mode == "auto" and os.name != "nt":
        return None
    try:
        import ssl

        return ssl.create_default_context()
    except Exception:  # pragma: no cover
        return None


QUOTA_MARKERS = ("429", "quota", "rate limit", "resource_exhausted", "too_many_requests")
UNAVAILABLE_MARKERS = ("404", "not found", "not supported", "permission_denied", "403")


def classify_error(exc: Exception) -> str:
    """ממיין כשל ל-quota / unavailable / network / other."""
    text = f"{type(exc).__name__} {exc}".lower()
    if any(marker in text for marker in QUOTA_MARKERS):
        return "quota"
    if any(marker in text for marker in UNAVAILABLE_MARKERS):
        return "unavailable"
    if "timeout" in text or "connection" in text or "ssl" in text:
        return "network"
    return "other"


def friendly_error(exc: Exception, kind: str, model: str) -> str:
    """הודעת שגיאה שאפשר לעשות איתה משהו, במקום JSON של 400 תווים."""
    if kind == "quota":
        return f"מכסה מוצתה עבור {model} - בדוק את התוכנית שלך או נסה שוב מאוחר יותר"
    if kind == "unavailable":
        return f"המודל {model} לא זמין למפתח הזה"
    if kind == "network":
        return f"בעיית רשת: {type(exc).__name__}"
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def sdk_available() -> bool:
    try:
        import google.genai  # noqa: F401
    except Exception:
        return False
    return True


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text)
    return text.strip()


def parse_json(text: str) -> dict[str, Any] | None:
    """מפענח JSON גם אם המודל עטף אותו בגדר markdown או הוסיף טקסט."""
    if not text:
        return None
    candidate = _strip_fence(text)
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else {"result": value}
    except ValueError:  # sbpy: ignore=silent-except
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(candidate[start : end + 1])
            return value if isinstance(value, dict) else {"result": value}
        except ValueError:
            return None
    return None


def _extract_tokens(interaction: Any) -> int:
    usage = getattr(interaction, "usage", None)
    if usage is None:
        return 0
    for attribute in ("total_tokens", "total_token_count", "totalTokens"):
        value = getattr(usage, attribute, None)
        if isinstance(value, int):
            return value
    if isinstance(usage, dict):
        for key in ("total_tokens", "total_token_count"):
            value = usage.get(key)
            if isinstance(value, int):
                return value
    return 0


class GeminiEngine:
    """נקודת הכניסה היחידה של SBpy אל הרשת."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self._client: Any = None
        self._error: str = ""

    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """מצב הזמינות - בלי ליצור חיבור."""
        if not self.config.enabled:
            return {"available": False, "reason": "disabled"}
        if self.config.offline:
            return {"available": False, "reason": "offline"}
        backends = [b.strip().lower() for b in self.config.backend.split(",") if b.strip()]
        if any(b in ("ollama", "openai", "groq", "deepseek", "anthropic", "claude") for b in backends):
            return {"available": True, "reason": "", "backend": self.config.backend}
        if not sdk_available():
            return {"available": False, "reason": "no-sdk", "fix": "pip install -U google-genai"}
        if not self.config.active_api_key:
            return {"available": False, "reason": "no-api-key", "fix": "set GEMINI_API_KEY"}
        return {"available": True, "reason": "", "backend": "gemini"}

    @property
    def available(self) -> bool:
        return bool(self.status()["available"])

    def key_for(self, backend: str) -> str:
        """The API key for one backend.

        Keys saved with `sbpy config set-key <provider>` live in
        ``config.api_keys``; without this they were stored and never read.
        """
        aliases = {
            "openai": ("openai",),
            "groq": ("groq", "openai"),
            "deepseek": ("deepseek", "openai"),
            "anthropic": ("anthropic", "claude"),
            "claude": ("claude", "anthropic"),
            "gemini": ("gemini", "google"),
        }
        for name in aliases.get(backend, (backend,)):
            value = (self.config.api_keys or {}).get(name)
            if value:
                return str(value).strip()
        return ""

    def _http_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"timeout": int(self.config.timeout * 1000)}
        context = build_ssl_context(self.config.ssl_trust)
        if context is not None:
            options["client_args"] = {"verify": context}
        return options

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from google import genai  # יבוא עצל בכוונה

        kwargs: dict[str, Any] = {"api_key": self.config.active_api_key}
        try:
            self._client = genai.Client(**kwargs, http_options=self._http_options())
        except TypeError:
            # גרסאות SDK שלא מכירות http_options / client_args
            self._client = genai.Client(**kwargs)
        return self._client

    # ------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        schema: dict[str, Any] | None = None,
        model: str = "",
        tier: str = TIER_AUTO,
        temperature: float = 0.2,
        thinking_level: str = "",
        stream: bool = False,
        on_text: Callable[[str], None] | None = None,
        _retrying: bool = False,
    ) -> GeminiResult:
        """פנייה לספק AI עם תמיכה בריבוי ספקים ו-Fallback אוטומטי."""
        status = self.status()
        if not status["available"]:
            return GeminiResult(ok=False, error=str(status["reason"]), tier=tier)

        user_instructions = (self.config.custom_instructions or "").strip()
        if user_instructions:
            if system:
                system = f"{system}\n\n[User Custom Instructions]:\n{user_instructions}"
            else:
                system = f"[User Custom Instructions]:\n{user_instructions}"

        model = model or self.config.model_for(tier)
        started = time.perf_counter()
        backends = [b.strip().lower() for b in self.config.backend.split(",") if b.strip()]
        if not backends:
            backends = ["gemini"]

        last_error = "all-providers-failed"

        from .spinner import Spinner

        with Spinner(f"AI Analyzing ({model})..."):
            for b in backends:
                if b == "ollama":
                    res = self._generate_ollama(
                        prompt,
                        system=system,
                        schema=schema,
                        model=model if model and "gemini" not in model else "",
                        tier=tier,
                        stream=stream,
                        on_text=on_text,
                        started=started,
                    )
                    if res.ok:
                        return res
                    last_error = res.error
                elif b in ("openai", "groq", "deepseek"):
                    from .providers import call_openai_compatible

                    ret = call_openai_compatible(
                        prompt=prompt,
                        system=system,
                        schema=schema,
                        api_key=self.key_for(b),
                        model=model if model and "gemini" not in model else "gpt-4o-mini",
                        timeout=self.config.timeout,
                    )
                    if ret.get("ok"):
                        return GeminiResult(
                            ok=True,
                            text=ret.get("text", ""),
                            data=ret.get("data"),
                            tokens=ret.get("tokens", 0),
                            model=ret.get("model", b),
                            tier=tier,
                            elapsed_ms=int((time.perf_counter() - started) * 1000),
                        )
                    last_error = ret.get("error", "provider-failed")
                elif b in ("anthropic", "claude"):
                    from .providers import call_anthropic

                    ret = call_anthropic(
                        prompt=prompt,
                        system=system,
                        api_key=self.key_for(b),
                        model=model if model and "gemini" not in model else "claude-3-5-haiku-20241022",
                        timeout=self.config.timeout,
                    )
                    if ret.get("ok"):
                        return GeminiResult(
                            ok=True,
                            text=ret.get("text", ""),
                            tokens=ret.get("tokens", 0),
                            model=ret.get("model", b),
                            tier=tier,
                            elapsed_ms=int((time.perf_counter() - started) * 1000),
                        )
                    last_error = ret.get("error", "provider-failed")
                elif b == "gemini":
                    payload: dict[str, Any] = {
                        "model": model,
                        "input": prompt,
                        "store": self.config.store,
                        "generation_config": {
                            "temperature": temperature,
                            "thinking_level": thinking_level or self.config.thinking_level,
                        },
                    }
                    if system:
                        payload["system_instruction"] = system
                    if schema:
                        payload["response_format"] = {
                            "type": "text",
                            "mime_type": "application/json",
                            "schema": schema,
                        }

                    if stream and on_text is not None and not schema:
                        return self._generate_streaming(payload, model, tier, on_text, started)

                    try:
                        client = self._get_client()
                        interaction = client.interactions.create(**payload)
                        text = getattr(interaction, "output_text", "") or ""
                        result = GeminiResult(
                            ok=True,
                            text=text,
                            tokens=_extract_tokens(interaction),
                            model=model,
                            tier=tier,
                            elapsed_ms=int((time.perf_counter() - started) * 1000),
                        )
                        if schema:
                            result.data = parse_json(text)
                            if result.data is None:
                                result.ok = False
                                result.error = "invalid-json"
                        return result
                    except Exception as exc:
                        failure = classify_error(exc)
                        if (
                            failure in {"quota", "unavailable"}
                            and tier == TIER_PRO
                            and self.config.pro_fallback
                            and not _retrying
                        ):
                            fallback = self.generate(
                                prompt,
                                system=system,
                                schema=schema,
                                tier=TIER_COMMAND,
                                temperature=temperature,
                                thinking_level=thinking_level,
                                _retrying=True,
                            )
                            if fallback.ok:
                                fallback.downgraded_from = model
                            return fallback
                        last_error = friendly_error(exc, failure, model)

        return GeminiResult(ok=False, error=last_error, tier=tier)

    def _generate_ollama(
        self,
        prompt: str,
        *,
        system: str = "",
        schema: dict[str, Any] | None = None,
        model: str = "",
        tier: str = TIER_AUTO,
        stream: bool = False,
        on_text: Callable[[str], None] | None = None,
        started: float,
    ) -> GeminiResult:
        """פנייה ל-Ollama API המקומי דרך urllib (ללא תלויות חיצוניות)."""
        import urllib.error
        import urllib.request

        url = f"{self.config.ollama_url.rstrip('/')}/api/generate"
        model_name = model or self.config.ollama_model
        req_body: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            req_body["system"] = system
        if schema:
            req_body["format"] = "json"

        try:
            data_bytes = json.dumps(req_body).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8", errors="replace"))

            output_text = str(resp_data.get("response") or "")
            if stream and on_text:
                on_text(output_text)

            prompt_eval = int(resp_data.get("prompt_eval_count") or 0)
            eval_count = int(resp_data.get("eval_count") or 0)
            tokens = prompt_eval + eval_count

            res = GeminiResult(
                ok=True,
                text=output_text,
                tokens=tokens,
                model=model_name,
                tier=tier,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            if schema:
                res.data = parse_json(output_text)
                if res.data is None:
                    res.ok = False
                    res.error = "invalid-json"
            return res
        except Exception as exc:
            return GeminiResult(
                ok=False,
                error=f"Ollama error: {exc}",
                model=model_name,
                tier=tier,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

    def _generate_streaming(
        self,
        payload: dict[str, Any],
        model: str,
        tier: str,
        on_text: Callable[[str], None],
        started: float,
    ) -> GeminiResult:
        """זרימה - התשובה מוצגת תוך כדי במקום אחרי 20 שניות של שקט."""
        chunks: list[str] = []
        tokens = 0
        try:
            client = self._get_client()
            for event in client.interactions.create(**payload, stream=True):
                kind = getattr(event, "event_type", "")
                if kind == "step.delta":
                    delta = getattr(event, "delta", None)
                    if getattr(delta, "type", "") == "text":
                        text = getattr(delta, "text", "") or ""
                        if text:
                            chunks.append(text)
                            on_text(text)
                elif kind == "interaction.completed":
                    tokens = _extract_tokens(getattr(event, "interaction", None))
        except Exception as exc:
            return GeminiResult(
                ok=False,
                text="".join(chunks),
                error=f"{type(exc).__name__}: {exc}",
                model=model,
                tier=tier,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

        return GeminiResult(
            ok=True,
            text="".join(chunks),
            tokens=tokens,
            model=model,
            tier=tier,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )


_engine: GeminiEngine | None = None


def get_engine(config: Config | None = None) -> GeminiEngine:
    global _engine
    if _engine is None or config is not None:
        _engine = GeminiEngine(config)
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None
