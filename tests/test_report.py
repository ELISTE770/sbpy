"""בדיקות עבור הפקת דוחות HTML אינטראקטיביים."""

from __future__ import annotations

import os
import unittest

from sbpy.report import _compute_grade, generate_html_report
from sbpy.results import Finding, ScanResult
from tests.support import IsolatedConfigTest


class ReportTest(IsolatedConfigTest):
    def test_compute_grade(self) -> None:
        clean_findings: list[Finding] = []
        grade, color = _compute_grade(clean_findings)
        self.assertEqual(grade, "A")

        crit_findings = [Finding(file="a.py", line=1, col=0, rule="sql-injection", message="sqli", severity="critical")]
        grade, color = _compute_grade(crit_findings)
        self.assertEqual(grade, "C")

    def test_generate_html_report_file(self) -> None:
        findings = [
            Finding(file="test.py", line=10, col=4, rule="bare-except", message="bare except used", severity="error", hint="Use Exception"),
            Finding(file="sec.py", line=20, col=0, rule="shell-injection", message="os.system call", severity="critical", hint="Use subprocess"),
        ]
        results = [ScanResult(shortcut="SFB", target="test.py", findings=findings)]
        out_html = os.path.join(self.home, "report.html")

        path = generate_html_report(results, project_root=self.home, output_path=out_html)
        self.assertTrue(os.path.isfile(path))

        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        self.assertIn("SBpy", content)
        self.assertIn("bare-except", content)
        self.assertIn("shell-injection", content)
        self.assertIn("Critical", content)


if __name__ == "__main__":
    unittest.main()
