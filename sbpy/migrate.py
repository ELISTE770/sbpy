"""עוזר מיגרציות ושדרוג ספריות ותחביר (Smart Migration Assistant).

ממיר קוד פייתון ישן לתחביר ולספריות מודרניות באופן אוטונומי:
- unittest -> pytest
- requests -> httpx
- pydantic v1 -> pydantic v2
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class MigrationResult:
    file: str
    original: str
    updated: str
    changes: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return self.original != self.updated


def migrate_unittest_to_pytest(source: str) -> tuple[str, list[str]]:
    """ממיר בדיקות מ-unittest ל-pytest נקי."""
    changes: list[str] = []
    lines = source.splitlines()
    new_lines: list[str] = []
    has_pytest_import = "import pytest" in source

    for line in lines:
        new_line = line

        # 1. self.assertEqual(a, b) -> assert a == b
        m_eq = re.search(r"self\.assertEqual\s*\((.*?),\s*(.*?)\)", new_line)
        if m_eq:
            a, b = m_eq.group(1).strip(), m_eq.group(2).strip()
            new_line = re.sub(r"self\.assertEqual\s*\(.*?\)", f"assert {a} == {b}", new_line)
            changes.append("המרת self.assertEqual ל-assert ==")

        # 2. self.assertTrue(x) -> assert x
        m_tr = re.search(r"self\.assertTrue\s*\((.*?)\)", new_line)
        if m_tr:
            x = m_tr.group(1).strip()
            new_line = re.sub(r"self\.assertTrue\s*\(.*?\)", f"assert {x}", new_line)
            changes.append("המרת self.assertTrue ל-assert")

        # 3. self.assertFalse(x) -> assert not x
        m_fa = re.search(r"self\.assertFalse\s*\((.*?)\)", new_line)
        if m_fa:
            x = m_fa.group(1).strip()
            new_line = re.sub(r"self\.assertFalse\s*\(.*?\)", f"assert not ({x})", new_line)
            changes.append("המרת self.assertFalse ל-assert not")

        # 4. self.assertIn(a, b) -> assert a in b
        m_in = re.search(r"self\.assertIn\s*\((.*?),\s*(.*?)\)", new_line)
        if m_in:
            a, b = m_in.group(1).strip(), m_in.group(2).strip()
            new_line = re.sub(r"self\.assertIn\s*\(.*?\)", f"assert {a} in {b}", new_line)
            changes.append("המרת self.assertIn ל-assert in")

        # 5. self.assertIsNone(x) -> assert x is None
        m_none = re.search(r"self\.assertIsNone\s*\((.*?)\)", new_line)
        if m_none:
            x = m_none.group(1).strip()
            new_line = re.sub(r"self\.assertIsNone\s*\(.*?\)", f"assert {x} is None", new_line)
            changes.append("המרת self.assertIsNone ל-assert is None")

        # 6. self.assertRaises(Exc) -> pytest.raises(Exc)
        if "self.assertRaises(" in new_line:
            new_line = new_line.replace("self.assertRaises(", "pytest.raises(")
            changes.append("המרת self.assertRaises ל-pytest.raises")
            has_pytest_import = False  # נוודא שמוסיפים import pytest

        # 7. unittest.TestCase -> ביטול ירושה
        if re.search(r"class\s+\w+\(unittest\.TestCase\):", new_line):
            new_line = re.sub(r"\(unittest\.TestCase\)", "", new_line)
            changes.append("הסרת ירושה מ-unittest.TestCase")

        new_lines.append(new_line)

    updated_source = "\n".join(new_lines) + ("\n" if source.endswith("\n") else "")
    if "pytest.raises" in updated_source and "import pytest" not in updated_source:
        updated_source = "import pytest\n" + updated_source
        changes.append("הוספת import pytest")

    return updated_source, changes


def migrate_requests_to_httpx(source: str) -> tuple[str, list[str]]:
    """ממיר שימוש ב-requests ל-httpx המודרנית."""
    changes: list[str] = []
    updated = source

    if "import requests" in updated:
        updated = updated.replace("import requests", "import httpx")
        changes.append("החלפת import requests ב-import httpx")

    if "from requests import" in updated:
        updated = updated.replace("from requests import", "from httpx import")
        changes.append("החלפת from requests ב-from httpx")

    if "requests.get(" in updated:
        updated = updated.replace("requests.get(", "httpx.get(")
        changes.append("המרת requests.get ל-httpx.get")

    if "requests.post(" in updated:
        updated = updated.replace("requests.post(", "httpx.post(")
        changes.append("המרת requests.post ל-httpx.post")

    if "requests.Session()" in updated:
        updated = updated.replace("requests.Session()", "httpx.Client()")
        changes.append("המרת requests.Session ל-httpx.Client")

    return updated, changes


def migrate_pydantic_v1_to_v2(source: str) -> tuple[str, list[str]]:
    """ממיר מודלים של Pydantic v1 לתחביר Pydantic v2."""
    changes: list[str] = []
    updated = source

    if "from pydantic import validator" in updated:
        updated = updated.replace("from pydantic import validator", "from pydantic import field_validator")
        changes.append("המרת validator ל-field_validator")

    if "@validator(" in updated:
        updated = updated.replace("@validator(", "@field_validator(")
        changes.append("המרת דקורטור @validator ל-@field_validator")

    if ".dict()" in updated:
        updated = updated.replace(".dict()", ".model_dump()")
        changes.append("המרת .dict() ל-.model_dump()")

    if ".json()" in updated:
        updated = updated.replace(".json()", ".model_dump_json()")
        changes.append("המרת .json() ל-.model_dump_json()")

    return updated, changes


MIGRATION_PROVIDERS: dict[str, Callable[[str], tuple[str, list[str]]]] = {
    "pytest": migrate_unittest_to_pytest,
    "httpx": migrate_requests_to_httpx,
    "pydantic": migrate_pydantic_v1_to_v2,
}


def run_migration(
    file_path: str,
    target: str,
    *,
    dry_run: bool = False,
) -> MigrationResult:
    """מריץ מיגרציה על קובץ בודד."""
    provider = MIGRATION_PROVIDERS.get(target.lower())
    if not provider:
        raise ValueError(f"Unknown migration target: {target}. Available: {list(MIGRATION_PROVIDERS.keys())}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
        original = handle.read()

    updated, changes = provider(original)
    res = MigrationResult(file=file_path, original=original, updated=updated, changes=changes)

    if not dry_run and res.has_changes:
        # בדיקת תקינות תחבירית לפני כתיבה
        ast.parse(updated)
        with open(file_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)

    return res
