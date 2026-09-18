import unittest
import test_workspace_grants as fixtures
from source_grants import SourceGrants


class SourceGrantTests(unittest.TestCase):
    pair = fixtures.WorkspaceGrantTests.pair

    def setUp(self):
        fixtures.WorkspaceGrantTests.setUp(self)
        self.binding = self.grants.request(self.token, str(self.project), 'a' * 64)['id']
        self.grants.approve(self.binding)
        self.sources = SourceGrants(self.grants)

    def test_metadata_alone_cannot_read(self):
        self.assertFalse(self.sources.authorize(self.token, 'missing', ['main.go']))

    def test_explicit_scope_restart_and_revoke(self):
        grant = self.sources.approve(self.binding, ['main.go', 'test.go'])
        self.assertTrue(SourceGrants(self.grants).authorize(self.token, grant, ['main.go']))
        self.assertFalse(self.sources.authorize(self.token, grant, ['other.go']))
        self.assertFalse(self.sources.authorize(self.pair(), grant, ['main.go']))
        self.sources.revoke(grant)
        self.assertFalse(self.sources.authorize(self.token, grant, ['main.go']))

    def test_parent_revocation_invalidates_read_consent(self):
        grant = self.sources.approve(self.binding, ['main.go'])
        self.grants.revoke(self.binding)
        self.assertFalse(self.sources.authorize(self.token, grant, ['main.go']))

    def test_invalid_scope_not_approved(self):
        for paths in [[], ['../main.go'], ['.env'], ['*'], ['src/*.go']]:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.sources.approve(self.binding, paths)

    def test_revoked_binding_cannot_get_new_consent(self):
        self.grants.revoke(self.binding)
        with self.assertRaises(ValueError): self.sources.approve(self.binding, ['main.go'])
