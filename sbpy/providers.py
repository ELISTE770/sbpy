"""תמיכה בריבוי ספקי ענן ושרשרת Fallbacks (Gemini, OpenAI, Anthropic, Ollama).

מאפשר להגדיר שרשרת ספקים (למשל SBPY_BACKEND="gemini,openai,ollama") כך שאם
ספק אחד חווה עומס או חסימת מכסה (Quota 429), המערכת עוברת אוטומטית ובאופן
שקוף לספק הבא בשרשרת.
מימוש אפס-תלויות מבוסס urllib.request של ה-stdlib.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any



def _parse_json_response(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\n|\n```$", "", candidate, flags=re.MULTILINE).strip()
    try:
        val = json.loads(candidate)
        return val if isinstance(val, dict) else {"result": val}
    except ValueError:  # sbpy: ignore=silent-except
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            val = json.loads(candidate[start : end + 1])
            return val if isinstance(val, dict) else {"result": val}
        except ValueError:
            return None
    return None


def call_openai_compatible(
    *,
    prompt: str,
    system: str = "",
    schema: dict[str, Any] | None = None,
    api_key: str = "",
    url: str = "",
    model: str = "gpt-4o-mini",
    timeout: float = 60.0,
    provider: str = "openai",
) -> dict[str, Any]:
    """פנייה לספק תואם OpenAI (OpenAI, Groq, DeepSeek, Together, LocalAI, vLLM)."""
    if not url:
        if provider == "groq" or "llama" in model.lower():
            url = "https://api.groq.com/openai/v1/chat/completions"
        elif provider == "deepseek" or "deepseek" in model.lower():
            url = "https://api.deepseek.com/chat/completions"
        else:
            url = "https://api.openai.com/v1/chat/completions"

    api_key = (
        api_key
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("GROQ_API_KEY", "")
        or os.environ.get("DEEPSEEK_API_KEY", "")
        or os.environ.get("SBPY_API_KEY", "")
    )
    if not api_key and "localhost" not in url and "127.0.0.1" not in url:
        return {"ok": False, "error": "missing-api-key"}

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if schema:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8", errors="replace"))

        choice = resp_data.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "") or ""
        tokens = int(resp_data.get("usage", {}).get("total_tokens", 0))

        data = None
        if schema:
            data = _parse_json_response(text)

        return {"ok": True, "text": text, "data": data, "tokens": tokens, "model": model}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "model": model}


def call_anthropic(
    *,
    prompt: str,
    system: str = "",
    schema: dict[str, Any] | None = None,
    api_key: str = "",
    model: str = "claude-3-5-haiku-20241022",
    timeout: float = 60.0,
) -> dict[str, Any]:
    """פנייה ל-Anthropic Claude API."""
    api_key = (
        api_key
        or os.environ.get("ANTHROPIC_API_KEY", "")
        or os.environ.get("CLAUDE_API_KEY", "")
        or os.environ.get("SBPY_API_KEY", "")
    )
    if not api_key:
        return {"ok": False, "error": "missing-api-key"}

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data_bytes,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8", errors="replace"))

        contents = resp_data.get("content", [])
        text = "".join(c.get("text", "") for c in contents if c.get("type") == "text")
        tokens = int(
            resp_data.get("usage", {}).get("input_tokens", 0)
            + resp_data.get("usage", {}).get("output_tokens", 0)
        )

        data = None
        if schema:
            data = _parse_json_response(text)

        return {"ok": True, "text": text, "data": data, "tokens": tokens, "model": model}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "model": model}
