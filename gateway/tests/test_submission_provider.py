import json
import unittest
from submission_provider import evaluate, evaluator_key
from test_learning_loop import exercise


class ProviderTests(unittest.TestCase):
    def test_config_binding_and_structured_response(self):
        config = ('deepseek', 'test-model', 'https://example.invalid', 'test-secret')
        materials = {'answer': '说明', 'report': '', 'snapshot': {'files': []}}
        def send(provider, endpoint, secret, body):
            self.assertNotIn('test-secret', json.dumps(body))
            self.assertIn('静态', body['messages'][0]['content'])
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
                {'function': {'name': 'assess_submission', 'arguments': json.dumps({'scores': {'meaning': 1}, 'quote': '说明', 'feedback': '反馈', 'nextStep': '下一步'})}}]}}]}
        result = evaluate(exercise(), materials, evaluator_key(*config[:3]), settings=lambda: config, send=send)
        self.assertEqual(result['quote'], '说明')
        with self.assertRaises(ValueError):
            evaluate(exercise(), materials, 'wrong', settings=lambda: config, send=lambda *args: self.fail('配置变化不得外发'))

    def test_truncated_response_rejected(self):
        config = ('deepseek', 'model', 'https://example.invalid', 'secret')
        with self.assertRaises(ValueError):
            evaluate(exercise(), {'answer': '说明', 'report': '', 'snapshot': {'files': []}},
                     evaluator_key(*config[:3]), settings=lambda: config,
                     send=lambda *args: {'choices': [{'finish_reason': 'length'}]})
