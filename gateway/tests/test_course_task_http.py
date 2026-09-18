import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server
from teaching_plan import practice_contracts


class QuietHandler(server.TrainerGatewayHandler):
    def log_message(self, *args):
        pass


class CourseTaskHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'learning-plans').mkdir()
        self.plan_id = 'a' * 64
        lesson = {'id': 'lesson-1', 'objective': '实现函数', 'practiceTask': {
            'prompt': '实现函数', 'requiredFiles': ['main.py'], 'acceptance': ['返回正确值']}}
        self.plan = {'lessons': [lesson], 'submissionContracts': practice_contracts([lesson], self.plan_id, 'project-practice'),
                     'submissionPolicy': {'version': 1, 'mode': 'project-practice', 'primaryRole': 'course-task'}}
        self.path = self.root / 'learning-plans' / (self.plan_id + '.json')
        self.path.write_text(json.dumps(self.plan))
        self.data_patch = patch.object(server, 'DATA', self.root)
        self.env_patch = patch.dict('os.environ', {'TRAINER_GATEWAY_SESSION_TOKEN': 'test-session'})
        self.data_patch.start(); self.env_patch.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join()
        self.env_patch.stop(); self.data_patch.stop(); self.temp.cleanup()

    def request(self, headers=(), suffix='lesson-1'):
        connection = http.client.HTTPConnection(*self.http.server_address, timeout=3)
        try:
            connection.putrequest('GET', '/v1/course-task/' + self.plan_id + '/' + suffix)
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_authorized_read_is_not_submission(self):
        status, body = self.request([('X-Trainer-Session', 'test-session')])
        self.assertEqual(status, 200)
        self.assertFalse(body['submissionEnabled'])
        self.assertEqual(body['contract']['taskSource']['role'], 'course-task')

    def test_missing_wrong_duplicate_and_browser_auth(self):
        self.assertEqual(self.request()[0], 401)
        self.assertEqual(self.request([('X-Trainer-Session', 'wrong')])[0], 401)
        auth = [('X-Trainer-Session', 'test-session')]
        self.assertEqual(self.request(auth + auth)[0], 401)
        self.assertEqual(self.request(auth + [('Origin', 'https://example.com')])[0], 403)

    def test_query_and_missing_lesson_rejected(self):
        auth = [('X-Trainer-Session', 'test-session')]
        for suffix in ('missing', 'lesson-1?x=1', '../lesson-1'):
            self.assertEqual(self.request(auth, suffix)[0], 400)

    def test_mismatched_import_contract_and_malformed_plan_are_rejected(self):
        auth = [('X-Trainer-Session', 'test-session')]
        self.plan['submissionPolicy']['mode'] = 'project-import'
        self.path.write_text(json.dumps(self.plan))
        self.assertEqual(self.request(auth)[0], 400)
        self.path.write_text('[]')
        self.assertEqual(self.request(auth)[0], 400)
