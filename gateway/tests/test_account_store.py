import tempfile
import unittest
from pathlib import Path


class AccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        import learning_store, account_store
        self.learning_store, self.account_store = learning_store, account_store
        self.original = learning_store.DATABASE
        learning_store.DATABASE = Path(self.tmp.name) / 'learning.sqlite3'
        self.addCleanup(setattr, learning_store, 'DATABASE', self.original)
        with learning_store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS profile (id TEXT PRIMARY KEY, name TEXT, bio TEXT, avatar TEXT)')
            db.execute("INSERT INTO profile VALUES ('local','学习者','','🧑‍💻')")

    def test_claim_preserves_learning_data_and_builds_private_sync_outbox(self):
        self.learning_store.record_evidence({'conceptId': 'go.values', 'note': '我理解变量', 'level': 2, 'language': 'Go'})
        result = self.account_store.claim('octocat', {'readingStyle': 'serif'}, '1')
        self.assertTrue(result['signedIn']); self.assertEqual(result['login'], 'octocat')
        self.assertEqual(len(result['devices']), 1); self.assertGreaterEqual(result['pendingChanges'], 3)
        prepared = self.account_store.prepare_sync({'readingStyle': 'rounded'})
        self.assertGreaterEqual(prepared['preparedChanges'], 3)
        self.assertEqual(len(self.learning_store.learner_profile()), 1)

    def test_different_account_cannot_silently_take_over_profile(self):
        self.account_store.claim('first-user', github_id='1')
        with self.assertRaises(ValueError): self.account_store.claim('second-user', github_id='2')
        self.account_store.sign_out()
        with self.assertRaises(ValueError): self.account_store.claim('second-user', github_id='2')
        self.assertTrue(self.account_store.claim('renamed-user', github_id='1')['signedIn'])

    def test_delete_removes_account_queue_but_preserves_learning_records(self):
        self.learning_store.record_evidence({'conceptId': 'one', 'note': 'kept', 'level': 1})
        self.account_store.claim('octocat', github_id='1')
        with self.assertRaises(ValueError): self.account_store.delete_account()
        result = self.account_store.delete_account(True)
        self.assertTrue(result['localLearningDataPreserved']); self.assertFalse(self.account_store.status()['signedIn'])
        self.assertEqual(len(self.learning_store.learner_profile()), 1)


if __name__ == '__main__': unittest.main()
