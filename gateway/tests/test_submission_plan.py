import unittest

from learning_loop import validate_exercise
from submission_plan import plan_materials
from test_learning_loop import exercise


class SubmissionPlanTests(unittest.TestCase):
    def contract(self):
        value = exercise()
        value['kind'] = 'writing'
        value['submissionSpec']['code'] = True
        value['requiredFiles'] = ['src/main.py', 'tests/test_main.py']
        return value

    def test_selects_only_exercise_files(self):
        value = self.contract()
        plan = plan_materials(value, value['requiredFiles'] + ['unrelated.py'],
                              ['unrelated.py'], buffers_fresh=True, answer='完成说明')
        self.assertTrue(plan['readyForSnapshot'])
        self.assertEqual(plan['paths'], value['requiredFiles'])

    def test_missing_scope_dirty_and_stale_block(self):
        plan = plan_materials(self.contract(), ['src/main.py'], ['src/main.py'])
        self.assertFalse(plan['readyForSnapshot'])
        self.assertEqual({i['code'] for i in plan['issues']},
                         {'authorization_required', 'unsaved_files', 'buffer_status_unavailable', 'missing_answer'})

    def test_no_fallback_to_workspace_or_context_hints(self):
        value = self.contract()
        del value['requiredFiles']
        value['contextHints'] = ['读取整个工作区']
        plan = plan_materials(value, ['main.py'], [], answer='说明')
        self.assertEqual(plan['paths'], [])
        self.assertFalse(plan['readyForSnapshot'])

    def test_rejects_unsafe_ambiguous_and_duplicate_paths(self):
        for paths in [['../a'], ['.env'], ['src/*.py'], ['a', 'a'], [3]]:
            value = self.contract()
            value['requiredFiles'] = paths
            with self.assertRaises(ValueError):
                validate_exercise(value)

    def test_reflection_needs_no_ide(self):
        self.assertTrue(plan_materials(exercise(), [], [], answer='解释')['readyForSnapshot'])

    def test_execution_is_not_faked_by_report(self):
        value = self.contract()
        value['verificationRequirement'] = 'trusted_execution'
        plan = plan_materials(value, value['requiredFiles'], [], buffers_fresh=True, answer='完成')
        self.assertIn('execution_evidence_unavailable', [i['code'] for i in plan['issues']])
