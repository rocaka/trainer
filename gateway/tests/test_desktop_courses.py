import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_courses import list_courses, read_course
from teaching_plan import FIELDS


class DesktopCourseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.plans = self.root / 'learning-plans'
        self.plans.mkdir()
        self.key = 'a' * 64
        self.plan = {'title': 'Go 起步', 'workspacePath': '/private/project',
                     'submissionContracts': [{'private': 'metadata'}],
                     'lessons': [{**{f: '教学内容' for f in FIELDS}, 'id': str(i),
                                  'language': 'Go', 'code': 'fmt.Println("hello")',
                                  'source': '/private/source.go'} for i in range(3)]}

    def save(self, key=None, plan=None):
        path = self.plans / ((key or self.key) + '.json')
        path.write_text(json.dumps(self.plan if plan is None else plan), encoding='utf-8')
        return path

    def test_empty_library_does_not_create_data(self):
        data = self.root / 'new-profile'
        self.assertEqual(list_courses(data), {'courses': []})
        self.assertFalse(data.exists())

    def test_lists_complete_courses_without_history_reference(self):
        self.save()
        self.save(self.key + '-part-0')
        self.save('b' * 64, {'lessons': self.plan['lessons'][:1]})
        self.assertEqual(list_courses(self.root), {'courses': [
            {'id': self.key, 'title': 'Go 起步', 'lessonCount': 3}]})

    def test_read_is_canonical_readonly_and_metadata_minimal(self):
        path = self.save()
        before = path.read_bytes()
        result = read_course(self.root, self.key)
        self.assertEqual(result['id'], self.key)
        self.assertEqual(result['lessons'][0]['language'], 'Go')
        self.assertEqual(result['lessons'][0]['contentType'], 'concept')
        self.assertNotIn('source', result['lessons'][0])
        self.assertNotIn('workspacePath', result)
        self.assertNotIn('submissionContracts', result)
        self.assertEqual(path.read_bytes(), before)

    def test_title_uses_stored_course_then_module_before_first_lesson(self):
        self.plan.pop('title')
        self.plan['moduleTitles'] = ['1. Go 入门', '语法']
        self.save()
        self.assertEqual(read_course(self.root, self.key)['title'], '完整课程 · Go 入门')

    def test_practice_contract_is_preserved_separate_from_reflection(self):
        task = {'prompt': '编写程序', 'requiredFiles': ['main.go'], 'acceptance': ['打印 hello']}
        self.plan['lessons'][0]['practiceTask'] = task
        self.save()
        lesson = read_course(self.root, self.key)['lessons'][0]
        self.assertEqual(lesson['practiceTask'], task)
        self.assertEqual(lesson['reflection'], '教学内容')

    def test_html_is_returned_as_text_not_promoted_to_html(self):
        self.plan['lessons'][0]['explanation'] = '<script>alert(1)</script>'
        self.save()
        self.assertEqual(read_course(self.root, self.key)['lessons'][0]['explanation'], '<script>alert(1)</script>')

    def test_invalid_ids_missing_and_corrupt_plan_do_not_leak_paths(self):
        self.save()
        for key in ['../../secrets', '', 'A' * 64, None, 'b' * 64]:
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                read_course(self.root, key)
            self.assertNotIn(str(self.root), str(caught.exception))
        self.save(plan={'lessons': []})
        with self.assertRaises(ValueError):
            read_course(self.root, self.key)

    def test_symlinked_plan_is_not_read(self):
        outside = self.root / 'elsewhere.json'
        outside.write_text(json.dumps(self.plan), encoding='utf-8')
        try:
            (self.plans / (self.key + '.json')).symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation unavailable')
        self.assertEqual(list_courses(self.root), {'courses': []})
        with self.assertRaises(ValueError):
            read_course(self.root, self.key)

    def test_size_and_catalog_limits_are_bounded(self):
        self.save()
        with patch('desktop_courses.MAX_PLAN_BYTES', 10), self.assertRaises(ValueError):
            read_course(self.root, self.key)
        self.save('b' * 64)
        with patch('desktop_courses.MAX_COURSES', 1), self.assertRaises(ValueError):
            list_courses(self.root)


if __name__ == '__main__':
    unittest.main()
