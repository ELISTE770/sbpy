"""Unit tests for git_ops module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sbpy.git_ops import (
    BACKUP_SUFFIX,
    is_git_repo,
    record_backup,
    undo_last_patch,
)


class GitOpsTest(unittest.TestCase):
    def test_record_and_undo_patch(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("original_code = 1\n")
            temp_path = f.name

        try:
            # 1. Record backup
            record_backup(temp_path, "original_code = 1\n")

            # 2. Modify file (as if patch was applied)
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write("modified_code = 2\n")

            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "modified_code = 2\n")

            # 3. Undo
            restored = undo_last_patch()
            self.assertEqual(restored, temp_path)
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "original_code = 1\n")
        finally:
            Path(temp_path).unlink(missing_ok=True)
            Path(temp_path + BACKUP_SUFFIX).unlink(missing_ok=True)

    def test_is_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertFalse(is_git_repo(temp_dir))
            git_dir = Path(temp_dir) / ".git"
            git_dir.mkdir()
            self.assertTrue(is_git_repo(temp_dir))


if __name__ == "__main__":
    unittest.main()
