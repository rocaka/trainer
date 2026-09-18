import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch
import jobs
from teaching_plan import FIELDS

class ArchiveTests(unittest.TestCase):
    def test_archive_is_reversible_and_skips_active(self):
        with tempfile.TemporaryDirectory() as root, patch.object(jobs, 'STORE', Path(root)), patch.object(jobs, 'JOBS', {}), patch.object(jobs, 'RUNNING', {'busy'}):
            for key, status in [('done', 'completed'), ('failed', 'failed'), ('busy', 'cancelled'), ('queued', 'queued')]:
                jobs.JOBS[key] = {'id': key, 'status': status, 'createdAt': '', 'result': {'planId': 'keep'}}
                jobs.persist(jobs.JOBS[key])
            self.assertEqual(jobs.archive_jobs()['count'], 2)
            self.assertEqual(len(jobs.list_jobs(archived=True)), 2)
            self.assertEqual(len(jobs.list_jobs(archived=False)), 2)
            self.assertEqual(jobs.get('done')['result']['planId'], 'keep')
            with self.assertRaises(ValueError): jobs.archive_jobs('busy')
            jobs.archive_jobs('done', restore=True)
            self.assertEqual(len(jobs.list_jobs(archived=True)), 1)

    def test_active_plan_job_can_be_reattached(self):
        with tempfile.TemporaryDirectory() as root, patch.object(jobs, 'STORE', Path(root)), patch.object(jobs, 'JOBS', {}), patch.object(jobs, 'RUNNING', {'active'}):
            job = {'id': 'active', 'status': 'running', 'createdAt': '',
                   'recipe': {'kind': 'plan', 'payload': {'skillId': 'go', 'mode': 'upgrade'}},
                   'completed': 2, 'total': 8, 'message': '正在生成'}
            jobs.JOBS['active'] = job
            jobs.persist(job)
            self.assertEqual(jobs.active_plan_job('go')['id'], 'active')
            self.assertIsNone(jobs.active_plan_job('python'))

    def test_permanent_delete_requires_archive_and_preserves_course_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = root / 'job-history'
            plan_id = 'a' * 64
            plan = {'planId': plan_id, 'lessons': [{**{field: 'test' for field in FIELDS}, 'id': str(index)} for index in range(3)]}
            (root / 'learning-plans').mkdir(parents=True)
            (root / 'learning-plans' / (plan_id + '.json')).write_text(json.dumps(plan))
            job = {'id': 'done', 'status': 'completed', 'createdAt': 'now', 'archived': True,
                   'recipe': {'kind': 'plan', 'payload': {'skillId': 'go', 'mode': 'upgrade'}},
                   'result': plan}
            with patch.object(jobs, 'DATA', root), patch.object(jobs, 'STORE', store), patch.object(jobs, 'JOBS', {'done': job}), patch.object(jobs, 'RUNNING', set()):
                jobs.persist(job)
                result = jobs.delete_jobs('done')
                self.assertEqual(result, {'count': 1, 'preservedCourses': 1})
                self.assertFalse((store / 'done.json').exists())
                self.assertTrue((root / 'saved-courses' / (plan_id + '.json')).exists())
                self.assertNotIn('done', jobs.JOBS)

    def test_permanent_delete_rejects_visible_or_active_jobs(self):
        for job in [
            {'id': 'visible', 'status': 'failed', 'createdAt': ''},
            {'id': 'active', 'status': 'running', 'createdAt': '', 'archived': True},
        ]:
            with self.subTest(job=job['id']), tempfile.TemporaryDirectory() as root, \
                    patch.object(jobs, 'STORE', Path(root)), patch.object(jobs, 'JOBS', {job['id']: job}), \
                    patch.object(jobs, 'RUNNING', {'active'} if job['id'] == 'active' else set()):
                jobs.persist(job)
                with self.assertRaises(ValueError): jobs.delete_jobs(job['id'])
