import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plan_library import saved_plan, maintain_plan, preserve_course_reference
from teaching_plan import FIELDS, validate_plan

class PlanLibraryTests(unittest.TestCase):
    def fixture(self, root):
        key = 'a' * 64
        plan = {'planId': key, 'lessons': [{**{f: 'test' for f in FIELDS}, 'id': str(i)} for i in range(3)]}
        (root / 'learning-plans').mkdir()
        (root / 'job-history').mkdir()
        (root / 'learning-plans' / (key + '.json')).write_text(json.dumps(plan))
        (root / 'job-history/old.json').write_text(json.dumps({'status': 'completed', 'recipe': {'payload': {'skillId': 'go'}}, 'result': {'planId': key}}))
        # Legacy disk fixture intentionally omits contentType; the supported
        # read-time migration adds it without changing any teaching content.
        return validate_plan(plan, aggregate=True)

    def test_open_legacy_without_review_never_calls_model(self):
        import server
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); plan = self.fixture(root)
            with patch.object(server, 'DATA', root), patch.object(server, 'provider_settings', side_effect=AssertionError('model called')):
                result = server.generate_plan({'skillId': 'go', 'mode': 'open'})
            self.assertEqual(result['lessons'], plan['lessons'])
            self.assertTrue(result['cached'])

    def test_missing_course_does_not_generate(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            saved_plan(Path(folder), 'unknown')

    def test_saved_course_catalog_survives_job_history_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); plan = self.fixture(root)
            job = {'status': 'completed', 'createdAt': 'now',
                   'recipe': {'kind': 'plan', 'payload': {'skillId': 'go'}},
                   'result': {'planId': plan['planId']}}
            self.assertTrue(preserve_course_reference(root, job))
            for path in (root / 'job-history').glob('*.json'): path.unlink()
            self.assertEqual(saved_plan(root, 'go')['planId'], plan['planId'])

    def test_review_preserves_lesson_ids_and_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); plan = self.fixture(root)
            result = maintain_plan(root, plan, {}, lambda *_: {'findings': [{'requirement': 'test', 'status': 'covered', 'lessonId': '0', 'quote': 'test', 'recommendation': ''}]})
            self.assertEqual(result['lessons'], plan['lessons'])
            self.assertEqual(result['planId'], plan['planId'])

    def test_supplement_only_appends(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); plan = self.fixture(root)
            def generate(_, schema):
                if 'lessons' in schema['properties']:
                    return {'lessons': plan['lessons'][:1]}
                return {'findings': [{'requirement': 'test', 'status': 'missing', 'lessonId': '', 'quote': '', 'recommendation': 'add'}]}
            result = maintain_plan(root, plan, {}, generate, supplement=True)
            self.assertEqual(result['lessons'][:3], plan['lessons'])
            self.assertEqual(len({x['id'] for x in result['lessons']}), 4)

    def test_failed_recheck_preserves_added_lesson_and_resume_does_not_regenerate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); plan = self.fixture(root)
            calls = []
            def first(_, schema):
                calls.append(schema)
                if len(calls) == 3:
                    raise RuntimeError('network interrupted')
                if 'lessons' in schema['properties']:
                    return {'lessons': plan['lessons'][:1]}
                return {'findings': [{'requirement': 'test', 'status': 'missing', 'lessonId': '', 'quote': '', 'recommendation': 'add'}]}
            with patch('plan_library.current_id', return_value='test-resume'):
                with self.assertRaises(RuntimeError):
                    maintain_plan(root, plan, {}, first, supplement=True)
                stored = json.loads((root / 'learning-plans' / (plan['planId'] + '.json')).read_text())
                self.assertEqual(len(stored['lessons']), 4)
                resumed = []
                def finish(_, schema):
                    resumed.append(schema)
                    self.assertIn('findings', schema['properties'])
                    return {'findings': [{'requirement': 'test', 'status': 'covered', 'lessonId': '0', 'quote': 'test', 'recommendation': ''}]}
                result = maintain_plan(root, stored, {}, finish, supplement=True)
                self.assertEqual(len(resumed), 1)
                self.assertEqual(len(result['lessons']), 4)
                self.assertEqual(result['lessons'][:3], plan['lessons'])

    def test_single_lesson_response_is_valid_for_supplement_only(self):
        from teaching_plan import parse_plan_response, IncompletePlanError
        with tempfile.TemporaryDirectory() as folder:
            plan = self.fixture(Path(folder))
            response = {'choices': [{'message': {'tool_calls': [{'function': {'arguments': json.dumps({'lessons': plan['lessons'][:1]})}}]}}]}
            self.assertEqual(len(parse_plan_response(response, min_lessons=1)['lessons']), 1)
            with self.assertRaises(IncompletePlanError):
                parse_plan_response(response)
