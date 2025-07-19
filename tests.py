import json
import os
import glob
import unittest
from io import StringIO
from typing import Any, Dict, List

# Import the pyhuml module (assuming it's in the same directory or installed)
import pyhuml


class TestAssertions(unittest.TestCase):
    """Test assertions from JSON test files."""

    def test_assertions(self):
        self.maxDiff = None
        """Walk the ./tests/assertions directory and run tests from JSON files."""
        # Find all JSON files in the assertions directory
        assertion_files = glob.glob("./tests/assertions/*.json")

        if not assertion_files:
            self.skipTest("No assertion files found in ./tests/assertions/")

        for filepath in assertion_files:
            with self.subTest(file=filepath):
                # Read the JSON test file
                with open(filepath, 'r', encoding='utf-8') as f:
                    tests = json.load(f)

                # Run each assertion
                for n, test_case in enumerate(tests):
                    # +2 to account for the opening [ and the line break in the test file
                    test_name = f"line {n + 2}: {test_case['name']}"

                    with self.subTest(test=test_name):
                        self._run_assertion(
                            test_case['input'],
                            test_case['error']
                        )

    def _run_assertion(self, input_str: str, error_expected: bool):
        """Run a single assertion test."""
        # Test with loads() directly
        if error_expected:
            with self.assertRaises(pyhuml.HUMLError):
                pyhuml.loads(input_str)
        else:
            # Should not raise an error
            try:
                result = pyhuml.loads(input_str)
            except pyhuml.HUMLError as e:
                self.fail(f"Unexpected error: {e}")

        # Test again via load() with StringIO
        if error_expected:
            with self.assertRaises(pyhuml.HUMLError):
                pyhuml.load(StringIO(input_str))
        else:
            # Should not raise an error
            try:
                result = pyhuml.load(StringIO(input_str))
            except pyhuml.HUMLError as e:
                self.fail(f"Unexpected error: {e}")


class TestEncodeDoc(unittest.TestCase):
    """Test encoding and round-trip conversion."""

    def test_encode_doc(self):
        self.maxDiff = None
        """Test that we can load a HUML doc, encode it, and get the same result."""
        # Check if test files exist
        huml_path = "tests/documents/mixed.huml"
        json_path = "tests/documents/mixed.json"

        if not os.path.exists(huml_path) or not os.path.exists(json_path):
            self.skipTest(f"Test files not found: {huml_path} or {json_path}")

        # Read and parse the HUML file
        with open(huml_path, 'r', encoding='utf-8') as f:
            huml_content = f.read()

        res_huml = pyhuml.loads(huml_content)

        # Marshal it back to HUML
        marshalled = pyhuml.dumps(res_huml)

        # Parse it again
        res_huml_converted = pyhuml.loads(marshalled)

        # Read and parse the JSON file
        with open(json_path, 'r', encoding='utf-8') as f:
            res_json = json.load(f)

        # Deep compare both
        self.assertDictEqual(
            res_huml_converted, res_json,
            f"{huml_path} and {json_path} should be deeply equal"
        )


class TestDocuments(unittest.TestCase):
    """Test loading HUML documents and comparing with JSON equivalents."""

    def test_documents(self):
        """Test all HUML documents against their JSON counterparts."""
        # Find all HUML files in the documents directory
        huml_files = glob.glob("tests/documents/*.huml")

        if not huml_files:
            self.skipTest("No HUML files found in tests/documents/")

        for huml_path in huml_files:
            json_path = huml_path[:-5] + ".json"  # Replace .huml with .json

            with self.subTest(file=huml_path):
                # Skip if corresponding JSON doesn't exist
                if not os.path.exists(json_path):
                    self.skipTest(
                        f"No corresponding JSON file for {huml_path}")

                # Read and parse HUML
                with open(huml_path, 'r', encoding='utf-8') as f:
                    huml_content = f.read()

                res_huml = pyhuml.loads(huml_content)

                # Read and parse JSON
                with open(json_path, 'r', encoding='utf-8') as f:
                    res_json = json.load(f)

                # Deep compare
                self.assertDictEqual(
                    res_huml, res_json,
                    f"{huml_path} and {json_path} should be deeply equal"
                )


if __name__ == '__main__':
    import unittest
    unittest.main()
    # with open("tests/documents/mixed.huml", 'r', encoding='utf-8') as f:
    #     input_str = f.read( )
    #     print(pyhuml.loads(input_str))
