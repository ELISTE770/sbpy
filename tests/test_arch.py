"""בדיקות עבור איתור תלויות מעגליות והפרות שכבות (sbpy/arch.py)."""

from __future__ import annotations

import os
import unittest

from sbpy.arch import find_circular_imports, scan_architecture
from tests.support import IsolatedConfigTest


class ArchTest(IsolatedConfigTest):
    def test_find_circular_imports(self) -> None:
        # יוצרים מעגל: a.py מייבא את b, ו-b.py מייבא את a
        a_file = os.path.join(self.home, "mod_a.py")
        b_file = os.path.join(self.home, "mod_b.py")

        with open(a_file, "w", encoding="utf-8") as handle:
            handle.write("import mod_b\n")

        with open(b_file, "w", encoding="utf-8") as handle:
            handle.write("import mod_a\n")

        cycles = find_circular_imports(self.home)
        self.assertGreater(len(cycles), 0)
        cycle_flat = [node for c in cycles for node in c]
        self.assertIn("mod_a", cycle_flat)
        self.assertIn("mod_b", cycle_flat)

        findings = scan_architecture(self.home)
        self.assertTrue(any(f.rule == "circular-import" for f in findings))

    def test_layer_boundary_violations(self) -> None:
        # שכבות: ["domain", "services", "api"]
        # נבדוק הפרה: קוד ב-domain מייבא מ-api
        domain_dir = os.path.join(self.home, "domain")
        api_dir = os.path.join(self.home, "api")
        os.makedirs(domain_dir, exist_ok=True)
        os.makedirs(api_dir, exist_ok=True)

        with open(os.path.join(domain_dir, "models.py"), "w", encoding="utf-8") as handle:
            handle.write("import api.routes\n")

        with open(os.path.join(api_dir, "routes.py"), "w", encoding="utf-8") as handle:
            handle.write("x = 1\n")

        findings = scan_architecture(self.home, layers=["domain", "services", "api"])
        layer_violations = [f for f in findings if f.rule == "layer-violation"]
        self.assertGreater(len(layer_violations), 0)
        self.assertIn("domain", layer_violations[0].message)
        self.assertIn("api", layer_violations[0].message)


if __name__ == "__main__":
    unittest.main()
