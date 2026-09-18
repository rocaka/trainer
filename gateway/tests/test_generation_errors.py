import json
import unittest
from unittest.mock import patch, MagicMock
import server


class GenerationErrorTests(unittest.TestCase):
    def test_text_coach_rejects_coding_turn_before_returning_it(self):
        turn = {'question': 'why', 'options': ['a', 'b'], 'correctIndex': 0,
                'feedback': 'explain', 'reflectionPrompt': 'edit main.go', 'evidenceType': 'writing'}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            'choices': [{'message': {'tool_calls': [{'function': {'arguments': json.dumps(turn)}}]}}]
        }).encode()
        with patch.object(server, 'provider_settings', return_value=('deepseek', 'test', 'https://example.invalid', 'test')), \
             patch.object(server, 'read_skill', return_value={'documents': {}}), \
             patch.object(server, 'urlopen', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'invalid coach turn'):
                server.generate_coach_turn({'lessonTitle': 'test', 'code': 'main()'})

    def test_coach_contract_requires_bounded_evidence_type(self):
        self.assertIn('evidenceType', server.COACH_SCHEMA['required'])
        self.assertEqual(server.COACH_SCHEMA['properties']['evidenceType']['enum'],
                         ['reflection', 'reading', 'transfer'])

    def test_coach_prompt_uses_visible_exercise_as_primary_focus(self):
        prompt = server._build_coach_prompt({
            'lessonTitle': '错误路径',
            'language': 'Go',
            'layer': '拆开看',
            'focusTitle': '观察与练习',
            'focusContent': '预测 chain.json 不存在时 load 应返回什么，并说明风险。',
            'reflectionContext': '解释错误为何必须逐层处理。',
            'code': 'loaded, err := load()\nif err != nil { return err }',
        }, 'core.adaptive-teaching', 'skill rules', 'contract')

        self.assertIn('Current visible learning focus: 观察与练习', prompt)
        self.assertIn('预测 chain.json 不存在时 load 应返回什么', prompt)
        self.assertIn('Focus content (primary source of truth)', prompt)
        self.assertIn('Code reference (supporting material only)', prompt)
        self.assertIn('Do not fall back to a generic code-reading question', prompt)

    def test_coach_prompt_keeps_legacy_clients_compatible(self):
        prompt = server._build_coach_prompt({
            'lessonTitle': '变量', 'code': 'let score = 18'
        }, 'core.adaptive-teaching', '', 'contract')
        self.assertIn('Current visible learning focus: 课程讲解', prompt)
        self.assertIn('let score = 18', prompt)

    def run_generation(self, response=None, error=None):
        result = MagicMock()
        result.__enter__.return_value.read.return_value = json.dumps(response).encode()
        with patch.object(server, 'provider_settings', return_value=('deepseek', 'test', 'https://example.invalid', 'test')), patch.object(server, 'build_prompt', return_value='test'), patch.object(server, 'read_curriculum_context', return_value={}), patch.object(server, 'urlopen', return_value=result, side_effect=error) as request:
            try:
                return server.generate_draft({'seed': 'x' * 50})
            finally:
                self.assertEqual(request.call_args.kwargs['timeout'], 180)

    def test_timeout_is_not_key_error(self):
        with self.assertRaisesRegex(RuntimeError, '超过 180 秒'):
            self.run_generation(error=TimeoutError())

    def test_length_without_tool_is_still_truncation(self):
        with self.assertRaisesRegex(RuntimeError, '长度上限'):
            self.run_generation({'choices': [{'finish_reason': 'length', 'message': {}}]})

    def test_plain_json_object_is_validated(self):
        with patch.object(server, 'validate_draft', return_value={'valid': False}) as validate:
            result = self.run_generation({'choices': [{'finish_reason': 'stop', 'message': {'content': '```json\n{"title":"test"}\n```'}}]})
            validate.assert_called_once_with(result['draft'])
            self.assertEqual(result['draft']['title'], 'test')
            self.assertEqual(result['draft']['ruleProvenance']['generationMode'], 'course')

    def test_empty_choices_actionable(self):
        with self.assertRaisesRegex(RuntimeError, '结构化'):
            self.run_generation({'choices': []})

    def test_truncated_output_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, '长度上限'):
            self.run_generation({'choices': [{'finish_reason': 'length', 'message': {'tool_calls': [{'function': {'arguments': '{'}}]}}]})

    def test_malformed_json_has_actionable_error(self):
        with self.assertRaisesRegex(RuntimeError, '结构不完整'):
            self.run_generation({'choices': [{'finish_reason': 'stop', 'message': {'tool_calls': [{'function': {'arguments': '{'}}]}}]})
