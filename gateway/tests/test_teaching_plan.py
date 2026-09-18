import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from teaching_plan import build_plan, validate_plan, FIELDS, IncompletePlanError, parse_plan_response, audit_coverage

class TeachingPlanTests(unittest.TestCase):
    def test_practice_contract_binds_course_and_requires_every_criterion(self):
        from teaching_plan import practice_contracts
        from submission_target import resolve_target
        plan = self.practice_plan()
        contracts = practice_contracts(plan['lessons'], 'a' * 64, 'project-practice')
        contract = contracts[0]
        self.assertFalse(contract['submissionSpec']['answer'])
        self.assertEqual(contract['verificationRequirement'], 'static_review')
        self.assertEqual(contract['passRule']['minimumScore'], len(contract['rubric']))
        resolved = resolve_target(contracts, mode='project-practice', plan_id='a' * 64,
                                  lesson_id=contract['lessonId'], task_id=contract['taskSource']['taskId'], revision=1)
        self.assertEqual(resolved, contract)
        self.assertEqual(practice_contracts(plan['lessons'], 'a' * 64, 'project-import'), [])
        other = practice_contracts(plan['lessons'], 'b' * 64, 'project-practice')
        self.assertNotEqual(other[0]['exerciseId'], contract['exerciseId'])

    def practice_plan(self):
        plan = self.plan()
        for lesson in plan['lessons']:
            lesson['practiceTask'] = {'prompt': '实现本课函数', 'requiredFiles': ['src/main.py'], 'acceptance': ['返回预期结果']}
        return plan

    def test_invalid_practice_file_rejected(self):
        plan = self.practice_plan()
        plan['lessons'][0]['practiceTask']['requiredFiles'] = ['../secret']
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_practice_schema_does_not_change_legacy_schema(self):
        from teaching_plan import module_schema, PLAN_SCHEMA
        self.assertIn('practiceTask', module_schema('project-practice')['properties']['lessons']['items']['required'])
        self.assertNotIn('practiceTask', PLAN_SCHEMA['properties']['lessons']['items']['required'])

    def test_legacy_project_brief_is_classified_without_regeneration(self):
        plan = self.plan()
        lesson = plan['lessons'][0]
        lesson['title'] = '定义目标与安全边界'
        lesson['explanation'] = '## 最小可交付版本\n\n先确认学习者假设和安全边界。'
        validated = validate_plan(plan)
        self.assertEqual(validated['lessons'][0]['contentType'], 'project-brief')
        self.assertEqual(validated['lessons'][1]['contentType'], 'concept')

    def test_new_schema_requires_explicit_content_type(self):
        from teaching_plan import PLAN_SCHEMA
        item = PLAN_SCHEMA['properties']['lessons']['items']
        self.assertIn('contentType', item['required'])
        self.assertEqual(set(item['properties']['contentType']['enum']),
                         {'project-brief', 'concept', 'implementation', 'verification'})

    def test_submission_policy_saved_cached_and_previewed(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            previews = []
            with patch('teaching_plan.publish_partial', side_effect=previews.append):
                result = build_plan('source', {'SKILL.md': 'material'}, 'rules', directory,
                                    lambda *args: self.plan(), generation_mode='project-import')
            policy = {'version': 1, 'mode': 'project-import', 'primaryRole': 'coach-exercise'}
            self.assertEqual(result['submissionPolicy'], policy)
            self.assertTrue(previews)
            self.assertTrue(all(p['submissionPolicy'] == policy for p in previews))
            saved = json.loads((Path(directory) / (result['planId'] + '.json')).read_text())
            self.assertEqual(saved['submissionPolicy'], policy)
            cached = build_plan('source', {'SKILL.md': 'material'}, 'rules', directory,
                                lambda *args: self.fail('缓存不得重复调用生成'), generation_mode='project-import')
            self.assertTrue(cached['cached'])
            other = build_plan('source', {'SKILL.md': 'material'}, 'rules', directory,
                               lambda *args: self.practice_plan(), generation_mode='project-practice')
            self.assertNotEqual(result['planId'], other['planId'])
            self.assertEqual(other['submissionPolicy']['primaryRole'], 'course-task')

    def test_lesson_prompt_includes_readability_contract(self):
        def generate(prompt, schema):
            for required in ('## 标题', 'Markdown 表格', '**加粗文字**', '真实语言'):
                self.assertIn(required, prompt)
            return self.plan()
        with tempfile.TemporaryDirectory() as directory:
            build_plan('format', {'SKILL.md': 'material'}, 'rules', directory, generate)

    def test_coverage_does_not_confuse_partial_with_complete(self):
        lessons = [{**item, 'id': 'm0-' + item['id']} for item in self.plan()['lessons']]
        report = audit_coverage({'moduleTitles': ['基础', '实战'], 'lessons': lessons})
        self.assertEqual(report['coveredModules'], 1)
        self.assertEqual(report['status'], 'incomplete')
        lessons.extend([{**item, 'id': 'm1-' + item['id']} for item in self.plan()['lessons']])
        report = audit_coverage({'moduleTitles': ['基础', '实战'], 'lessons': lessons})
        self.assertEqual(report['status'], 'structure-passed')
        lessons[0]['exercise'] = ''
        self.assertEqual(audit_coverage({'moduleTitles': ['基础', '实战'], 'lessons': lessons})['status'], 'incomplete')

    def test_first_module_published_before_next_module_runs(self):
        snapshots = []
        calls = []
        def generate(*args):
            calls.append(1)
            if len(calls) == 2:
                self.assertEqual(len(snapshots), 1)
                self.assertEqual(len(snapshots[0]['lessons']), 3)
                raise RuntimeError('provider failed')
            return self.plan()
        with tempfile.TemporaryDirectory() as directory, patch('teaching_plan.publish_partial', side_effect=snapshots.append):
            with self.assertRaises(RuntimeError):
                build_plan('partial', {'SKILL.md': 'intro', 'project/source/a.md': 'source'}, 'rules', directory, generate)
            self.assertEqual(snapshots[0]['coverageStatus'], 'generating')
            self.assertEqual(snapshots[0]['moduleCount'], 2)

    def test_full_outline_generates_every_module_and_resumes(self):
        calls = []
        def generate(prompt, schema):
            calls.append(schema)
            if 'modules' in schema['properties']:
                return {'modules': [{'title': f'模块{i}', 'scope': '实现与验证'} for i in range(4)]}
            return self.plan()
        with tempfile.TemporaryDirectory() as directory:
            result = build_plan('full', {'SKILL.md': '完整项目'}, 'rules', directory, generate, outline=True)
            self.assertEqual(result['coverageStatus'], 'outline-generated')
            self.assertEqual(len(result['lessons']), 12)
            self.assertEqual(len(result['moduleTitles']), 4)
            restored = build_plan('full', {'SKILL.md': '完整项目'}, 'rules', directory, generate, outline=True)
            self.assertTrue(restored['cached'])
            self.assertEqual(len(calls), 5)

    def test_truncation_and_malformed_arguments_are_retryable(self):
        for reason, arguments in [('length', '{}'), ('stop', '{"lessons":"')]:
            with self.assertRaises(IncompletePlanError):
                parse_plan_response({'choices': [{'finish_reason': reason, 'message': {'tool_calls': [{'function': {'arguments': arguments}}]}}]})

    def test_split_checkpoints_resume_without_repeating_completed_child(self):
        calls = []
        def generate(prompt, schema):
            calls.append(prompt)
            if len(calls) in (1, 4):
                raise IncompletePlanError('length')
            if len(calls) == 3:
                raise TimeoutError('interrupted')
            return self.plan()
        with tempfile.TemporaryDirectory() as directory:
            docs = {'SKILL.md': '教学内容' * 300}
            with self.assertRaises(TimeoutError):
                build_plan('test.split', docs, 'rules', directory, generate)
            result = build_plan('test.split', docs, 'rules', directory, generate)
            self.assertEqual(len(calls), 5)
            self.assertEqual(len(result['lessons']), 6)
            self.assertEqual(len({x['id'] for x in result['lessons']}), 6)

    def test_retries_are_bounded_and_no_invalid_plan_saved(self):
        calls = []
        def generate(*args):
            calls.append(1)
            raise IncompletePlanError('length')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, '断点继续'):
                build_plan('test', {'SKILL.md': 'x' * 4000}, 'rules', directory, generate)
            self.assertEqual(len(calls), 3)
            self.assertEqual(list(Path(directory).glob('*.json')), [])

    def test_corrupt_aggregate_rebuilt_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_plan('test', {'SKILL.md': 'material'}, 'rules', directory, lambda *_: self.plan())
            (Path(directory) / (result['planId'] + '.json')).write_text('{broken')
            restored = build_plan('test', {'SKILL.md': 'material'}, 'rules', directory, lambda *_: self.fail('Valid checkpoint should be reused'))
            self.assertEqual(len(restored['lessons']), 3)
            self.assertFalse(restored['cached'])

    def test_source_modules_resume_after_interruption(self):
        calls = []
        def generate(prompt, schema):
            calls.append(prompt)
            if len(calls) == 2:
                raise RuntimeError('interrupted')
            return self.plan()
        with tempfile.TemporaryDirectory() as directory:
            documents = {'SKILL.md': '项目教学', 'project/source/main.py.md': 'def main(): return 1'}
            with self.assertRaises(RuntimeError):
                build_plan('test.project', documents, 'rules', directory, generate)
            result = build_plan('test.project', documents, 'rules', directory, generate)
            self.assertEqual(len(calls), 3)
            self.assertEqual(result['moduleCount'], 2)
            self.assertEqual(len(result['lessons']), 6)

    def plan(self):
        return {'lessons': [{**{field: '具体项目内容' for field in FIELDS}, 'id': str(i)} for i in range(3)]}

    def test_missing_or_duplicate_lessons_rejected(self):
        plan = self.plan()
        plan['lessons'][1]['id'] = '0'
        with self.assertRaises(ValueError): validate_plan(plan)
        with self.assertRaises(ValueError): validate_plan({'lessons': []})

    def test_cache_invalidates_for_skill_content_and_rules(self):
        calls = []
        def generate(prompt, schema):
            calls.append(prompt)
            return self.plan()
        with tempfile.TemporaryDirectory() as directory:
            first = build_plan('ai.rag', {'SKILL.md': '检索'}, '规则1', directory, generate)
            second = build_plan('ai.rag', {'SKILL.md': '检索'}, '规则1', directory, generate)
            third = build_plan('ai.rag', {'SKILL.md': '分块'}, '规则1', directory, generate)
            fourth = build_plan('ai.rag', {'SKILL.md': '分块'}, '规则2', directory, generate)
            self.assertTrue(second['cached'])
            self.assertEqual(len(calls), 3)
            self.assertNotEqual(first['planId'], third['planId'])
            self.assertNotEqual(third['planId'], fourth['planId'])
