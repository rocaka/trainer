import unittest
from test_learning_loop import exercise
from submission_target import resolve_target
from learning_loop import validate_exercise


class TargetTests(unittest.TestCase):
    def contract(self, mode, role):
        value = exercise()
        value['taskSource'] = {'mode': mode, 'role': role, 'taskId': 'task-1'}
        return value

    def resolve(self, contracts, mode, **extra):
        return resolve_target(contracts, mode=mode, plan_id='a' * 64,
                              lesson_id='lesson-1', task_id='task-1', revision=1, **extra)

    def test_practice_prefers_course_not_chat(self):
        course = self.contract('project-practice', 'course-task')
        coach = self.contract('project-practice', 'coach-exercise')
        self.assertEqual(self.resolve([course, coach], 'project-practice'), course)

    def test_import_defaults_to_coach(self):
        course = self.contract('project-import', 'course-task')
        coach = self.contract('project-import', 'coach-exercise')
        self.assertEqual(self.resolve([course, coach], 'project-import'), coach)

    def test_explicit_secondary_task_supported(self):
        coach = self.contract('project-practice', 'coach-exercise')
        self.assertEqual(self.resolve([coach], 'project-practice', role='coach-exercise'), coach)

    def test_no_fallback_to_wrong_source_or_legacy(self):
        with self.assertRaises(ValueError):
            self.resolve([exercise(), self.contract('project-practice', 'coach-exercise')], 'project-practice')

    def test_duplicate_binding_blocks(self):
        course = self.contract('project-practice', 'course-task')
        with self.assertRaises(ValueError):
            self.resolve([course, course], 'project-practice')

    def test_unknown_source_rejected(self):
        value = self.contract('unknown', 'course-task')
        with self.assertRaises(ValueError):
            validate_exercise(value)
