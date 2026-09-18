import json
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import backup
import jobs
import assessments
import learning_store
from teaching_review import review_module
from teaching_plan import build_plan, FIELDS


class WorkflowTests(unittest.TestCase):
    def test_text_answer_assesses_exact_question_and_rejects_code_type(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'learning-plans').mkdir()
            key = 'a' * 64
            (root / 'learning-plans' / (key + '.json')).write_text(json.dumps({'lessons': [{'id': 'one', 'language': 'Go'}]}))
            payload = {'planId': key, 'lessonId': 'one', 'answer': '检查错误后返回，避免使用无效结果',
                       'activity': 'coach-text', 'question': 'load 失败后为什么返回？', 'evidenceType': 'reading'}
            prompts = []
            def generate(prompt, schema):
                prompts.append(prompt)
                return {'score': 2, 'quote': '避免使用无效结果', 'feedback': '依据明确', 'nextStep': '解释调用者如何处理'}
            with patch.object(assessments, 'DATA', root), patch.object(learning_store, 'DATABASE', root / 'db.sqlite3'):
                assessments.assess(payload, generate)
                self.assertIn(payload['question'], prompts[0])
                with self.assertRaisesRegex(ValueError, '代码任务'):
                    assessments.assess({**payload, 'evidenceType': 'writing'}, generate)
                self.assertEqual(len(prompts), 1)

    def test_retry_recovers_staged_optimization_before_reading_removed_source(self):
        import server
        record = {'result': {'draft': {'id': 'test'}}, 'pendingId': 'saved', 'source': 'test', 'createdAt': 'now'}
        with patch.object(server, 'current_id', return_value='saved'), patch.object(server, 'read_pending', return_value=record), patch.object(server, 'optimize_pending_candidate') as optimize:
            result = server.run_recipe({'kind': 'optimize-pending', 'payload': {'id': 'removed', 'feedback': ''}})
        self.assertEqual(result['pending']['pendingId'], 'saved')
        optimize.assert_not_called()

    def test_restore_rejects_normalized_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'duplicate.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('backup-manifest.json', '{"format":1}')
                output.writestr('skills/a', 'one')
                output.writestr('skills/./a', 'two')
            with self.assertRaises(ValueError):
                backup.inspect_backup(archive)

    def test_restore_preserves_current_data_and_does_not_resume_paid_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'skills').mkdir()
            (root / 'skills/SKILL.md').write_text('original')
            (root / 'job-history').mkdir()
            (root / 'job-history/one.json').write_text(json.dumps({'status': 'running'}))
            with patch.object(backup, 'DATA', root):
                saved = backup.create_backup()
                (root / 'skills/SKILL.md').write_text('newer')
                restored = backup.restore_backup(saved['path'])
                self.assertEqual((root / 'skills/SKILL.md').read_text(), 'original')
                self.assertEqual((Path(restored['previousDataPath']) / 'skills/SKILL.md').read_text(), 'newer')
                self.assertEqual(json.loads((root / 'job-history/one.json').read_text())['status'], 'paused')

    def test_restore_rejects_zip_traversal_before_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('backup-manifest.json', '{"format":1}')
                output.writestr('../outside', 'bad')
            with patch.object(backup, 'DATA', root), self.assertRaises(ValueError):
                backup.restore_backup(archive)
            self.assertFalse((root / 'restore-history').exists())

    def test_cancel_prevents_followup_and_retains_partial(self):
        started, release = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as folder, patch.object(jobs, 'STORE', Path(folder)), patch.dict(jobs.JOBS, {}, clear=True):
            def work():
                jobs.publish_partial({'lessons': ['ready']})
                started.set(); release.wait(2)
                jobs.checkpoint()
                self.fail('Cancelled task ran another step')
            job = jobs.submit(work, {'kind': 'candidate', 'payload': {}})
            self.assertTrue(started.wait(2))
            jobs.cancel(job['id']); release.set()
            deadline = time.monotonic() + 2
            while jobs.active() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(jobs.active())
            result = jobs.get(job['id'])
            self.assertEqual(result['status'], 'cancelled')
            self.assertEqual(result['partialResult']['lessons'], ['ready'])

    def test_nonplan_restart_pauses_with_recipe(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(jobs, 'STORE', Path(folder)), patch.dict(jobs.JOBS, {}, clear=True):
            job = {'id': 'abc', 'status': 'running', 'recipe': {'kind': 'candidate', 'payload': {'seed': 'test'}}}
            jobs.persist(job)
            jobs.recover(lambda _: self.fail('Nonplan work restarted without user continuing'))
            self.assertEqual(jobs.JOBS['abc']['status'], 'paused')
            self.assertEqual(jobs.JOBS['abc']['recipe'], job['recipe'])

    def test_model_coverage_requires_exact_quote(self):
        result = review_module('module', 'scope', [{'id': '1', 'explanation': 'known text'}], lambda *_: {
            'findings': [{'requirement': 'one', 'status': 'covered', 'lessonId': '1', 'quote': 'invented', 'recommendation': ''}]})
        self.assertEqual(result['findings'][0]['status'], 'uncertain')

    def test_missing_content_repaired_once_and_cached(self):
        reviews = []
        def generate(prompt, schema):
            if 'findings' in schema['properties']:
                reviews.append(1)
                return {'findings': [{'requirement': 'scope', 'status': 'missing' if len(reviews) == 1 else 'covered',
                                     'lessonId': '0', 'quote': 'teaching', 'recommendation': 'add exercise'}]}
            return {'lessons': [{**{key: 'teaching' for key in FIELDS}, 'id': str(i)} for i in range(3)]}
        with tempfile.TemporaryDirectory() as folder:
            result = build_plan('review', {'SKILL.md': 'material'}, 'rules', folder, generate, review=True)
            self.assertEqual(len(result['lessons']), 6)
            self.assertEqual(result['contentReviews'][0]['status'], 'model-reviewed')
            again = build_plan('review', {'SKILL.md': 'material'}, 'rules', folder, lambda *_: self.fail('Should reuse review'), review=True)
            self.assertTrue(again['cached'])

    def test_assessment_replaces_same_lesson_and_rejects_unfounded_quote(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'learning-plans').mkdir()
            key = 'a' * 64
            (root / 'learning-plans' / (key + '.json')).write_text(json.dumps({'lessons': [{'id': 'one', 'language': 'Go'}]}))
            with patch.object(assessments, 'DATA', root), patch.object(learning_store, 'DATABASE', root / 'db.sqlite3'):
                payload = {'planId': key, 'lessonId': 'one', 'answer': 'this is my evidence'}
                response = {'score': 2, 'quote': 'my evidence', 'feedback': 'ok', 'nextStep': 'practice'}
                assessments.assess(payload, lambda *_: response)
                assessments.assess(payload, lambda *_: response)
                self.assertEqual(assessments.language_estimates()['Go'], {'score': 50, 'count': 1})
                with self.assertRaises(ValueError):
                    assessments.assess(payload, lambda *_: {**response, 'quote': 'not in answer'})
