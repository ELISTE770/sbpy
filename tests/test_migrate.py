"""בדיקות עבור עוזר המיגרציות (sbpy/migrate.py)."""

from __future__ import annotations

import unittest

from sbpy.migrate import (
    migrate_pydantic_v1_to_v2,
    migrate_requests_to_httpx,
    migrate_unittest_to_pytest,
)
from tests.support import IsolatedConfigTest


class MigrateTest(IsolatedConfigTest):
    def test_migrate_unittest_to_pytest(self) -> None:
        source = """
import unittest

class TestMath(unittest.TestCase):
    def test_add(self):
        self.assertEqual(1 + 1, 2)
        self.assertTrue(True)
        self.assertIn(1, [1, 2])
        self.assertIsNone(None)
"""
        updated, changes = migrate_unittest_to_pytest(source)
        self.assertNotIn("unittest.TestCase", updated)
        self.assertIn("assert 1 + 1 == 2", updated)
        self.assertIn("assert True", updated)
        self.assertIn("assert 1 in [1, 2]", updated)
        self.assertIn("assert None is None", updated)
        self.assertGreater(len(changes), 0)

    def test_migrate_requests_to_httpx(self) -> None:
        source = """
import requests

def fetch():
    s = requests.Session()
    return requests.get("https://api.example.com")
"""
        updated, changes = migrate_requests_to_httpx(source)
        self.assertIn("import httpx", updated)
        self.assertIn("httpx.Client()", updated)
        self.assertIn("httpx.get(", updated)
        self.assertNotIn("requests", updated)

    def test_migrate_pydantic(self) -> None:
        source = """
from pydantic import BaseModel, validator

class User(BaseModel):
    name: str

    @validator('name')
    def check_name(cls, v):
        return v.strip()

u = User(name="Alice")
d = u.dict()
j = u.json()
"""
        updated, changes = migrate_pydantic_v1_to_v2(source)
        self.assertIn("field_validator", updated)
        self.assertIn("@field_validator('name')", updated)
        self.assertIn("u.model_dump()", updated)
        self.assertIn("u.model_dump_json()", updated)


if __name__ == "__main__":
    unittest.main()
