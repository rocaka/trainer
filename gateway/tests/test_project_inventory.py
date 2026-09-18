import tempfile
import unittest
from pathlib import Path
from project_import import inspect_project

class InventoryTests(unittest.TestCase):
    def test_functions_and_exclusions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.py').write_text('def score(value):\n    return value + 1\n')
            (root / '.env.secret').write_text('SECRET=private')
            (root / 'node_modules').mkdir()
            (root / 'node_modules' / 'ignored.py').write_text('secret=1')
            result = inspect_project(folder)
            self.assertEqual(result['fileCount'], 1)
            self.assertIn('score', result['projectDocuments']['project/INVENTORY.md'])
            self.assertNotIn('SECRET', str(result))

