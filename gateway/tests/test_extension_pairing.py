import tempfile
import unittest
from pathlib import Path
from extension_pairing import Pairings, PairingError


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = [1000]
        self.store = Pairings(Path(self.temp.name) / 'pairing.db', clock=lambda: self.clock[0])

    def tearDown(self): self.temp.cleanup()

    def test_approval_required_and_single_redemption(self):
        request = self.store.request('VS Code')
        with self.assertRaises(PairingError): self.store.redeem(request['id'], request['claimSecret'])
        self.store.approve(request['id'], request['code'])
        token = self.store.redeem(request['id'], request['claimSecret'])
        self.assertTrue(self.store.authorize(token, 'workspace:bind'))
        self.assertFalse(self.store.authorize(token, 'assessment:write'))
        with self.assertRaises(PairingError): self.store.redeem(request['id'], request['claimSecret'])
        self.store.revoke(token)
        self.assertFalse(self.store.authorize(token, 'workspace:bind'))

    def test_expiry_and_code_attempt_limit(self):
        request = self.store.request('VS Code')
        for _ in range(5):
            with self.assertRaises(PairingError): self.store.approve(request['id'], 'wrong')
        with self.assertRaises(PairingError): self.store.approve(request['id'], request['code'])
        other = self.store.request('VS Code')
        self.clock[0] += 301
        with self.assertRaises(PairingError): self.store.approve(other['id'], other['code'])

    def test_secrets_not_persisted_and_wrong_claim_rejected(self):
        request = self.store.request('VS Code')
        self.store.approve(request['id'], request['code'])
        with self.assertRaises(PairingError): self.store.redeem(request['id'], 'wrong-secret')
        token = self.store.redeem(request['id'], request['claimSecret'])
        raw = self.store.path.read_bytes()
        self.assertNotIn(token.encode(), raw)
        self.assertNotIn(request['claimSecret'].encode(), raw)
        self.clock[0] += 31 * 86400
        self.assertFalse(self.store.authorize(token, 'workspace:bind'))
