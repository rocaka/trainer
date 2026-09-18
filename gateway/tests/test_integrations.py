import unittest
from integrations import integration_status
from sync_contract import merge, validate_change
from github_insights import aggregate


class IntegrationTests(unittest.TestCase):
    def test_unconfigured_state_never_claims_connection(self):
        result = integration_status({})
        self.assertFalse(result['cloud']['configured'])
        self.assertFalse(result['github']['configured'])

    def test_only_https_cloud_and_github_device_flow_client_id_are_accepted(self):
        bad = integration_status({'TRAINER_CLOUD_ENDPOINT': 'http://example.com', 'TRAINER_GITHUB_CLIENT_ID': 'not a client id'})
        self.assertFalse(bad['cloud']['configured']); self.assertFalse(bad['github']['configured'])
        good = integration_status({'TRAINER_CLOUD_ENDPOINT': 'https://sync.example.com/',
            'TRAINER_GITHUB_CLIENT_ID': 'client_1234'})
        self.assertTrue(good['cloud']['configured']); self.assertTrue(good['github']['configured'])

    def test_sync_merge_is_deterministic_and_learning_records_are_immutable(self):
        base = {'id': 'a' * 32, 'kind': 'profile', 'version': 1, 'updatedAt': '2026-01-01T00:00:00Z', 'payload': {'name': 'A'}}
        newer = {**base, 'version': 2, 'payload': {'name': 'B'}}
        self.assertEqual(merge(base, newer), newer)
        learning = {**base, 'kind': 'evidence'}
        with self.assertRaises(ValueError): merge(learning, {**learning, 'payload': {'note': 'changed'}})
        with self.assertRaises(ValueError): validate_change({})

    def test_github_metrics_exclude_content(self):
        result = aggregate([{'repositoryId': 'r1', 'committedAt': '2026-09-01T09:00:00Z', 'message': 'secret'},
                            {'repositoryId': 'r1', 'committedAt': '2026-09-01T10:00:00Z'}], {'Go': 120})
        self.assertEqual(result['commitCount'], 2)
        self.assertEqual(result['repositoryCount'], 1)
        self.assertNotIn('message', str(result))
        self.assertEqual(result['languages'][0], {'name': 'Go', 'bytes': 120})
