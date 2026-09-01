"""בדיקות עבור הפקת דיאגרמות Mermaid (sbpy/diagrams.py)."""

from __future__ import annotations

import os
import unittest

from sbpy.diagrams import generate_class_diagram, generate_flow_diagram, save_diagram
from tests.support import IsolatedConfigTest


class DiagramsTest(IsolatedConfigTest):
    def test_class_diagram_generation(self) -> None:
        target_file = os.path.join(self.home, "models.py")
        with open(target_file, "w", encoding="utf-8") as handle:
            handle.write("""
class Animal:
    name: str

    def speak(self):
        pass

class Dog(Animal):
    breed: str

    def bark(self, volume):
        pass
""")

        diagram = generate_class_diagram(self.home)
        self.assertIn("class Animal", diagram)
        self.assertIn("class Dog", diagram)
        self.assertIn("Animal <|-- Dog", diagram)
        self.assertIn("+bark(volume)", diagram)

    def test_flow_diagram_generation(self) -> None:
        file_a = os.path.join(self.home, "app.py")
        file_b = os.path.join(self.home, "db.py")

        with open(file_a, "w", encoding="utf-8") as handle:
            handle.write("import db\n")

        with open(file_b, "w", encoding="utf-8") as handle:
            handle.write("x = 1\n")

        flow = generate_flow_diagram(self.home)
        self.assertIn("app --> db", flow)

        out_md = os.path.join(self.home, "arch.md")
        saved = save_diagram(flow, out_md)
        self.assertTrue(os.path.isfile(saved))


if __name__ == "__main__":
    unittest.main()
