import tempfile
import unittest
from pathlib import Path
from extension_pairing import Pairings, PairingError
from workspace_grants import WorkspaceGrants


class WorkspaceGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.pairs = Pairings(self.root / 'credentials.db')
        self.grants = WorkspaceGrants(self.pairs)
        self.token = self.pair()

    def pair(self):
        pair = self.pairs.request('test')
        self.pairs.approve(pair['id'], pair['code'])
        return self.pairs.redeem(pair['id'], pair['claimSecret'])

    def test_pending_grant_cannot_authorize_and_token_is_scoped(self):
        grant = self.grants.request(self.token, str(self.project), 'a' * 64)
        self.assertFalse(self.grants.authorize(self.token, grant['id']))
        self.grants.approve(grant['id'])
        self.assertTrue(self.grants.authorize(self.token, grant['id']))
        self.assertFalse(self.grants.authorize(self.pair(), grant['id']))
        self.grants.revoke(grant['id'])
        self.assertFalse(self.grants.authorize(self.token, grant['id']))

    def test_pairing_revocation_invalidates_workspace(self):
        grant = self.grants.request(self.token, str(self.project), 'a' * 64)
        self.grants.approve(grant['id'])
        self.pairs.revoke(self.token)
        self.assertFalse(self.grants.authorize(self.token, grant['id']))
        with self.assertRaises(PairingError):
            self.grants.request(self.token, str(self.project), 'a' * 64)

    def test_unsafe_roots_and_replaced_directory_rejected(self):
        link = self.root / 'link'
        link.symlink_to(self.project, target_is_directory=True)
        for root in [str(link), '/', str(Path.home()), 'relative', str(self.project / '..')]:
            with self.assertRaises(ValueError):
                self.grants.request(self.token, root, 'a' * 64)
        grant = self.grants.request(self.token, str(self.project), 'a' * 64)
        self.grants.approve(grant['id'])
        self.project.rename(self.root / 'old-project')
        self.project.mkdir()
        self.assertFalse(self.grants.authorize(self.token, grant['id']))

    def test_restart_preserves_grant_without_external_send_permission(self):
        grant = self.grants.request(self.token, str(self.project), 'a' * 64)
        self.grants.approve(grant['id'])
        restarted = WorkspaceGrants(self.pairs)
        self.assertTrue(restarted.authorize(self.token, grant['id']))
        self.assertEqual(grant['scope'], 'workspace:metadata')
        self.assertNotIn(self.token, str(restarted.pending()))

    def test_expired_requests_cannot_be_approved(self):
        now = self.pairs.clock()
        self.pairs.clock = lambda: now
        grant = self.grants.request(self.token, str(self.project), 'a' * 64)
        self.pairs.clock = lambda: now + 301
        self.assertEqual(self.grants.pending(), [])
        with self.assertRaises(ValueError):
            self.grants.approve(grant['id'])

    def test_rebinding_same_workspace_supersedes_previous_course(self):
        old = self.grants.request(self.token, str(self.project), 'a' * 64)
        self.grants.approve(old['id'])
        new = self.grants.request(self.token, str(self.project), 'b' * 64)
        self.grants.approve(new['id'])
        self.assertFalse(self.grants.authorize(self.token, old['id']))
        self.assertTrue(self.grants.authorize(self.token, new['id']))
        self.assertEqual([item['plan_id'] for item in self.grants.active()], ['b' * 64])
