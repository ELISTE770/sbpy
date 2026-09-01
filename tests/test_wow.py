import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import sbpy
from sbpy.agent import _extract_failing_files_and_tracebacks, run_autonomous_agent, run_self_healing_tests
from sbpy.config import Config
from sbpy.scaffold import generate_scaffold
from sbpy.search import _extract_symbols_from_file, semantic_code_search
from sbpy.trace import CrashSnapshot, FrameSnapshot, get_latest_crash_snapshot, set_latest_crash_snapshot


class TestWowFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.config = Config(offline=True, color=False)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_extract_tracebacks(self):
        sample_tb = """
FAIL: test_add (test_calc.CalcTest.test_add)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "test_calc.py", line 15, in test_add
    self.assertEqual(add(2, 2), 4)
AssertionError: 5 != 4
"""
        extracted = _extract_failing_files_and_tracebacks(sample_tb)
        self.assertTrue(len(extracted) >= 1)
        self.assertEqual(extracted[0][0], "test_calc.py")

    def test_self_healing_runner_offline(self):
        res = run_self_healing_tests(
            test_cmd=["py", "-c", "import sys; sys.exit(1)"],
            max_iterations=1,
            root_dir=self.tmp_dir,
            config=self.config,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.error_summary, "Offline mode active")

    def test_extract_symbols_from_file(self):
        code = '''
"""Module docstring."""

class Calculator:
    """Class for math."""
    def multiply(self, a: int, b: int) -> int:
        """Multiplies two numbers."""
        return a * b

def divide(a: float, b: float) -> float:
    """Divides two numbers with error handling."""
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b
'''
        fpath = os.path.join(self.tmp_dir, "math_ops.py")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(code)

        symbols = _extract_symbols_from_file(fpath)
        self.assertEqual(len(symbols), 3)  # Calculator, Calculator.multiply, divide
        names = [s["name"] for s in symbols]
        self.assertIn("Calculator", names)
        self.assertIn("Calculator.multiply", names)
        self.assertIn("divide", names)

    def test_semantic_search_offline(self):
        code = '''
def handle_retry_backoff(attempt: int) -> float:
    """Calculates exponential backoff delay for network requests."""
    return 2 ** attempt
'''
        fpath = os.path.join(self.tmp_dir, "network.py")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(code)

        results = semantic_code_search("retry network delay", root_dir=self.tmp_dir, config=self.config)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0].symbol, "handle_retry_backoff")

    def test_scaffolding_offline(self):
        res = generate_scaffold("fastapi crud", root_dir=self.tmp_dir, config=self.config)
        self.assertFalse(res.files)
        self.assertEqual(res.summary, "Offline mode active")

    def test_scaffolding_mock_generation(self):
        cfg = Config(offline=False)
        mock_engine = MagicMock()
        mock_engine.generate.return_value = MagicMock(
            ok=True,
            text='{"src/user.py": "class User: pass", "tests/test_user.py": "def test_u(): pass"}',
        )
        with patch("sbpy.scaffold.get_engine", return_value=mock_engine):
            res = generate_scaffold("user model", root_dir=self.tmp_dir, apply=True, config=cfg)
            self.assertEqual(len(res.written_files), 2)
            self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, "src", "user.py")))
            self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, "tests", "test_user.py")))

    def test_trace_global_snapshot(self):
        snap = CrashSnapshot(
            exc_type="ValueError",
            exc_value="Invalid input",
            timeline=[FrameSnapshot("app.py", 10, "run", "x = 1/0", {"x": "0"})],
        )
        set_latest_crash_snapshot(snap)
        got = get_latest_crash_snapshot()
        self.assertIsNotNone(got)
        self.assertEqual(got.exc_type, "ValueError")

    def test_startup_exports(self):
        import sbpy
        self.assertTrue(hasattr(sbpy, "heal"))
        self.assertTrue(hasattr(sbpy, "agent"))
        self.assertTrue(hasattr(sbpy, "find"))
        self.assertTrue(hasattr(sbpy, "gen"))


if __name__ == "__main__":
    unittest.main()
