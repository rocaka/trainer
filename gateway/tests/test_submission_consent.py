import tempfile
import unittest
from pathlib import Path

import submission_queue as queue
from submission_consent import SubmissionConsent
from submission_materials import prepare_materials
from submission_worker import run_one
from test_learning_loop import exercise


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.db'
        queue.initialize(self.path)
        self.now = 100
        self.consent = SubmissionConsent(self.path, clock=lambda: self.now)
        contract = exercise()
        materials = prepare_materials(contract, self.temp.name, answer='返回值', guard=lambda _: {'valid': True})
        self.job = queue.enqueue(self.path, 'local', 'click', materials['materialFingerprint'],
                                 'b' * 64, prepared=(contract, materials))

    def test_denied_by_default(self):
        self.assertFalse(self.consent.authorize(queue.claim_next(self.path)))

    def test_explicit_scope_and_expiry(self):
        self.consent.approve('local', self.job['id'], lifetime=10)
        job = queue.claim_next(self.path)
        self.assertTrue(self.consent.authorize(job))
        for key in ('learner', 'fingerprint', 'evaluator_key', 'claim'):
            self.assertFalse(self.consent.authorize({**job, key: 'different'}))
        self.now = 110
        self.assertFalse(self.consent.authorize(job))

    def test_revoke_owner_and_block(self):
        self.consent.approve('local', self.job['id'])
        self.assertFalse(self.consent.revoke('other', self.job['id']))
        self.assertTrue(self.consent.revoke('local', self.job['id']))
        self.assertFalse(self.consent.authorize(queue.claim_next(self.path)))

    def test_wrong_owner_cannot_approve(self):
        with self.assertRaises(ValueError):
            self.consent.approve('other', self.job['id'])

    def test_worker_uses_persisted_consent(self):
        self.consent.approve('local', self.job['id'])
        result = run_one(self.path, load=lambda j: queue.load_materials(self.path, j),
                         authorize=self.consent.authorize,
                         evaluate=lambda *args: {'scores': {'meaning': 4}, 'quote': '返回值',
                                                  'feedback': '正确', 'nextStep': '继续'})
        self.assertEqual(result['outcome'], 'passed')

    def test_invalid_lifetime(self):
        for value in (0, -1, 3601, True):
            with self.assertRaises(ValueError):
                self.consent.approve('local', self.job['id'], lifetime=value)
