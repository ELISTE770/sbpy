"""בדיקות עבור הסקת טיפוסים מזמן ריצה (sbpy/infer.py)."""

from __future__ import annotations

import os
import unittest

from sbpy.infer import TypeCollector, generate_type_signatures
from tests.support import IsolatedConfigTest


class InferTest(IsolatedConfigTest):
    def test_collects_runtime_types(self) -> None:
        collector = TypeCollector(target_dir=self.home)
        target_file = os.path.join(self.home, "math_ops.py")

        with open(target_file, "w", encoding="utf-8") as handle:
            handle.write("""
def add(a, b):
    return a + b

def greet(name, times):
    return [name] * times
""")

        import sys
        sys.path.insert(0, self.home)
        import math_ops

        with collector:
            math_ops.add(1, 2)
            math_ops.add(5, 10)
            math_ops.greet("hello", 3)

        summary = collector.summary()
        self.assertIn(target_file, summary)
        
        funcs = summary[target_file]
        self.assertIn("add", funcs)
        self.assertEqual(funcs["add"]["args"]["a"], "int")
        self.assertEqual(funcs["add"]["args"]["b"], "int")
        self.assertEqual(funcs["add"]["return"], "int")

        self.assertIn("greet", funcs)
        self.assertEqual(funcs["greet"]["args"]["name"], "str")
        self.assertEqual(funcs["greet"]["args"]["times"], "int")
        self.assertIn("list", funcs["greet"]["return"])

        sigs = generate_type_signatures(summary)
        self.assertIn(target_file, sigs)
        self.assertTrue(any("def add(a: int, b: int) -> int:" in s for s in sigs[target_file]))


if __name__ == "__main__":
    unittest.main()
