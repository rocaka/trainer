import json
import tempfile
import unittest
from pathlib import Path

from learning_loop import connect
from submission_materials import prepare_materials
import submission_queue as queue
from submission_worker import run_one
from test_learning_loop import exercise


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'jobs.db'
        queue.initialize(self.path)
        self.contract = exercise()
        self.materials = prepare_materials(self.contract, self.temp.name, answer='返回值说明',
                                          guard=lambda _: {'valid': True})
        self.job = queue.enqueue(self.path, 'local', 'click', self.materials['materialFingerprint'], 'b' * 64)
        self.calls = 0

    def evaluate(self, *args):
        self.calls += 1
        return {'scores': {'meaning': 4}, 'quote': '返回值', 'feedback': '正确', 'nextStep': '继续练习'}

    def run_job(self, authorize=lambda _: True, evaluate=None):
        return run_one(self.path, load=lambda _: (self.contract, self.materials),
                       authorize=authorize, evaluate=evaluate or self.evaluate)

    def test_success_commits_result_and_does_not_repeat(self):
        self.assertEqual(self.run_job()['outcome'], 'passed')
        self.assertIsNone(self.run_job())
        self.assertEqual(self.calls, 1)
        with connect(self.path) as db:
            result = json.loads(db.execute('SELECT result FROM material_results').fetchone()[0])
        self.assertEqual(result['method'], 'static_review')

    def test_revoked_consent_does_not_call_provider(self):
        self.assertEqual(self.run_job(authorize=lambda _: False)['status'], 'failed')
        self.assertEqual(self.calls, 0)

    def test_tampered_material_does_not_call_provider(self):
        self.materials['answer'] = '不同内容'
        self.assertEqual(self.run_job()['status'], 'failed')
        self.assertEqual(self.calls, 0)

    def test_fabricated_quote_not_saved(self):
        def invalid(*args):
            result = self.evaluate()
            result['quote'] = '不存在的引用'
            return result
        self.assertEqual(self.run_job(evaluate=invalid)['status'], 'failed')
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM material_results').fetchone()[0], 0)

    def test_transport_failure_not_retried(self):
        def failed(*args):
            self.calls += 1
            raise TimeoutError('sensitive provider details')
        self.assertEqual(self.run_job(evaluate=failed)['status'], 'failed')
        self.assertIsNone(self.run_job(evaluate=failed))
        self.assertEqual(self.calls, 1)
        with connect(self.path) as db:
            code = db.execute('SELECT code FROM submission_failures').fetchone()[0]
        self.assertEqual(code, 'timeout')
        self.assertNotIn('sensitive', code)

    def test_explicit_retry_revalidates_materials_then_completes(self):
        def fail(*args): raise TimeoutError('secret provider response')
        self.run_job(evaluate=fail)
        # Replaying the same submission cannot trigger a second model call.
        replay = queue.enqueue(self.path, 'local', 'click', self.materials['materialFingerprint'],
                               'b' * 64, prepared=(self.contract, self.materials), retry_failed=True)
        self.assertEqual(replay['status'], 'failed')
        retry = queue.enqueue(self.path, 'local', 'new-click', self.materials['materialFingerprint'],
                              'b' * 64, prepared=(self.contract, self.materials), retry_failed=True)
        self.assertEqual(retry['status'], 'queued')
        self.assertEqual(self.run_job()['status'], 'completed')
        duplicate = queue.enqueue(self.path, 'local', 'third-click', self.materials['materialFingerprint'],
                                  'b' * 64, prepared=(self.contract, self.materials), retry_failed=True)
        self.assertEqual(duplicate['status'], 'completed')
        self.assertIsNone(self.run_job())
