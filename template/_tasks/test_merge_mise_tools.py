"""Tests for merge-mise-tools.py."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_mise_tools import parse_tools


class TestParseTools(unittest.TestCase):
    """parse_tools reads [tools] key-value pairs from a TOML file."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "test.toml")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, content):
        with open(self.path, "w") as f:
            f.write(content)

    def test_bare_keys(self):
        self._write('[tools]\ngo = "1.26.4"\ngolangci-lint = "2.12.2"\n')
        self.assertEqual(
            parse_tools(self.path), {"go": "1.26.4", "golangci-lint": "2.12.2"}
        )

    def test_quoted_keys(self):
        self._write('[tools]\n"go:golang.org/x/vuln/cmd/govulncheck" = "1.1.4"\n')
        self.assertEqual(
            parse_tools(self.path),
            {"go:golang.org/x/vuln/cmd/govulncheck": "1.1.4"},
        )

    def test_ignores_other_sections(self):
        self._write('[tools]\ngo = "1.26.4"\n\n[env]\nCOVEROUT = "cover.out"\n')
        self.assertEqual(parse_tools(self.path), {"go": "1.26.4"})

    def test_ignores_settings_section(self):
        self._write('[tools]\ngo = "1.26.4"\n\n[settings]\ntask.timings = false\n')
        self.assertEqual(parse_tools(self.path), {"go": "1.26.4"})

    def test_empty_file(self):
        self._write("")
        self.assertEqual(parse_tools(self.path), {})

    def test_no_tools_section(self):
        self._write('[env]\nCOVEROUT = "cover.out"\n')
        self.assertEqual(parse_tools(self.path), {})

    def test_comments_skipped(self):
        self._write('[tools]\n# this is a comment\ngo = "1.26.4"\n')
        self.assertEqual(parse_tools(self.path), {"go": "1.26.4"})

    def test_blank_lines_skipped(self):
        self._write('[tools]\ngo = "1.26.4"\n\n\n[env]\n')
        self.assertEqual(parse_tools(self.path), {"go": "1.26.4"})

    def test_quoted_value_contains_dots_slashes(self):
        self._write(
            "[tools]\n"
            '"npm:cpd" = "5.0.11"\n'
            '"go:golang.org/x/tools/cmd/deadcode" = "0.46.0"\n',
        )
        self.assertEqual(
            parse_tools(self.path),
            {
                "npm:cpd": "5.0.11",
                "go:golang.org/x/tools/cmd/deadcode": "0.46.0",
            },
        )


class TestMerge(unittest.TestCase):
    """End-to-end merge of missing tools into mise.toml."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.desired = os.path.join(self.tmpdir.name, ".mise-desired.toml")
        self.target = os.path.join(self.tmpdir.name, "mise.toml")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, path, content):
        p = os.path.join(self.tmpdir.name, path)
        with open(p, "w") as f:
            f.write(content)

    def _read(self, path):
        p = os.path.join(self.tmpdir.name, path)
        with open(p) as f:
            return f.read()

    def test_merge_adds_new_tool_inside_tools_section(self):
        self._write(".mise-desired.toml", '[tools]\ngo = "1.26.4"\nruff = "0.11.4"\n')
        self._write(
            "mise.toml", '[tools]\ngo = "1.26.4"\n\n[env]\nCOVEROUT = "cover.out"\n'
        )
        from merge_mise_tools import main

        original_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir.name)
            main()
            result = self._read("mise.toml")
        finally:
            os.chdir(original_cwd)

        self.assertIn('ruff = "0.11.4"', result)
        self.assertNotIn(".mise-desired.toml", os.listdir(self.tmpdir.name))

    def test_merge_skips_existing_tools(self):
        self._write(".mise-desired.toml", '[tools]\ngo = "1.26.4"\nruff = "0.11.4"\n')
        self._write(
            "mise.toml",
            '[tools]\ngo = "1.26.4"\nruff = "0.9.0"\n\n[env]\nCOVEROUT = "cover.out"\n',
        )
        from merge_mise_tools import main

        original_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir.name)
            main()
            result = self._read("mise.toml")
        finally:
            os.chdir(original_cwd)

        # Existing pin preserved — no duplicate
        self.assertIn('ruff = "0.9.0"', result)
        self.assertEqual(result.count("ruff"), 1)

    def test_merge_adds_tools_section_when_missing(self):
        self._write(".mise-desired.toml", '[tools]\nruff = "0.11.4"\n')
        self._write("mise.toml", '[env]\nCOVEROUT = "cover.out"\n')
        from merge_mise_tools import main

        original_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir.name)
            main()
            result = self._read("mise.toml")
        finally:
            os.chdir(original_cwd)

        self.assertIn("[tools]", result)
        self.assertIn('ruff = "0.11.4"', result)


if __name__ == "__main__":
    unittest.main()
