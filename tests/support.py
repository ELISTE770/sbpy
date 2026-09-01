"""עזרים משותפים לבדיקות: סביבה מבודדת ומנוע Gemini מזויף."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from typing import Any

from sbpy import budget
from sbpy.config import Config, reset_config
from sbpy.gemini import GeminiResult


class FakeEngine:
    """מנוע Gemini מזויף - סופר קריאות ומחזיר תשובה קבועה."""

    def __init__(self, payload: dict[str, Any] | None = None, ok: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.payload = payload if payload is not None else {
            "title": "אבחנה מהמודל",
            "cause": "סיבה",
            "fix": "תיקון",
            "confidence": 0.9,
        }
        self.ok = ok

    def status(self) -> dict[str, Any]:
        return {"available": True, "reason": ""}

    @property
    def available(self) -> bool:
        return True

    def generate(self, prompt: str, **kwargs: Any) -> GeminiResult:
        self.calls.append({"prompt": prompt, **kwargs})
        if not self.ok:
            return GeminiResult(ok=False, error="fake-failure", model="fake", tier=kwargs.get("tier", ""))
        import json

        return GeminiResult(
            ok=True,
            text=json.dumps(self.payload, ensure_ascii=False),
            data=dict(self.payload),
            tokens=42,
            model="fake-model",
            tier=str(kwargs.get("tier", "")),
        )


class IsolatedConfigTest(unittest.TestCase):
    """כל בדיקה מקבלת בית נקי משלה, בלי לגעת ב-~/.sbpy האמיתי."""

    def setUp(self) -> None:
        self._saved_env = dict(os.environ)
        self.home = tempfile.mkdtemp(prefix="sbpy-test-")
        os.environ["SBPY_HOME"] = self.home
        os.environ["SBPY_OFFLINE"] = "1"
        os.environ["SBPY_LANG"] = "he"
        os.environ.pop("SBPY_DEBUG", None)
        self.config: Config = reset_config()
        import sbpy

        sbpy.reset_state()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved_env)
        reset_config()
        import sbpy

        sbpy.reset_state()
        shutil.rmtree(self.home, ignore_errors=True)

    def online_config(self, **overrides: Any) -> Config:
        """תצורה שמדמה חיבור זמין (בלי לפנות באמת לרשת)."""
        base = {"offline": False, "api_key": "test-key"}
        base.update(overrides)
        self.config = self.config.with_overrides(**base)
        return self.config
