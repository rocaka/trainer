import tempfile
import unittest
from pathlib import Path
from extension_pairing import Pairings
from pairing_service import PairingService
from submission_runtime import SubmissionRuntime
from learning_loop import connect


class RuntimeTests(unittest.TestCase):
    def test_private_startup_no_evaluation_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            pairing = PairingService(Pairings(root / 'pair.db'), 'native', root)
            settings = lambda: ('deepseek', 'test', 'https://example.invalid', 'test-key')
            runtime = SubmissionRuntime(root, root, pairing, settings, lambda *args: self.fail('启动不能调用AI'))
            path = runtime.service.database
            try:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(len(runtime.evaluator_key()), 64)
                disclosure = runtime.disclosure()
                self.assertEqual(disclosure['host'], 'example.invalid')
                self.assertFalse(disclosure['executesCode'])
                self.assertNotIn('test-key', str(disclosure))
                runtime.settings = lambda: ('deepseek', 'test', 'https://user:password@example.invalid/api?key=hidden', 'secret')
                disclosure = runtime.disclosure()
                self.assertEqual(disclosure['host'], 'example.invalid')
                for sensitive in ('password', 'hidden', 'secret'):
                    self.assertNotIn(sensitive, str(disclosure))
                with connect(path) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM material_jobs').fetchone()[0], 0)
            finally:
                runtime.close()
            runtime = SubmissionRuntime(root, root, pairing, settings, lambda *args: self.fail('重启不能调用AI'))
            runtime.close()

    def test_unsafe_existing_storage_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'submissions').mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                SubmissionRuntime(root, root, None, None, None)
