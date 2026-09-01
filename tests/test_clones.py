"""בדיקות עבור איתור קוד משוכפל (sbpy/clones.py)."""

from __future__ import annotations

import os
import unittest

from sbpy.clones import find_code_clones, scan_clones
from tests.support import IsolatedConfigTest


class ClonesTest(IsolatedConfigTest):
    def test_detects_structural_clones(self) -> None:
        file_a = os.path.join(self.home, "service_a.py")
        file_b = os.path.join(self.home, "service_b.py")

        # פונקציות זהות מבנית אך עם שמות משתנים שונים
        with open(file_a, "w", encoding="utf-8") as handle:
            handle.write("""
def calculate_tax(amount, rate):
    base = amount * rate
    discount = base * 0.05
    total = base - discount
    return total
""")

        with open(file_b, "w", encoding="utf-8") as handle:
            handle.write("""
def compute_fee(price, percentage):
    sub = price * percentage
    deduct = sub * 0.05
    res = sub - deduct
    return res
""")

        clones = find_code_clones(self.home, min_statements=3)
        self.assertGreater(len(clones), 0)
        
        findings = scan_clones(self.home, min_statements=3)
        self.assertGreater(len(findings), 0)
        self.assertTrue(any(f.rule == "code-clone" for f in findings))


if __name__ == "__main__":
    unittest.main()
