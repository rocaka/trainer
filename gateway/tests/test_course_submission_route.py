import io
import json
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock, patch
from course_submission_http import dispatch


class RouteTests(unittest.TestCase):
    def call(self, runtime=None, **changes):
        payload = dict(planId='a'*64, lessonId='lesson', bindingId='binding', requestKey='request',
                       evaluatorKey='b'*64, answer='', consent=True)
        payload.update(changes)
        raw = json.dumps(payload).encode()
        headers = Message()
        headers['X-Trainer-Session'] = 'native'
        headers['Content-Length'] = str(len(raw))
        handler = SimpleNamespace(path='/v1/course-submissions', command='POST', headers=headers,
                                  rfile=io.BytesIO(raw), server=SimpleNamespace(course_submission_runtime=runtime), send_json=Mock())
        with patch.dict('os.environ', {'TRAINER_GATEWAY_SESSION_TOKEN': 'native'}):
            self.assertTrue(dispatch(handler))
        return handler.send_json.call_args.args

    def test_disabled_is_explicit(self):
        self.assertEqual(self.call()[0], 503)

    def test_consent_and_config_gate_before_collection(self):
        runtime = SimpleNamespace(service=Mock(), dispatcher=Mock(), evaluator_key=lambda: 'b'*64)
        self.assertEqual(self.call(runtime, consent=False)[0], 403)
        self.assertEqual(self.call(runtime, evaluatorKey='c'*64)[0], 409)
        runtime.service.submit.assert_not_called()

    def test_single_submit_dispatch_without_paths(self):
        runtime = SimpleNamespace(service=Mock(), dispatcher=Mock(), evaluator_key=lambda: 'b'*64)
        runtime.service.submit.return_value = {'id': 'd'*32, 'status': 'queued'}
        runtime.dispatcher.dispatch.return_value = {'id': 'd'*32, 'status': 'queued'}
        self.assertEqual(self.call(runtime)[0], 202)
        runtime.service.submit.assert_called_once()
        runtime.dispatcher.dispatch.assert_called_once_with('local', 'd'*32)
        self.assertEqual(self.call(runtime, paths=['arbitrary.py'])[0], 400)

    def test_storage_read_and_explicit_cleanup(self):
        runtime = SimpleNamespace(service=Mock(), dispatcher=Mock(), evaluator_key=lambda: 'b'*64)
        runtime.service.material_storage.return_value = {'snapshotCount': 2, 'protectedCount': 1}
        runtime.service.delete_archived_materials.return_value = {'removedCount': 1, 'feedbackPreserved': True}

        status, body = self.call_method(runtime, 'GET', '/v1/course-submissions/storage')
        self.assertEqual(status, 200)
        self.assertEqual(body['snapshotCount'], 2)
        self.assertEqual(self.call_method(runtime, 'DELETE', '/v1/course-submissions/storage',
                                          {'confirm': False, 'preserveFeedback': True})[0], 403)
        status, body = self.call_method(runtime, 'DELETE', '/v1/course-submissions/storage',
                                        {'confirm': True, 'preserveFeedback': True})
        self.assertEqual(status, 200)
        self.assertTrue(body['feedbackPreserved'])
        runtime.service.delete_archived_materials.assert_called_once_with('local')

    def call_method(self, runtime, method, path, payload=None):
        raw = json.dumps(payload or {}).encode()
        headers = Message()
        headers['X-Trainer-Session'] = 'native'
        if method == 'DELETE':
            headers['Content-Length'] = str(len(raw))
        handler = SimpleNamespace(path=path, command=method, headers=headers,
                                  rfile=io.BytesIO(raw), server=SimpleNamespace(course_submission_runtime=runtime), send_json=Mock())
        with patch.dict('os.environ', {'TRAINER_GATEWAY_SESSION_TOKEN': 'native'}):
            self.assertTrue(dispatch(handler))
        return handler.send_json.call_args.args
