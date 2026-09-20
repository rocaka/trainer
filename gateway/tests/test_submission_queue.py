import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import submission_queue as queue
from learning_loop import connect


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'queue.sqlite3'
        queue.initialize(self.path)

    def enqueue(self, key='click', learner='local', fingerprint='a' * 64, evaluator='b' * 64):
        return queue.enqueue(self.path, learner, key, fingerprint, evaluator)

    def test_dedup_and_request_alias_collision(self):
        a, b = self.enqueue(), self.enqueue('second-click')
        self.assertEqual(a['id'], b['id'])
        with self.assertRaises(ValueError):
            self.enqueue('second-click', fingerprint='c' * 64)

    def test_identity_separates_users_and_evaluators(self):
        jobs = [self.enqueue(), self.enqueue(learner='other'), self.enqueue('config', evaluator='c' * 64)]
        self.assertEqual(len({j['id'] for j in jobs}), 3)

    def test_parallel_enqueue_and_single_claim(self):
        with ThreadPoolExecutor(max_workers=4) as workers:
            jobs = list(workers.map(lambda n: self.enqueue(str(n)), range(12)))
            claims = list(workers.map(lambda _: queue.claim_next(self.path), range(12)))
        self.assertEqual(len({j['id'] for j in jobs}), 1)
        self.assertEqual(sum(j is not None for j in claims), 1)

    def test_no_automatic_retry_after_failure(self):
        self.enqueue()
        job = queue.claim_next(self.path)
        queue.finish(self.path, job['id'], job['claim'], 'failed')
        self.assertEqual(self.enqueue('retry-click')['status'], 'failed')
        self.assertIsNone(queue.claim_next(self.path))

    def test_restart_marks_inflight_without_resending_and_rejects_stale_worker(self):
        self.enqueue()
        claimed = queue.claim_next(self.path)
        queue.recover_interrupted(self.path)
        self.assertIsNone(queue.claim_next(self.path))
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT code FROM submission_failures').fetchone()[0], 'interrupted')
        with self.assertRaises(ValueError):
            queue.finish(self.path, claimed['id'], claimed['claim'], 'completed')

    def test_wrong_claim_cannot_finish_or_cancel_running(self):
        self.enqueue()
        job = queue.claim_next(self.path)
        with self.assertRaises(ValueError):
            queue.finish(self.path, job['id'], 'wrong', 'completed')
        self.assertFalse(queue.cancel(self.path, 'local', job['id']))
        queue.finish(self.path, job['id'], job['claim'], 'completed')
        self.assertEqual(self.enqueue('again')['status'], 'completed')

    def test_cancel_checks_owner_and_does_not_requeue(self):
        job = self.enqueue()
        self.assertFalse(queue.cancel(self.path, 'other', job['id']))
        self.assertTrue(queue.cancel(self.path, 'local', job['id']))
        self.assertEqual(self.enqueue('again')['status'], 'cancelled')
        self.assertIsNone(queue.claim_next(self.path))

    def test_manual_cleanup_preserves_feedback_and_active_materials(self):
        completed = self.enqueue('completed', fingerprint='c' * 64)
        running = self.enqueue('running', fingerprint='d' * 64)
        with connect(self.path) as db:
            db.execute('INSERT INTO material_snapshots VALUES(?,?,?)', ('local', 'c' * 64, '{"file":"completed source"}'))
            db.execute('INSERT INTO material_snapshots VALUES(?,?,?)', ('local', 'd' * 64, '{"file":"running source"}'))
        claim = queue.claim_next(self.path, completed['id'])
        queue.complete(self.path, completed['id'], claim['claim'], {'feedback': '保留反馈'})
        queue.claim_next(self.path, running['id'])

        before = queue.material_storage(self.path, 'local')
        self.assertEqual(before['snapshotCount'], 2)
        self.assertEqual(before['protectedCount'], 1)
        result = queue.delete_archived_materials(self.path, 'local')
        self.assertEqual(result['removedCount'], 1)
        self.assertEqual(result['protectedCount'], 1)
        self.assertTrue(result['feedbackPreserved'])
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM material_results').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT fingerprint FROM material_snapshots').fetchone()[0], 'd' * 64)

    def test_cleanup_is_scoped_to_learner(self):
        with connect(self.path) as db:
            db.execute('INSERT INTO material_snapshots VALUES(?,?,?)', ('local', 'e' * 64, '{}'))
            db.execute('INSERT INTO material_snapshots VALUES(?,?,?)', ('other', 'f' * 64, '{}'))
        self.assertEqual(queue.delete_archived_materials(self.path, 'local')['removedCount'], 1)
        self.assertEqual(queue.material_storage(self.path, 'other')['snapshotCount'], 1)
