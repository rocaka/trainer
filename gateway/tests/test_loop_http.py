import http.client
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import learning_loop as loop
from learning_loop_service import LearningLoopService
from loop_http import dispatch
from test_learning_loop import exercise
from extension_pairing import Pairings
from pairing_service import PairingService


class Handler(BaseHTTPRequestHandler):
    def do_GET(self): dispatch(self)
    def do_POST(self): dispatch(self)
    def log_message(self, *args): pass


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / 'test.db'
        loop.migrate(path); loop.save_exercise(path, exercise())
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.loop_service = LearningLoopService(path, Path(self.temp.name), 'native-test')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def request(self, method, route, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.request(method, route, body, headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally: connection.close()

    def test_actual_http_submit_read_and_cancel(self):
        headers = {'X-Trainer-Session': 'native-test', 'Content-Type': 'application/json'}
        body = json.dumps({'exerciseId': 'go-reading-1', 'revision': 1, 'answer': '返回计算结果', 'idempotencyKey': 'http-test'})
        status, result = self.request('POST', '/v2/submissions', body, headers)
        self.assertEqual(status, 202)
        route = '/v2/submissions/' + result['id']
        self.assertEqual(self.request('GET', route, headers=headers)[1]['kind'], 'reading')
        self.assertEqual(self.request('POST', route + '/cancel', '{}', headers)[1]['status'], 'cancelled')

    def test_auth_origin_size_and_disabled_gate(self):
        self.assertEqual(self.request('GET', '/v2/submissions/missing')[0], 401)
        headers = {'X-Trainer-Session': 'native-test', 'Origin': 'https://untrusted.example'}
        self.assertEqual(self.request('POST', '/v2/submissions', '{}', headers)[0], 403)
        headers = {'X-Trainer-Session': 'native-test', 'Content-Length': '999999', 'Content-Type': 'application/json'}
        self.assertEqual(self.request('POST', '/v2/submissions', '{}', headers)[0], 413)
        self.server.loop_service = None
        self.assertEqual(self.request('GET', '/v2/exercises/test')[0], 503)

    def test_pairing_public_request_native_approval_over_http(self):
        self.server.pairing_service = PairingService(Pairings(Path(self.temp.name) / 'pair.db'), 'native-test')
        headers = {'Content-Type': 'application/json'}
        status, pair = self.request('POST', '/v2/pairings', '{"name":"VS Code"}', headers)
        self.assertEqual(status, 201)
        payload = json.dumps({'id': pair['id'], 'code': pair['code']})
        self.assertEqual(self.request('POST', '/v2/pairings/approve', payload, headers)[0], 401)
        self.assertEqual(self.request('POST', '/v2/pairings/approve', payload, dict(headers, **{'X-Trainer-Session': 'native-test'}))[0], 200)
        self.assertEqual(self.request('POST', '/v2/pairings', '{"name":"web"}', dict(headers, Origin='https://example.com'))[0], 403)
