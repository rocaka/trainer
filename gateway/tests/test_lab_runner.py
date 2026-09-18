import unittest

from lab_runner import run_python_experiment


class LabRunnerTests(unittest.TestCase):
    def test_traces_assignment_and_print(self):
        result = run_python_experiment('name = "小明"\nprint(name)')
        self.assertEqual(result["output"], ["小明"])
        self.assertEqual(result["trace"][0]["label"], "name")

    def test_rejects_imports(self):
        with self.assertRaises(ValueError):
            run_python_experiment("import os")


if __name__ == "__main__":
    unittest.main()
