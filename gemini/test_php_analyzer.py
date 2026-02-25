
import unittest
import os
import shutil
import json
from php_analyzer import analyze_php_file, find_php_files

class TestPhpAnalyzer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up a temporary directory and mock PHP files for testing."""
        cls.test_dir = "temp_test_project"
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
        os.makedirs(os.path.join(cls.test_dir, "subdir"))

        cls.files_to_create = {
            "simple.php": """
                <?php
                if ($a > 1) {
                    echo "hello";
                }
            """,
            "if_else.php": """
                <?php
                if ($a > 1) {
                    echo "a";
                } else {
                    echo "b";
                }
            """,
            "nested.php": """
                <?php // Test nesting
                if ($a) {
                    if ($b) {
                        if ($c) {
                            echo "c";
                        }
                    }
                }
                if ($d) { echo "d"; }
            """,
            "complex_condition.php": """
                <?php
                if (isset($a) && ($b || my_func(1, 2))) {
                    // complex
                }
            """,
            "no_branches.php": "<?php echo 'no branches'; ?>",
            "empty.php": "",
            os.path.join("subdir", "sub_file.php"): """
                <?php
                if ($x) {
                    echo "x";
                }
            """
        }

        for path, content in cls.files_to_create.items():
            full_path = os.path.join(cls.test_dir, path)
            with open(full_path, "w") as f:
                f.write(content)
        
        # Create a non-php file that should be ignored
        with open(os.path.join(cls.test_dir, "README.md"), "w") as f:
            f.write("# Test")

    @classmethod
    def tearDownClass(cls):
        """Remove the temporary directory after all tests are done."""
        shutil.rmtree(cls.test_dir)

    def test_find_php_files(self):
        """Test that PHP files are found recursively."""
        expected_files = sorted([
            os.path.join(self.test_dir, "simple.php"),
            os.path.join(self.test_dir, "if_else.php"),
            os.path.join(self.test_dir, "nested.php"),
            os.path.join(self.test_dir, "complex_condition.php"),
            os.path.join(self.test_dir, "no_branches.php"),
            os.path.join(self.test_dir, "empty.php"),
            os.path.join(self.test_dir, "subdir", "sub_file.php")
        ])
        found_files = sorted(find_php_files(self.test_dir))
        self.assertEqual(len(found_files), 7)
        self.assertListEqual(found_files, expected_files)

    def test_analysis_simple_if(self):
        """Test a single if statement."""
        result = analyze_php_file(os.path.join(self.test_dir, "simple.php"))
        self.assertIsNotNone(result)
        self.assertEqual(result["total_branches"], 1)
        self.assertEqual(result["max_depth"], 1)
        self.assertEqual(result["branches"][0]["type"], "if")
        self.assertEqual(result["branches"][0]["depth"], 0)
        self.assertEqual(result["branches"][0]["condition"], "$a > 1")

    def test_analysis_if_else(self):
        """Test an if/else block."""
        result = analyze_php_file(os.path.join(self.test_dir, "if_else.php"))
        self.assertIsNotNone(result)
        self.assertEqual(result["total_branches"], 2)
        self.assertEqual(result["max_depth"], 1)
        self.assertEqual(result["branches"][0]["type"], "if")
        self.assertEqual(result["branches"][1]["type"], "else")

    def test_analysis_nested_if(self):
        """Test nested if statements for max_depth calculation."""
        result = analyze_php_file(os.path.join(self.test_dir, "nested.php"))
        self.assertIsNotNone(result)
        self.assertEqual(result["total_branches"], 4)
        self.assertEqual(result["max_depth"], 3)
        # Check depth of each branch
        self.assertEqual(result["branches"][0]["depth"], 0) # if ($a)
        self.assertEqual(result["branches"][1]["depth"], 1) # if ($b)
        self.assertEqual(result["branches"][2]["depth"], 2) # if ($c)
        self.assertEqual(result["branches"][3]["depth"], 0) # if ($d)

    def test_analysis_complex_condition(self):
        """Test a complex condition is extracted correctly."""
        result = analyze_php_file(os.path.join(self.test_dir, "complex_condition.php"))
        self.assertIsNotNone(result)
        self.assertEqual(result["total_branches"], 1)
        expected_condition = "isset($a) && ($b || my_func(1, 2))"
        self.assertEqual(result["branches"][0]["condition"], expected_condition)

    def test_analysis_no_branches(self):
        """Test a file with no conditional branches."""
        result = analyze_php_file(os.path.join(self.test_dir, "no_branches.php"))
        self.assertIsNotNone(result)
        self.assertEqual(result["total_branches"], 0)
        self.assertEqual(result["max_depth"], 0)

    def test_analysis_empty_file(self):
        """Test an empty file."""
        result = analyze_php_file(os.path.join(self.test_dir, "empty.php"))
        self.assertIsNotNone(result)
        self.assertEqual(result["total_branches"], 0)
        self.assertEqual(result["max_depth"], 0)

if __name__ == '__main__':
    unittest.main()
