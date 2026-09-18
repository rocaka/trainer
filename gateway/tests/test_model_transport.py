import unittest
import json
import subprocess
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from model_transport import normalize_settings, key_service, diagnose, http_failure
from model_transport import request_body, response_body, build_request, native_open, NoRelayRedirect

class TransportTests(unittest.TestCase):
    def test_billing_error_with_401_and_plain_content_type(self):
        body = json.dumps({'error': {'type': 'CreditsError', 'message': 'secret account billing URL'}}).encode()
        error = HTTPError('https://opencode.ai', 401, '', {'Content-Type': 'text/plain'}, BytesIO(body))
        message = http_failure(error)
        self.assertIn('余额或可用额度不足', message)
        self.assertNotIn('secret', message)
        self.assertNotIn('密钥无效', message)

    def test_unknown_or_malformed_error_does_not_echo_body(self):
        for body in (b'private secret', b'[]', b'{"error":"secret"}', b'x' * 20000):
            with self.subTest(body=body[:20]):
                message = http_failure(HTTPError('https://example.com', 401, '', {}, BytesIO(body)))
                self.assertIn('鉴权失败', message)
                self.assertNotIn('secret', message)

    def test_native_transport_keeps_secrets_off_argv_and_reads_final_headers(self):
        request = build_request('custom-chat', 'https://example.com/v1/chat/completions', 'test-secret', {'messages': []})
        result = subprocess.CompletedProcess([], 0, b'{"ok":true}\n200', b'HTTP/1.1 200 Connection established\r\n\r\nHTTP/2 200\r\nContent-Type: application/json\r\nx-request-id: test-id\r\n\r\n')
        with patch('model_transport.subprocess.run', return_value=result) as run:
            with native_open(request, 25) as response:
                self.assertEqual(json.loads(response.read()), {'ok': True})
                self.assertEqual(response.headers['x-request-id'], 'test-id')
        argv = run.call_args.args[0]
        self.assertEqual(argv[:2], ['/usr/bin/curl', '-q'])
        self.assertNotIn('test-secret', str(argv))
        self.assertNotIn('--location', argv)
        self.assertNotIn('--insecure', argv)
        self.assertIn(b'test-secret', run.call_args.kwargs['input'])

    def test_native_refuses_redirect_and_timeout(self):
        request = build_request('custom-chat', 'https://example.com/v1/chat/completions', 'test', {})
        with patch('model_transport.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'\n302', b'HTTP/2 302\r\nLocation: https://other.example\r\n\r\n')):
            with self.assertRaises(HTTPError) as error:
                native_open(request, 25)
            self.assertEqual(error.exception.code, 302)
        with patch('model_transport.subprocess.run', return_value=subprocess.CompletedProcess([], 28, b'', b'private error')):
            with self.assertRaises(TimeoutError): native_open(request, 25)

    def test_go_identity_session_and_parameter_scope(self):
        body = {'model': 'kimi-k2.7-code', 'messages': [], 'temperature': .7}
        with patch('jobs.current_id', return_value=None):
            a = build_request('custom-chat', 'https://opencode.ai/zen/go/v1/chat/completions', 'test', body, 'lesson-a')
            b = build_request('custom-chat', 'https://opencode.ai/zen/go/v1/chat/completions', 'test', body, 'lesson-a')
            c = build_request('custom-chat', 'https://other.example/v1/chat/completions', 'test', body, 'lesson-a')
        self.assertEqual(a.get_header('User-agent'), 'Trainer/0.1.1')
        self.assertEqual(a.get_header('X-opencode-session'), b.get_header('X-opencode-session'))
        self.assertIsNone(c.get_header('X-opencode-session'))
        self.assertEqual(json.loads(a.data)['temperature'], 1)
        self.assertEqual(json.loads(c.data)['temperature'], .7)
        self.assertEqual(body['temperature'], .7)

    def test_job_session_stable_across_modules(self):
        with patch('jobs.current_id', return_value='job-1'):
            a = build_request('custom-chat', 'https://opencode.ai/zen/go/v1/chat/completions', 'test', {}, 'module1')
            b = build_request('custom-chat', 'https://opencode.ai/zen/go/v1/chat/completions', 'test', {}, 'module2')
        self.assertEqual(a.get_header('X-opencode-session'), b.get_header('X-opencode-session'))

    def test_two_stage_responses_diagnostic(self):
        basic = {'output': [{'content': [{'type': 'output_text', 'text': 'OK'}]}]}
        structured = {'status': 'completed', 'output': [{'type': 'function_call', 'name': 'connection_test', 'arguments': '{"ok":true}'}]}
        with patch('model_transport.relay_open', side_effect=[BytesIO(json.dumps(basic).encode()), BytesIO(json.dumps(structured).encode())]) as send:
            result = diagnose({'endpoint': 'https://opencode.ai/zen/go/v1/responses', 'model': 'gpt-5.6-luna'}, 'test')
        self.assertTrue(result['ok'])
        first, second = [call.args[0] for call in send.call_args_list]
        self.assertNotIn('tools', json.loads(first.data))
        self.assertIn('tools', json.loads(second.data))
        self.assertEqual(first.get_header('X-opencode-session'), second.get_header('X-opencode-session'))

    def test_partial_diagnostic_and_no_redirect(self):
        basic = {'choices': [{'message': {'content': 'OK'}}]}
        with patch('model_transport.relay_open', side_effect=[BytesIO(json.dumps(basic).encode()), HTTPError('https://example.com', 400, '', {}, None)]):
            result = diagnose({'endpoint': 'https://example.com/v1/chat/completions', 'protocol': 'chat-completions', 'model': 'test'}, 'test')
        self.assertFalse(result['ok'])
        self.assertIn('普通回复已通过', result['message'])
        self.assertIsNone(NoRelayRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))

    def test_endpoint_normalization_and_key_isolation(self):
        value = normalize_settings({'endpoint': 'https://relay.example/v1', 'model': 'm', 'protocol': 'chat-completions'})
        self.assertEqual(value['endpoint'], 'https://relay.example/v1/chat/completions')
        self.assertEqual(normalize_settings({'endpoint': 'https://relay.example', 'model': 'm'})['endpoint'], 'https://relay.example/v1/responses')
        self.assertNotEqual(key_service(value), key_service({'endpoint': 'https://different.example/v1'}))
        for endpoint in ('http://remote.example', 'https://user:secret@relay.example', 'https://relay.example?key=secret'):
            with self.assertRaises(ValueError):
                normalize_settings({'endpoint': endpoint, 'model': 'm'})
        with self.assertRaises(ValueError):
            normalize_settings({'endpoint': 'https://relay.example/responses', 'protocol': 'chat-completions', 'model': 'm'})

    def test_chat_removes_provider_specific_options(self):
        body = {'thinking': {'type': 'disabled'}, 'messages': [], 'tools': [{'function': {'strict': True}}]}
        result = request_body('custom-chat', body)
        self.assertNotIn('thinking', result)
        self.assertNotIn('strict', result['tools'][0]['function'])
        self.assertIn('thinking', body)

    def test_diagnostic_does_not_echo_upstream_body_or_secret(self):
        settings = {'endpoint': 'https://relay.example', 'model': 'm'}
        with patch('model_transport.relay_open', side_effect=HTTPError(settings['endpoint'], 401, 'secret echo', {}, None)):
            result = diagnose(settings, 'secret-value')
        self.assertFalse(result['ok'])
        self.assertIn('401', result['message'])
        self.assertNotIn('secret', str(result))

    def test_responses_request(self):
        body = {'model': 'test', 'messages': [{'role': 'user', 'content': 'synthetic'}], 'tools': [{'function': {'name': 'submit', 'parameters': {'type': 'object'}}}], 'max_tokens': 200}
        result = request_body('okai', body)
        self.assertEqual(result['tool_choice']['name'], 'submit')
        self.assertEqual(result['max_output_tokens'], 200)
        self.assertFalse(result['store'])
        self.assertNotIn('thinking', result)

    def test_responses_function_result_and_truncation(self):
        result = response_body('okai', {'status': 'completed', 'output': [{'type': 'function_call', 'name': 'submit', 'arguments': '{"ok":true}'}]})
        self.assertEqual(result['choices'][0]['message']['tool_calls'][0]['function']['arguments'], '{"ok":true}')
        self.assertEqual(response_body('okai', {'status': 'incomplete'})['choices'][0]['finish_reason'], 'length')
        with self.assertRaises(ValueError):
            response_body('okai', {'status': 'completed', 'output': []})

    def test_deepseek_unchanged(self):
        body = {'choices': []}
        self.assertIs(response_body('deepseek', body), body)
