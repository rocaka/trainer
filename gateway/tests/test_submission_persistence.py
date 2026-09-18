import tempfile
import unittest
from pathlib import Path

from learning_loop import connect
from submission_materials import prepare_materials
import submission_queue as queue
from submission_worker import run_one
from test_learning_loop import exercise


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'private-test.db'
        queue.initialize(self.path)
        self.contract = exercise()
        self.materials = prepare_materials(self.contract, self.temp.name, answer='返回值', guard=lambda _: {'valid': True})

    def enqueue(self, key='click'):
        return queue.enqueue(self.path, 'local', key, self.materials['materialFingerprint'],
                             'b' * 64, prepared=(self.contract, self.materials))

    def test_persist_reopen_evaluate(self):
        self.enqueue()
        queue.initialize(self.path)
        result = run_one(self.path, load=lambda job: queue.load_materials(self.path, job),
                         authorize=lambda _: True,
                         evaluate=lambda *args: {'scores': {'meaning': 4}, 'quote': '返回值',
                                                  'feedback': '正确', 'nextStep': '继续'})
        self.assertEqual(result['outcome'], 'passed')

    def test_request_conflict_rolls_back_snapshot(self):
        self.enqueue()
        self.materials = prepare_materials(self.contract, self.temp.name, answer='新答案', guard=lambda _: {'valid': True})
        with self.assertRaises(ValueError):
            self.enqueue()
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM material_snapshots').fetchone()[0], 1)

    def test_tampered_material_never_enqueued(self):
        self.materials['answer'] = '篡改'
        with self.assertRaises(ValueError):
            self.enqueue()
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM material_jobs').fetchone()[0], 0)

    def test_owner_isolation(self):
        job = self.enqueue()
        with self.assertRaises(ValueError):
            queue.load_materials(self.path, {**job, 'learner': 'other'})

    def test_duplicate_snapshot_not_copied(self):
        self.assertEqual(self.enqueue()['id'], self.enqueue('second')['id'])
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM material_snapshots').fetchone()[0], 1)
