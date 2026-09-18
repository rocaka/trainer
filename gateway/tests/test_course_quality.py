import unittest
from course_quality import audit_course_quality


class CourseQualityTests(unittest.TestCase):
    def lesson(self, **changes):
        value = {'id': 'go-1', 'language': 'Go', 'code': 'package main\nfunc main() {}',
                 'exercise': '修改 main 函数并比较输出结果',
                 'practiceTask': {'prompt': '修改入口', 'requiredFiles': ['main.go'], 'acceptance': ['包含 main']}}
        value.update(changes)
        return value

    def test_matching_language_exercise_and_files_pass(self):
        report = audit_course_quality([self.lesson()], {'mode': 'project-practice', 'primaryRole': 'course-task'})
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['passed'], report['total'])

    def test_mismatched_example_vague_exercise_and_extension_are_reported(self):
        lesson = self.lesson(code='def main():\n  pass', exercise='理解一下',
                             practiceTask={'prompt': '做题', 'requiredFiles': ['main.py'], 'acceptance': ['完成']})
        report = audit_course_quality([lesson], {'mode': 'project-practice', 'primaryRole': 'course-task'})
        self.assertEqual(report['status'], 'needs-review')
        self.assertEqual([x['kind'] for x in report['findings'] if x['status'] == 'needs-work'],
                         ['language', 'exercise', 'submission'])

    def test_import_has_no_false_course_submission_requirement(self):
        report = audit_course_quality([self.lesson(practiceTask=None)],
                                      {'mode': 'project-import', 'primaryRole': 'coach-exercise'})
        self.assertEqual(report['total'], 2)

