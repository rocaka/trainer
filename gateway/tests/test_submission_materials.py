import tempfile
import unittest
from pathlib import Path

from submission_materials import prepare_materials
from submission_snapshot import SnapshotBlocked
from test_learning_loop import exercise


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.file = self.root / 'main.py'
        self.file.write_text('print(1)', encoding='utf-8')
        self.contract = exercise()
        self.contract['submissionSpec']['code'] = True
        self.contract['requiredFiles'] = ['main.py']
        self.calls = 0

    def guard(self, paths):
        self.calls += 1
        return {'valid': True, 'authorizedPaths': ['main.py'], 'dirtyPaths': [], 'buffersFresh': True}

    def prepare(self, **kwargs):
        return prepare_materials(self.contract, self.root, answer='说明', guard=self.guard, **kwargs)

    def test_same_material_same_fingerprint(self):
        a, b = self.prepare(), self.prepare()
        self.assertEqual(a['materialFingerprint'], b['materialFingerprint'])
        self.assertEqual(self.calls, 4)
        self.assertEqual(a['snapshot']['files'][0]['content'], 'print(1)')

    def test_content_revision_and_report_change_identity(self):
        a = self.prepare()['materialFingerprint']
        self.file.write_text('print(2)', encoding='utf-8')
        b = self.prepare()['materialFingerprint']
        self.contract['revision'] += 1
        c = self.prepare()['materialFingerprint']
        d = self.prepare(report='运行结果')['materialFingerprint']
        self.assertEqual(len({a, b, c, d}), 4)

    def test_revocation_after_read_discards_result(self):
        def revoke(paths):
            state = self.guard(paths)
            state['valid'] = self.calls == 1
            return state
        with self.assertRaises(SnapshotBlocked):
            prepare_materials(self.contract, self.root, answer='说明', guard=revoke)
        self.assertEqual(self.calls, 2)

    def test_dirty_blocks_before_read(self):
        self.file.unlink()
        def dirty(paths):
            state = self.guard(paths)
            state['dirtyPaths'] = paths
            return state
        with self.assertRaisesRegex(SnapshotBlocked, 'unsaved_files'):
            prepare_materials(self.contract, self.root, answer='说明', guard=dirty)

    def test_missing_file_blocks_whole_submission(self):
        self.file.unlink()
        with self.assertRaises(SnapshotBlocked):
            self.prepare()

    def test_text_only_does_not_require_disk_root(self):
        self.contract = exercise()
        result = self.prepare()
        self.assertEqual(result['snapshot']['files'], [])
