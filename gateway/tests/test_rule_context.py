import unittest
from unittest.mock import patch
import server


class RuleContextTests(unittest.TestCase):
    def test_uses_active_core_and_shared_practice_contract(self):
        with patch('version_store.resolve_teaching_id', return_value='core.revision'), patch.object(server, 'read_skill', return_value={'documents': {'SKILL.md': 'ACTIVE CORE RULE', 'curriculum-map.yaml': 'ACTIVE MAP'}}) as read:
            context = server.read_curriculum_context()
            self.assertEqual(context['teaching_rules'], 'ACTIVE CORE RULE')
            self.assertEqual(context['curriculum_map'], 'ACTIVE MAP')
            read.assert_called_once_with('core.revision')
            prompt = server.build_prompt({'seed': '项目目标', 'generationMode': 'project-practice'}, context)
            self.assertIn('Generation mode: project-practice', prompt)
            self.assertIn('每一步必须包含', prompt)
            self.assertIn('ACTIVE CORE RULE', prompt)
