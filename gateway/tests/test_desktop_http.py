import io
import json
import os
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch
import desktop_http


class Handler:
    def __init__(self, token='test-session', method='GET', path='/v1/desktop/runtime'):
        self.command, self.path = method, path
        self.headers = Message()
        if token is not None: self.headers['X-Trainer-Session'] = token
        self.rfile = io.BytesIO(b'{}')
    def send_json(self, status, value): self.result = status, value


class RoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, TRAINER_GATEWAY_SESSION_TOKEN='test-session', TRAINER_DESKTOP_ISOLATED='1')
        self.env.start(); self.addCleanup(self.env.stop)

    def call(self, handler):
        self.assertTrue(desktop_http.dispatch(handler, self.tmp.name))
        return handler.result

    def test_missing_and_wrong_token_denied(self):
        for token in (None, 'wrong'):
            self.assertEqual(self.call(Handler(token))[0], 401)

    def test_duplicate_token_denied(self):
        handler = Handler(); handler.headers['X-Trainer-Session'] = 'test-session'
        self.assertEqual(self.call(handler)[0], 401)

    def test_browser_denied(self):
        handler = Handler(); handler.headers['Origin'] = 'http://localhost'
        self.assertEqual(self.call(handler)[0], 403)

    def test_runtime_never_echoes_token(self):
        status, value = self.call(Handler())
        self.assertEqual(status, 200)
        self.assertFalse(value['settingsWritable'])
        self.assertNotIn('test-session', json.dumps(value))

    def test_isolation_blocks_writes_on_windows(self):
        with patch.object(desktop_http.sys, 'platform', 'win32'), patch.object(desktop_http, 'write_windows') as writer:
            self.assertEqual(self.call(Handler(method='POST', path='/v1/desktop/settings'))[0], 403)
            writer.assert_not_called()

    def test_read_isolated_never_reads_real_credentials(self):
        with patch.object(desktop_http, 'read_secret') as reader:
            self.assertEqual(self.call(Handler(path='/v1/desktop/settings'))[0], 200)
            reader.assert_not_called()

    def test_course_catalog_empty_and_invalid_id(self):
        self.assertEqual(self.call(Handler(path='/v1/desktop/courses')), (200, {'courses': []}))
        self.assertEqual(self.call(Handler(path='/v1/desktop/courses/../../private'))[0], 400)

    def test_courses_require_same_native_session(self):
        self.assertEqual(self.call(Handler(token=None, path='/v1/desktop/courses'))[0], 401)

    def test_windows_save_has_no_secret_in_response(self):
        payload = {'endpoint': 'https://example.invalid', 'protocol': 'chat-completions', 'model': 'fixture', 'secret': 'TEST-ONLY', 'consent': True}
        encoded = json.dumps(payload).encode()
        handler = Handler(method='POST', path='/v1/desktop/settings')
        handler.rfile = io.BytesIO(encoded)
        handler.headers['Content-Length'] = str(len(encoded))
        with patch.dict(os.environ, TRAINER_DESKTOP_ISOLATED='0'), patch.object(desktop_http.sys, 'platform', 'win32'), patch.object(desktop_http, 'write_windows') as writer, patch('jobs.list_jobs', return_value=[]):
            status, result = self.call(handler)
            self.assertEqual(status, 200)
            self.assertTrue(result['saved'])
            self.assertNotIn('TEST-ONLY', json.dumps(result))
            writer.assert_called_once()
