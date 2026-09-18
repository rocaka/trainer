import json
import tempfile
import unittest
from pathlib import Path
from extension_pairing import Pairings
from pairing_service import PairingService


class BufferTransportTests(unittest.TestCase):
    def test_authenticated_metadata_and_invalid_report_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = Pairings(root / 'pair.db')
            service = PairingService(store, 'native', root)
            request = store.request('test')
            store.approve(request['id'], request['code'])
            token = store.redeem(request['id'], request['claimSecret'])
            binding = service.workspaces.request(token, str(root), 'a' * 64)['id']
            service.workspaces.approve(binding)
            payload = {'token': token, 'bindingId': binding, 'dirtyPaths': [], 'untitled': 0, 'trusted': True, 'local': True}
            def send(value):
                return service.handle('POST', '/v2/pairings/workspaces/buffers', '', json.dumps(value).encode())
            self.assertEqual(send({**payload, 'token': 'wrong'})[0], 401)
            self.assertEqual(send(payload)[0], 200)
            self.assertIn('receivedAt', service.buffer_states[binding])
            self.assertNotIn('token', service.buffer_states[binding])
            check_id = service.begin_buffer_check(binding)
            self.assertIsNone(service.checked_buffers(binding, check_id))
            self.assertEqual(send(payload)[0], 200)
            self.assertIsNone(service.checked_buffers(binding, check_id))
            self.assertEqual(send({**payload, 'checkId': check_id})[0], 200)
            self.assertEqual(service.checked_buffers(binding, check_id)['dirtyPaths'], [])
            newer = service.begin_buffer_check(binding)
            self.assertEqual(send({**payload, 'checkId': check_id})[0], 400)
            self.assertIsNone(service.checked_buffers(binding, newer))
            self.assertEqual(send({**payload, 'dirtyPaths': ['../outside']})[0], 400)
            self.assertNotIn(binding, service.buffer_states)
            service.workspaces.revoke(binding)
            self.assertEqual(send(payload)[0], 401)
