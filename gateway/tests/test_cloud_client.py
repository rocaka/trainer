import tempfile
import unittest
import json
import os
from pathlib import Path
from unittest.mock import patch
import learning_store
import account_store
import cloud_client
from cloud_service import AccountService


class RoundTripTests(unittest.TestCase):
    def test_two_local_databases_download_and_private_answer_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = AccountService(root/'server.db', verify=lambda _: ('1','same-user'))
            previous = learning_store.DATABASE
            previous_data = account_store.DATA
            self.addCleanup(setattr,learning_store,'DATABASE',previous)
            self.addCleanup(setattr,account_store,'DATA',previous_data)
            self.addCleanup(setattr,cloud_client,'SESSION',None)
            def request(path,payload,token='',base=None): return service.handle(path,payload,token)
            with patch.object(cloud_client,'call',request):
                for device in ('a','b'):
                    learning_store.DATABASE = root/(device+'.db')
                    account_store.DATA = root/(device + '-data')
                    account_store.DATA.mkdir()
                    account_store.claim('same-user',github_id='1')
                    token = service.handle('/v1/session',{'githubToken':'x','deviceId':device*32,'deviceName':'Mac'})['token']
                    cloud_client.SESSION = {'token':token,'base':'https://example.invalid','user':'1'}
                    if device == 'a':
                        learning_store.save_profile({'name':'Synced','bio':'','avatar':'🌱'})
                        learning_store.record_evidence({'conceptId':'one','note':'PRIVATE_CODE_AND_TERMINAL','level':1})
                    result = cloud_client.synchronize()
                    self.assertEqual(0,result['conflicts'])
                    with learning_store.connection() as db:
                        self.assertEqual('Synced',db.execute("SELECT name FROM profile WHERE id='local'").fetchone()[0])
                        wire = str([dict(row) for row in db.execute('SELECT * FROM cloud_mirror')])
                        self.assertNotIn('PRIVATE_CODE_AND_TERMINAL',wire)
                        self.assertEqual(2,db.execute('SELECT count(*) FROM cloud_mirror').fetchone()[0])

    def test_course_plan_is_restored_on_second_device_without_workspace_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = AccountService(root/'server.db', verify=lambda _: ('1', 'same-user'))
            previous_db, previous_data = learning_store.DATABASE, account_store.DATA
            previous_env = os.environ.get('TRAINER_DATA_DIR')
            self.addCleanup(setattr, learning_store, 'DATABASE', previous_db)
            self.addCleanup(setattr, account_store, 'DATA', previous_data)
            if previous_env is None: self.addCleanup(os.environ.pop, 'TRAINER_DATA_DIR', None)
            else: self.addCleanup(os.environ.__setitem__, 'TRAINER_DATA_DIR', previous_env)
            self.addCleanup(setattr, cloud_client, 'SESSION', None)
            def request(path, payload, token='', base=None): return service.handle(path, payload, token)
            plan_id = 'a' * 64
            lesson = {'id': 'one', 'title': '变量', 'objective': '理解变量', 'language': 'Go',
                      'code': 'package main', 'explanation': '解释', 'syntax': '语法',
                      'rationale': '原因', 'exercise': '练习', 'reflection': '回讲',
                      'source': 'Trainer', 'contentType': 'concept'}
            plan = {'skillId': 'core', 'title': '跨设备课程', 'lessons': [lesson, {**lesson, 'id': 'two'}, {**lesson, 'id': 'three'}]}
            with patch.object(cloud_client, 'call', request):
                first_data = root/'first-data'; (first_data/'learning-plans').mkdir(parents=True)
                (first_data/'learning-plans'/(plan_id + '.json')).write_text(json.dumps(plan), encoding='utf-8')
                learning_store.DATABASE, account_store.DATA = root/'first.db', first_data
                os.environ['TRAINER_DATA_DIR'] = str(first_data)
                account_store.claim('same-user', github_id='1')
                first_token = service.handle('/v1/session', {'githubToken':'x','deviceId':'a'*32,'deviceName':'Mac'})['token']
                cloud_client.SESSION = {'token': first_token, 'base': 'https://example.invalid', 'user': '1'}
                cloud_client.synchronize()

                second_data = root/'second-data'; second_data.mkdir()
                learning_store.DATABASE, account_store.DATA = root/'second.db', second_data
                os.environ['TRAINER_DATA_DIR'] = str(second_data)
                account_store.claim('same-user', github_id='1')
                second_token = service.handle('/v1/session', {'githubToken':'x','deviceId':'b'*32,'deviceName':'Mac'})['token']
                cloud_client.SESSION = {'token': second_token, 'base': 'https://example.invalid', 'user': '1'}
                cloud_client.synchronize()
                restored = json.loads((second_data/'learning-plans'/(plan_id + '.json')).read_text(encoding='utf-8'))
                self.assertEqual('跨设备课程', restored['title'])
                self.assertTrue((second_data/'saved-courses'/(plan_id + '.json')).is_file())
