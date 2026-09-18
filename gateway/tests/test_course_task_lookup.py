import json
import tempfile
import unittest
from pathlib import Path
from course_task_lookup import course_task, prepare_task
from teaching_plan import practice_contracts


class LookupTests(unittest.TestCase):
    def test_legacy_course_task_prepared_once_and_bound_to_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'learning-plans'; root.mkdir()
            key = 'b' * 64
            lesson = {'id': 'one', 'objective': '修改高度', 'exercise': '将 main.go 中 height 改为 2'}
            plan = {'lessons': [lesson], 'submissionPolicy': {'version': 1, 'mode': 'course', 'primaryRole': 'course-task'}}
            path = root / (key + '.json'); path.write_text(json.dumps(plan))
            payload = {'planId': key, 'lessonId': 'one'}
            task = {'prompt': '修改高度', 'requiredFiles': ['main.go'], 'acceptance': ['height 是 2']}
            self.assertEqual(prepare_task(directory, payload, lambda *_: task)['task'], task)
            self.assertEqual(prepare_task(directory, payload, lambda *_: self.fail('must reuse'))['task'], task)
            contract = course_task(directory, key, 'one')
            self.assertEqual(contract['taskSource']['mode'], 'course')
            self.assertEqual(contract['requiredFiles'], ['main.go'])
            self.assertEqual(json.loads(path.read_text()), plan)
            plan['lessons'][0]['exercise'] = '其他要求'; path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, '内容已变化'):
                course_task(directory, key, 'one')

    def test_import_registers_separate_coach_exercise(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'learning-plans'; root.mkdir()
            (root / ('b' * 64 + '.json')).write_text(json.dumps({'lessons': [{'id': 'one', 'objective': '理解入口',
                'exercise': '在独立文件中实现一个最小调用'}],
                'submissionPolicy': {'version': 1, 'mode': 'project-import', 'primaryRole': 'coach-exercise'}}))
            task = {'prompt': '新建练习入口', 'requiredFiles': ['trainer-exercises/entry.py'],
                    'acceptance': ['包含一次入口调用']}
            self.assertEqual(prepare_task(directory, {'planId': 'b' * 64, 'lessonId': 'one'}, lambda *_: task)['task'], task)
            contract = course_task(directory, 'b' * 64, 'one')
            self.assertEqual(contract['taskSource'], {
                'mode': 'project-import', 'role': 'coach-exercise',
                'taskId': 'coach-' + __import__('hashlib').sha256(b'one').hexdigest()[:24]})
            self.assertEqual(contract['requiredFiles'], ['trainer-exercises/entry.py'])

    def test_saved_contract_and_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'learning-plans'
            root.mkdir()
            lesson = {'id': 'lesson-1', 'objective': '实现函数', 'practiceTask': {
                'prompt': '实现函数', 'requiredFiles': ['main.py'], 'acceptance': ['返回正确值']}}
            contracts = practice_contracts([lesson], 'a' * 64, 'project-practice')
            plan = {'lessons': [lesson], 'submissionContracts': contracts,
                    'submissionPolicy': {'version': 1, 'mode': 'project-practice', 'primaryRole': 'course-task'}}
            path = root / ('a' * 64 + '.json')
            path.write_text(json.dumps(plan))
            self.assertEqual(course_task(directory, 'a' * 64, 'lesson-1'), contracts[0])
            plan['lessons'][0]['practiceTask']['prompt'] = '替换后的任务'
            path.write_text(json.dumps(plan))
            with self.assertRaises(ValueError):
                course_task(directory, 'a' * 64, 'lesson-1')
            with self.assertRaises(ValueError):
                course_task(directory, '../a', 'lesson-1')
