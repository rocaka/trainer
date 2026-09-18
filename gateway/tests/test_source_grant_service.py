import json
import unittest
import test_workspace_grants as fixtures
from pairing_service import PairingService


class SourceServiceTests(unittest.TestCase):
    pair = fixtures.WorkspaceGrantTests.pair

    def setUp(self):
        fixtures.WorkspaceGrantTests.setUp(self)
        self.plans = self.root / 'plans'
        self.plans.mkdir()
        (self.plans / ('a' * 64 + '.json')).write_text(json.dumps({'lessons': [{'title': 'test'}]}))
        self.service = PairingService(self.pairs, 'native-test', self.plans)
        self.binding = self.grants.request(self.token, str(self.project), 'a' * 64)['id']
        self.grants.approve(self.binding)

    def request(self, method, suffix='', payload=None, token='native-test'):
        return self.service.handle(method, '/v2/pairings/source-grants' + suffix, token, json.dumps(payload).encode() if payload is not None else b'')

    def test_only_native_may_list_or_approve_source_access(self):
        for token in ['', self.token]:
            self.assertEqual(self.request('GET', token=token)[0], 401)
            self.assertEqual(self.request('POST', '/approve', {'bindingId': self.binding, 'paths': ['main.go']}, token)[0], 401)

    def test_clear_requires_native_and_revokes_all_without_deleting_project(self):
        self.assertEqual(self.service.handle('POST', '/v2/pairings/clear', self.token, b'{}')[0], 401)
        self.assertTrue(self.grants.authorize(self.token, self.binding))
        status, result = self.service.handle('POST', '/v2/pairings/clear', 'native-test', b'{}')
        self.assertEqual(status, 200)
        self.assertTrue(result['cleared'])
        self.assertFalse(self.grants.authorize(self.token, self.binding))
        self.assertTrue(self.project.exists())
        self.assertTrue((self.plans / ('a' * 64 + '.json')).exists())
        self.assertEqual(self.service.handle('POST', '/v2/pairings/clear', 'native-test', b'{}')[0], 200)

    def test_approve_list_revoke_without_reading_source(self):
        status, value = self.request('POST', '/approve', {'bindingId': self.binding, 'paths': ['main.go']})
        self.assertEqual(status, 201)
        self.assertFalse((self.project / 'main.go').exists())
        grants = self.request('GET')[1]['grants']
        self.assertEqual(grants[0]['paths'], ['main.go'])
        self.assertTrue(grants[0]['valid'])
        self.assertNotIn(self.token, str(grants))
        self.assertEqual(self.request('POST', '/revoke', {'id': value['id']})[0], 200)
        self.assertEqual(self.request('GET')[1]['grants'], [])

    def test_parent_revocation_marks_consent_invalid(self):
        self.request('POST', '/approve', {'bindingId': self.binding, 'paths': ['main.go']})
        self.grants.revoke(self.binding)
        self.assertFalse(self.request('GET')[1]['grants'][0]['valid'])

    def test_invalid_selection_does_not_create_partial_grant(self):
        status, _ = self.request('POST', '/approve', {'bindingId': self.binding, 'paths': ['main.go', '.env']})
        self.assertEqual(status, 400)
        self.assertEqual(self.request('GET')[1]['grants'], [])

    def test_binding_revoked_while_confirmation_open_cannot_approve(self):
        self.grants.revoke(self.binding)
        self.assertEqual(self.request('POST', '/approve', {'bindingId': self.binding, 'paths': ['main.go']})[0], 400)
        self.assertEqual(self.request('GET')[1]['grants'], [])
