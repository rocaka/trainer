import tempfile
import unittest
from pathlib import Path
from cloud_service import AccountService, ServiceError


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.service = AccountService(Path(self.tmp.name)/'cloud.db', verify=lambda token: (token, 'user'+token))
        self.a = self.login('1','a'); self.b = self.login('1','b'); self.other = self.login('2','c')

    def login(self, user, device):
        return self.service.handle('/v1/session', {'githubToken':user,'deviceId':device*32,'deviceName':'Mac'})['token']

    def sync(self, token, changes=[]):
        return self.service.handle('/v1/sync', {'changes':changes,'cursor':0}, token)

    def test_two_devices_idempotency_and_account_isolation(self):
        change = {'id':'d'*64,'kind':'profile','baseRevision':0,'payload':{'name':'A','bio':'','avatar':'🌱'}}
        first = self.sync(self.a,[change])
        self.assertEqual(first['records'],self.sync(self.b)['records'])
        self.assertEqual(first['accepted'],self.sync(self.a,[change])['accepted'])
        self.assertEqual([],self.sync(self.other)['records'])
        changed = {**change,'payload':{**change['payload'],'name':'B'}}
        self.assertEqual(['d'*64],self.sync(self.b,[changed])['conflicts'])
        self.assertEqual('A',self.sync(self.a)['records'][0]['payload']['name'])

    def test_revocation_and_deletion_are_user_scoped(self):
        self.service.handle('/v1/devices/revoke', {'deviceId':'c'*32},self.a)
        self.assertEqual([],self.sync(self.other)['records'])
        self.service.handle('/v1/devices/revoke', {'deviceId':'b'*32},self.a)
        with self.assertRaises(ServiceError): self.sync(self.b)
        self.service.handle('/v1/account/delete', {'confirmed':True},self.a)
        with self.assertRaises(ServiceError): self.sync(self.a)
        self.assertEqual([],self.sync(self.other)['records'])

    def test_answer_body_rejected(self):
        value = {'id':'e'*64,'kind':'evidence','baseRevision':0,'payload':{'note':'private source code'}}
        with self.assertRaises(ServiceError): self.sync(self.a,[value])
