import unittest
import test_workspace_grants as fixtures
from source_grants import SourceGrants
from submission_binding import SubmissionBindings


class BindingTests(unittest.TestCase):
    pair = fixtures.WorkspaceGrantTests.pair

    def setUp(self):
        fixtures.WorkspaceGrantTests.setUp(self)
        self.binding = self.grants.request(self.token, str(self.project), 'a' * 64)['id']
        self.grants.approve(self.binding)
        self.sources = SourceGrants(self.grants)
        self.status = {'bindingId': self.binding, 'receivedAt': 100, 'trusted': True,
                       'local': True, 'untitled': 0, 'dirtyPaths': []}
        self.adapter = SubmissionBindings(self.grants, self.sources, lambda _: self.status, clock=lambda: 101)

    def test_metadata_is_not_source_consent(self):
        guard = self.adapter('local', self.binding)['guard']
        self.assertEqual(guard(['main.go'])['authorizedPaths'], [])
        grant = self.sources.approve(self.binding, ['main.go'])
        self.assertEqual(guard(['main.go'])['authorizedPaths'], ['main.go'])
        self.sources.revoke(grant)
        self.assertEqual(guard(['main.go'])['authorizedPaths'], [])

    def test_binding_revoked_after_resolve(self):
        guard = self.adapter('local', self.binding)['guard']
        self.grants.revoke(self.binding)
        with self.assertRaises(ValueError):
            guard(['main.go'])

    def test_missing_stale_future_wrong_binding_and_untitled_block(self):
        guard = self.adapter('local', self.binding)['guard']
        self.assertTrue(guard(['main.go'])['buffersFresh'])
        original = dict(self.status)
        for changes in ({'receivedAt': 90}, {'receivedAt': 102}, {'bindingId': 'other'},
                        {'untitled': 1}, {'trusted': False}, {'local': False}):
            self.status = {**original, **changes}
            self.assertFalse(guard(['main.go'])['buffersFresh'])
        self.status = None
        self.assertFalse(guard(['main.go'])['buffersFresh'])

    def test_other_learner_rejected(self):
        with self.assertRaises(ValueError):
            self.adapter('other', self.binding)
