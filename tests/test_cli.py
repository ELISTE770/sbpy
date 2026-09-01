"""בדיקות מקיפות ל-CLI."""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from sbpy import cli
from tests.support import IsolatedConfigTest


class CliCommandsTest(IsolatedConfigTest):
    def test_doctor_command(self) -> None:
        self.assertEqual(cli.main(["doctor"]), cli.EXIT_OK)

    def test_usage_command(self) -> None:
        self.assertEqual(cli.main(["usage"]), cli.EXIT_OK)

    def test_cache_command(self) -> None:
        self.assertEqual(cli.main(["cache"]), cli.EXIT_OK)
        self.assertEqual(cli.main(["cache", "--clear"]), cli.EXIT_OK)

    def test_index_command(self) -> None:
        self.assertEqual(cli.main(["index"]), cli.EXIT_OK)
        self.assertEqual(cli.main(["index", "--rebuild"]), cli.EXIT_OK)

    def test_learn_command(self) -> None:
        self.assertEqual(cli.main(["learn"]), cli.EXIT_OK)
        self.assertEqual(cli.main(["learn", "--clear"]), cli.EXIT_OK)

    def test_shortcuts_command(self) -> None:
        self.assertEqual(cli.main(["shortcuts"]), cli.EXIT_OK)

    def test_explain_command(self) -> None:
        self.assertEqual(cli.main(["explain", "ZeroDivisionError: division by zero"]), cli.EXIT_OK)

    def test_sfb_command_on_clean_file(self) -> None:
        path = os.path.join(self.home, "clean.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x = 1\ny = 2\n")
        self.assertEqual(cli.main(["sfb", path]), cli.EXIT_OK)

    def test_sfb_command_json_output(self) -> None:
        path = os.path.join(self.home, "buggy.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("try:\n    pass\nexcept:\n    pass\n")
        
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cli.main(["sfb", path, "--json"])
            self.assertEqual(code, cli.EXIT_FINDINGS)
            output = mock_out.getvalue()
            self.assertIn("bare-except", output)

    def test_sec_command_sarif_output(self) -> None:
        path = os.path.join(self.home, "insecure.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("import os\nos.system('ls ' + user_input)\n")
        
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cli.main(["sec", path, "--sarif"])
            self.assertEqual(code, cli.EXIT_FINDINGS)
            output = mock_out.getvalue()
            self.assertIn("shell-injection", output)
            self.assertIn("sarif", output.lower())

    def test_mod_command_finds_old_patterns(self) -> None:
        path = os.path.join(self.home, "old.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("import os\nimport typing\nx: typing.List[int] = [1]\np = os.path.join('a', 'b')\n")
        
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = cli.main(["mod", path])
            self.assertEqual(code, cli.EXIT_OK)
            output = mock_err.getvalue()
            self.assertIn("MOD", output)

    def test_fix_dry_run(self) -> None:
        path = os.path.join(self.home, "to_fix.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("print('{x}')\n")
        
        self.assertEqual(cli.main(["fix", path, "--dry-run"]), cli.EXIT_OK)


if __name__ == "__main__":
    unittest.main()
