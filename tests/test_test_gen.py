"""Unit tests for test_gen module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sbpy.test_gen import analyze_source_file, generate_unit_tests


class TestGenTest(unittest.TestCase):
    def test_analyze_and_generate_tests(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("def calculate(a, b):\n    return a + b\n\nclass Worker:\n    def run(self):\n        pass\n")
            temp_path = f.name

        try:
            funcs, classes = analyze_source_file(temp_path)
            self.assertEqual(len(funcs), 1)
            self.assertEqual(funcs[0].name, "calculate")
            self.assertEqual(len(classes), 1)
            self.assertEqual(classes[0].name, "Worker")

            test_code = generate_unit_tests(temp_path)
            self.assertIn("test_calculate_basic", test_code)
            self.assertIn("test_calculate_edge_cases", test_code)
            self.assertIn("test_worker_instantiation", test_code)
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
