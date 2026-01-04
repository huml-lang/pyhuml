import json
import os
import glob
import unittest
from io import StringIO

import pyhuml


def make_assertion_test(test_name, input_str, error_expected):
    """Create a test method for an individual assertion."""
    def test_method(self):
        if error_expected:
            with self.assertRaises(pyhuml.HUMLError):
                pyhuml.loads(input_str)
            with self.assertRaises(pyhuml.HUMLError):
                pyhuml.load(StringIO(input_str))
        else:
            try:
                pyhuml.loads(input_str)
                pyhuml.load(StringIO(input_str))
            except pyhuml.HUMLError as e:
                self.fail(f"Unexpected error: {e}")

    test_method.__name__ = f"test_{test_name}"
    test_method.__doc__ = test_name
    return test_method


def make_document_test(huml_path, json_path):
    """Create a test method for an individual document."""
    def test_method(self):
        with open(huml_path, 'r', encoding='utf-8') as f:
            huml_content = f.read()

        res_huml = pyhuml.loads(huml_content)

        with open(json_path, 'r', encoding='utf-8') as f:
            res_json = json.load(f)

        self.assertEqual(res_huml, res_json)

    basename = os.path.basename(huml_path)
    test_method.__name__ = f"test_{basename}"
    test_method.__doc__ = f"testing {basename}"
    return test_method


def make_encode_test(huml_path, json_path):
    """Create a test method for an individual encode round-trip."""
    def test_method(self):
        with open(huml_path, 'r', encoding='utf-8') as f:
            huml_content = f.read()

        res_huml = pyhuml.loads(huml_content)
        marshalled = pyhuml.dumps(res_huml)
        res_huml_converted = pyhuml.loads(marshalled)

        with open(json_path, 'r', encoding='utf-8') as f:
            res_json = json.load(f)

        self.assertEqual(res_huml_converted, res_json)

    basename = os.path.basename(huml_path)
    test_method.__name__ = f"test_encode_{basename}"
    test_method.__doc__ = f"encode round-trip {basename}"
    return test_method


class TestAssertions(unittest.TestCase):
    """Test assertions from JSON test files."""
    pass


class TestDocuments(unittest.TestCase):
    """Test loading HUML documents and comparing with JSON equivalents."""
    pass


class TestEncode(unittest.TestCase):
    """Test encoding and round-trip conversion."""
    pass


def load_tests(loader, tests, pattern):
    """Dynamically generate test cases from JSON test files."""
    suite = unittest.TestSuite()

    # Load assertion tests
    assertion_files = sorted(glob.glob("./tests/assertions/*.json"))
    for filepath in assertion_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)

        for n, test_case in enumerate(test_cases):
            test_name = f"{test_case['name']}"
            test_method = make_assertion_test(
                test_name,
                test_case['input'],
                test_case['error']
            )
            setattr(TestAssertions, test_method.__name__, test_method)

    # Load document tests
    huml_files = sorted(glob.glob("./tests/documents/*.huml"))
    for huml_path in huml_files:
        json_path = huml_path[:-5] + ".json"
        if os.path.exists(json_path):
            # Document comparison test
            test_method = make_document_test(huml_path, json_path)
            setattr(TestDocuments, test_method.__name__, test_method)

            # Encode round-trip test
            encode_method = make_encode_test(huml_path, json_path)
            setattr(TestEncode, encode_method.__name__, encode_method)

    # Add all test classes to suite
    suite.addTests(loader.loadTestsFromTestCase(TestAssertions))
    suite.addTests(loader.loadTestsFromTestCase(TestDocuments))
    suite.addTests(loader.loadTestsFromTestCase(TestEncode))

    return suite


if __name__ == '__main__':
    unittest.main(verbosity=2)
