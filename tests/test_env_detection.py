"""Unit tests for virtual environment and package manager detection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sbpy.suggestions import detect_package_installer, safe_install_argv


class EnvDetectionTest(unittest.TestCase):
    def test_poetry_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "poetry.lock").write_text("", encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                installer, cmd = detect_package_installer()
                self.assertEqual(installer, "poetry")
                self.assertEqual(cmd, ["poetry", "add"])

    def test_uv_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "uv.lock").write_text("", encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                installer, cmd = detect_package_installer()
                self.assertEqual(installer, "uv")
                self.assertEqual(cmd, ["uv", "add"])

    def test_pipenv_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "Pipfile").write_text("", encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                installer, cmd = detect_package_installer()
                self.assertEqual(installer, "pipenv")
                self.assertEqual(cmd, ["pipenv", "install"])

    def test_safe_install_argv_supports_managers(self) -> None:
        self.assertIsNotNone(safe_install_argv("pip install requests"))
        self.assertIsNotNone(safe_install_argv("poetry add httpx"))
        self.assertIsNotNone(safe_install_argv("uv add pydantic"))
        self.assertIsNotNone(safe_install_argv("pipenv install flask"))


if __name__ == "__main__":
    unittest.main()
