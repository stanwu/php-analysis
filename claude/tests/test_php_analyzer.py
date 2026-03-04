"""
Unit tests for php_analyzer.py
"""

import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Make the project root importable regardless of how tests are invoked.
sys.path.insert(0, str(Path(__file__).parent.parent))

from php_analyzer import (
    _analyse_file,
    _brace_depth_at,
    _extract_balanced,
    _indent_depth_at,
    _line_of,
    _strip_noise,
    analyse_directory,
)


# ---------------------------------------------------------------------------
# _strip_noise
# ---------------------------------------------------------------------------

class TestStripNoise(unittest.TestCase):
    def test_removes_single_line_comment(self):
        src = 'echo "hi"; // comment\n$x = 1;'
        result = _strip_noise(src)
        assert "comment" not in result
        assert "$x" in result

    def test_removes_multiline_comment(self):
        src = "/* block\ncomment */ $x = 1;"
        result = _strip_noise(src)
        assert "block" not in result
        assert "$x" in result

    def test_replaces_double_quoted_string(self):
        src = '$a = "hello world";'
        result = _strip_noise(src)
        assert "hello world" not in result
        assert '""' in result

    def test_replaces_single_quoted_string(self):
        src = "$a = 'hello world';"
        result = _strip_noise(src)
        assert "hello world" not in result
        assert "''" in result

    def test_keyword_inside_string_is_masked(self):
        src = '$s = "if (true) { }";'
        result = _strip_noise(src)
        assert "if (true)" not in result

    def test_escaped_quote_inside_string(self):
        src = r'$s = "say \"hi\"";'
        result = _strip_noise(src)
        assert "say" not in result

    def test_heredoc_replaced(self):
        src = "<<<EOT\nsome if content\nEOT;\n$x=1;"
        result = _strip_noise(src)
        assert "some if content" not in result

    def test_empty_string_unchanged(self):
        assert _strip_noise("") == ""

    def test_no_noise_unchanged(self):
        src = "$x = 1 + 2;"
        assert _strip_noise(src) == src


# ---------------------------------------------------------------------------
# _extract_balanced
# ---------------------------------------------------------------------------

class TestExtractBalanced(unittest.TestCase):
    def test_simple(self):
        text = "(abc)"
        assert _extract_balanced(text, 0) == "abc"

    def test_nested(self):
        text = "(a(b)c)"
        assert _extract_balanced(text, 0) == "a(b)c"

    def test_deeply_nested(self):
        text = "(a(b(c))d)"
        assert _extract_balanced(text, 0) == "a(b(c))d"

    def test_offset(self):
        text = "xyz(inner)"
        assert _extract_balanced(text, 3) == "inner"

    def test_unbalanced_returns_rest(self):
        text = "(abc"
        result = _extract_balanced(text, 0)
        assert result == "abc"

    def test_empty_parens(self):
        assert _extract_balanced("()", 0) == ""


# ---------------------------------------------------------------------------
# _line_of
# ---------------------------------------------------------------------------

class TestLineOf(unittest.TestCase):
    def test_start_is_line_1(self):
        assert _line_of("abc\ndef", 0) == 1

    def test_after_newline_is_line_2(self):
        text = "abc\ndef"
        assert _line_of(text, 4) == 2

    def test_third_line(self):
        text = "a\nb\nc"
        assert _line_of(text, 4) == 3

    def test_empty_text(self):
        assert _line_of("", 0) == 1


# ---------------------------------------------------------------------------
# _brace_depth_at
# ---------------------------------------------------------------------------

class TestBraceDepthAt(unittest.TestCase):
    def test_empty(self):
        assert _brace_depth_at("", 0) == 0

    def test_before_any_brace(self):
        assert _brace_depth_at("{}", 0) == 0

    def test_inside_first_block(self):
        text = "{ $x; }"
        assert _brace_depth_at(text, 2) == 1

    def test_after_closed_block(self):
        text = "{}"
        assert _brace_depth_at(text, 2) == 0

    def test_nested(self):
        text = "{{ "
        assert _brace_depth_at(text, 3) == 2

    def test_closed_then_open(self):
        text = "{} {"
        assert _brace_depth_at(text, 4) == 1


# ---------------------------------------------------------------------------
# _indent_depth_at
# ---------------------------------------------------------------------------

class TestIndentDepthAt(unittest.TestCase):
    def test_no_indent(self):
        src = "if (true) {"
        assert _indent_depth_at(src, 1) == 0

    def test_four_spaces(self):
        src = "line1\n    indented"
        assert _indent_depth_at(src, 2) == 1

    def test_eight_spaces(self):
        src = "line1\n        deep"
        assert _indent_depth_at(src, 2) == 2

    def test_one_tab(self):
        src = "line1\n\tindented"
        assert _indent_depth_at(src, 2) == 1

    def test_two_tabs(self):
        src = "line1\n\t\tindented"
        assert _indent_depth_at(src, 2) == 2

    def test_out_of_range_line(self):
        assert _indent_depth_at("abc", 99) == 0


# ---------------------------------------------------------------------------
# _analyse_file
# ---------------------------------------------------------------------------

class TestAnalyseFile(unittest.TestCase):
    def setUp(self):
        self.tmp_path = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_path, ignore_errors=True)

    def _write_php(self, content: str) -> Path:
        p = self.tmp_path / "test.php"
        p.write_text(content, encoding="utf-8")
        return p

    def test_empty_file(self):
        p = self._write_php("<?php\n")
        result = _analyse_file(p)
        assert result["total_branches"] == 0
        assert result["max_depth"] == 0
        assert result["branches"] == []

    def test_single_if(self):
        php = "<?php\nif ($x) { echo 1; }\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        assert result["total_branches"] == 1
        branches = result["branches"]
        assert branches[0]["type"] == "if"
        assert branches[0]["condition"] == "$x"

    def test_if_else(self):
        php = "<?php\nif ($x) {\n  echo 1;\n} else {\n  echo 2;\n}\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        types = [b["type"] for b in result["branches"]]
        assert "if" in types
        assert "else" in types
        assert result["total_branches"] == 2

    def test_elseif(self):
        php = "<?php\nif ($a) {\n} elseif ($b) {\n} else {\n}\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        types = [b["type"] for b in result["branches"]]
        assert types.count("if") == 1
        assert types.count("elseif") == 1
        assert types.count("else") == 1

    def test_if_inside_string_not_counted(self):
        php = '<?php\n$s = "if ($x) { }";\necho $s;\n'
        p = self._write_php(php)
        result = _analyse_file(p)
        assert result["total_branches"] == 0

    def test_nested_if_increases_depth(self):
        php = (
            "<?php\n"
            "if ($a) {\n"
            "    if ($b) {\n"
            "        if ($c) {\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        p = self._write_php(php)
        result = _analyse_file(p)
        assert result["max_depth"] >= 2

    def test_condition_extracted(self):
        php = "<?php\nif ($x > 0 && $y < 10) { }\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        assert result["branches"][0]["condition"] == "$x > 0 && $y < 10"

    def test_line_numbers(self):
        php = "<?php\n\nif ($z) { }\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        assert result["branches"][0]["line"] == 3

    def test_missing_file_returns_error(self):
        p = self.tmp_path / "nonexistent.php"
        result = _analyse_file(p)
        assert "error" in result
        assert result["total_branches"] == 0

    def test_function_grouping(self):
        php = (
            "<?php\n"
            "function foo() {\n"
            "    if ($a) { }\n"
            "}\n"
            "function bar() {\n"
            "    if ($b) { }\n"
            "    if ($c) { }\n"
            "}\n"
        )
        p = self._write_php(php)
        result = _analyse_file(p)
        names = {f["name"]: f for f in result["functions"]}
        assert "foo" in names
        assert "bar" in names
        assert names["foo"]["total_branches"] == 1
        assert names["bar"]["total_branches"] == 2

    def test_global_branches_grouped(self):
        php = "<?php\nif ($x) { }\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        global_entry = next(
            (f for f in result["functions"] if f["name"] == "<global>"), None
        )
        assert global_entry is not None
        assert global_entry["total_branches"] == 1

    def test_checksum_present(self):
        php = "<?php\nif ($x) { }\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        expected = hashlib.sha256(php.encode("utf-8")).hexdigest()
        assert result["checksum"] == expected

    def test_checksum_stable(self):
        php = "<?php\n$a = 1;\n"
        p = self._write_php(php)
        r1 = _analyse_file(p)
        r2 = _analyse_file(p)
        assert r1["checksum"] == r2["checksum"]

    def test_checksum_differs_for_different_content(self):
        p1 = self.tmp_path / "a.php"
        p2 = self.tmp_path / "b.php"
        p1.write_text("<?php\n$a = 1;\n", encoding="utf-8")
        p2.write_text("<?php\n$a = 2;\n", encoding="utf-8")
        r1 = _analyse_file(p1)
        r2 = _analyse_file(p2)
        assert r1["checksum"] != r2["checksum"]

    def test_missing_file_has_empty_checksum(self):
        p = self.tmp_path / "nonexistent.php"
        result = _analyse_file(p)
        assert result["checksum"] == ""

    def test_comment_if_not_counted(self):
        php = "<?php\n// if ($x) { }\n$y = 1;\n"
        p = self._write_php(php)
        result = _analyse_file(p)
        assert result["total_branches"] == 0


# ---------------------------------------------------------------------------
# analyse_directory
# ---------------------------------------------------------------------------

class TestAnalyseDirectory(unittest.TestCase):
    def setUp(self):
        self.tmp_path = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_path, ignore_errors=True)

    def test_empty_directory(self):
        report = analyse_directory(self.tmp_path)
        assert report["summary"]["total_files"] == 0
        assert report["summary"]["total_branches"] == 0
        assert report["files"] == {}

    def test_single_file(self):
        (self.tmp_path / "a.php").write_text("<?php\nif ($x) { }\n", encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        assert report["summary"]["total_files"] == 1
        assert report["summary"]["total_branches"] == 1

    def test_non_php_ignored(self):
        (self.tmp_path / "a.php").write_text("<?php\nif ($x) { }\n", encoding="utf-8")
        (self.tmp_path / "b.txt").write_text("if ($x) { }\n", encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        assert report["summary"]["total_files"] == 1

    def test_recursive_scan(self):
        sub = self.tmp_path / "sub"
        sub.mkdir()
        (self.tmp_path / "a.php").write_text("<?php\nif ($x) { }\n", encoding="utf-8")
        (sub / "b.php").write_text("<?php\nif ($y) { }\n", encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        assert report["summary"]["total_files"] == 2
        assert report["summary"]["total_branches"] == 2

    def test_most_complex_present(self):
        (self.tmp_path / "a.php").write_text("<?php\nif ($x) { }\n", encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        assert len(report["summary"]["most_complex"]) >= 1
        assert "file" in report["summary"]["most_complex"][0]

    def test_report_keys(self):
        report = analyse_directory(self.tmp_path)
        assert "summary" in report
        assert "files" in report
        assert "total_files" in report["summary"]
        assert "total_branches" in report["summary"]
        assert "most_complex" in report["summary"]

    def test_duplicates_key_present(self):
        report = analyse_directory(self.tmp_path)
        assert "duplicates" in report["summary"]

    def test_no_duplicates_when_files_differ(self):
        (self.tmp_path / "a.php").write_text("<?php\n$a = 1;\n", encoding="utf-8")
        (self.tmp_path / "b.php").write_text("<?php\n$b = 2;\n", encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        assert report["summary"]["duplicates"] == {}

    def test_duplicates_detected(self):
        content = "<?php\nif ($x) { }\n"
        (self.tmp_path / "a.php").write_text(content, encoding="utf-8")
        (self.tmp_path / "b.php").write_text(content, encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        dupes = report["summary"]["duplicates"]
        assert len(dupes) == 1
        paths = list(dupes.values())[0]
        assert sorted(paths) == ["a.php", "b.php"]

    def test_duplicates_three_copies(self):
        content = "<?php\n$x = 42;\n"
        for name in ("x.php", "y.php", "z.php"):
            (self.tmp_path / name).write_text(content, encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        dupes = report["summary"]["duplicates"]
        assert len(dupes) == 1
        paths = list(dupes.values())[0]
        assert len(paths) == 3

    def test_file_checksum_in_report(self):
        content = "<?php\n$a = 1;\n"
        (self.tmp_path / "a.php").write_text(content, encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert report["files"]["a.php"]["checksum"] == expected

    def test_multiple_files_total_branches(self):
        for i in range(3):
            php = "<?php\nif ($x) {{ }}\nelseif ($y) {{ }}\n"
            (self.tmp_path / f"f{i}.php").write_text(php, encoding="utf-8")
        report = analyse_directory(self.tmp_path)
        assert report["summary"]["total_branches"] == 6


if __name__ == "__main__":
    unittest.main()
