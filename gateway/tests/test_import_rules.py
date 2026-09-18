import tempfile
import unittest
from pathlib import Path
from project_import import inspect_project
from server import build_prompt, read_curriculum_context, optimization_mode


class ImportRulesTests(unittest.TestCase):
    def test_optimization_preserves_import_origin_over_category(self):
        self.assertEqual(optimization_mode({'category': 'course', 'ruleProvenance':
                                           {'generationMode': 'project-import'}}), 'project-import')

    def test_optimization_preserves_practice_and_legacy_import(self):
        self.assertEqual(optimization_mode({'ruleProvenance': {'generationMode': 'project-practice'}}), 'project-practice')
        self.assertEqual(optimization_mode({'documents': {'project/summary.md': 'context'}}), 'project-import')

    def test_submission_source_policy_in_generation_prompt(self):
        prompt = build_prompt({'seed': 'test', 'generationMode': 'project-practice'}, read_curriculum_context())
        self.assertIn('SUBMISSION_SOURCE_POLICY_V1', prompt)
        self.assertIn("not the AI coach's latest question", prompt)
        self.assertIn('context, not evidence of learner achievement', prompt)

    def test_import_declares_mode_and_practice_progression(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'main.py').write_text('print("hello")\n')
            result = inspect_project(str(root))
        self.assertEqual(result['generationMode'], 'project-import')
        self.assertIn('独立重建', result['seed'])
        prompt = build_prompt(result, read_curriculum_context())
        self.assertIn('Generation mode: project-import', prompt)
        self.assertIn('PROJECT_IMPORT_PROTOCOL_V1', prompt)

    def test_all_modes_load_same_import_protocol(self):
        context = read_curriculum_context()
        for mode in ['course', 'project-practice', 'project-import']:
            prompt = build_prompt({'seed': 'test', 'generationMode': mode}, context)
            self.assertIn('PROJECT_IMPORT_PROTOCOL_V1', prompt)
            self.assertIn('Generation mode: ' + mode, prompt)
