import json
import tempfile
import unittest
from pathlib import Path

from course_submission import CourseSubmission
from teaching_plan import practice_contracts
from submission_storage import private_database
from submission_consent import SubmissionConsent
from submission_worker import run_one
import submission_queue as queue


class CourseSubmissionTests(unittest.TestCase):
    def test_import_coach_task_multifile_review(self):
        from course_task_lookup import prepare_task
        path = self.root / 'learning-plans' / (self.plan_id + '.json')
        plan = json.loads(path.read_text())
        task = plan['lessons'][0].pop('practiceTask')
        plan.pop('submissionContracts')
        plan['submissionPolicy'] = {'version': 1, 'mode': 'project-import', 'primaryRole': 'coach-exercise'}
        plan['lessons'][0]['exercise'] = '修改 main.py 和 helper.py，使入口输出一'
        path.write_text(json.dumps(plan))
        prepare_task(self.root, {'planId': self.plan_id, 'lessonId': 'lesson-1'}, lambda *_: task)
        self.expected_role = 'coach-exercise'
        self.test_multifile_submit_dedup_evaluate_and_read()

    def test_prepared_legacy_course_uses_multifile_submission_and_review(self):
        from course_task_lookup import prepare_task
        path = self.root / 'learning-plans' / (self.plan_id + '.json')
        plan = json.loads(path.read_text())
        task = plan['lessons'][0].pop('practiceTask')
        plan.pop('submissionContracts')
        plan['submissionPolicy']['mode'] = 'course'
        plan['lessons'][0]['exercise'] = '在 main.py 和 helper.py 中完成输出值练习'
        path.write_text(json.dumps(plan))
        prepare_task(self.root, {'planId': self.plan_id, 'lessonId': 'lesson-1'}, lambda *_: task)
        self.test_multifile_submit_dedup_evaluate_and_read()

    def test_live_pairing_buffers_and_source_grants_feed_submission(self):
        from pairing_service import PairingService
        from extension_pairing import Pairings
        store = Pairings(self.root / 'pairing.db')
        pairing = PairingService(store, 'native', self.root / 'learning-plans')
        request = store.request('test extension')
        store.approve(request['id'], request['code'])
        token = store.redeem(request['id'], request['claimSecret'])
        binding = pairing.workspaces.request(token, str(self.workspace), self.plan_id)['id']
        pairing.workspaces.approve(binding)
        source = pairing.sources.approve(binding, ['main.py', 'helper.py'])
        service = CourseSubmission.from_pairing(self.root, self.db, pairing)
        def submit(key):
            return service.submit(learner='local', plan_id=self.plan_id, lesson_id='lesson-1',
                                  binding_id=binding, request_key=key, evaluator_key='b' * 64)
        with self.assertRaises(ValueError):
            submit('no-status')
        payload = {'token': token, 'bindingId': binding, 'dirtyPaths': ['main.py'],
                   'untitled': 0, 'trusted': True, 'local': True}
        def report():
            self.assertEqual(pairing.handle('POST', '/v2/pairings/workspaces/buffers', '', json.dumps(payload).encode())[0], 200)
        report()
        with self.assertRaises(ValueError):
            submit('dirty')
        payload['dirtyPaths'] = []
        report()
        self.assertEqual(submit('saved')['status'], 'queued')
        # No special checkId/confirmation is required for continuously synced state.
        self.assertEqual(pairing.buffer_checks, {})
        snapshot = pairing.latest_buffers(binding)
        snapshot['dirtyPaths'].append('tampered')
        self.assertEqual(pairing.latest_buffers(binding)['dirtyPaths'], [])
        pairing.sources.revoke(source)
        with self.assertRaises(ValueError):
            submit('revoked')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        (self.workspace / 'main.py').write_text('print(1)')
        (self.workspace / 'helper.py').write_text('value = 1')
        private = self.root / 'private'
        private.mkdir(mode=0o700)
        self.db = private_database(private)
        queue.initialize(self.db)
        plans = self.root / 'learning-plans'
        plans.mkdir()
        self.plan_id = 'a' * 64
        lesson = {'id': 'lesson-1', 'objective': '完成实现', 'practiceTask': {
            'prompt': '输出值', 'requiredFiles': ['main.py', 'helper.py'], 'acceptance': ['输出一']}}
        plan = {'lessons': [lesson], 'submissionContracts': practice_contracts([lesson], self.plan_id, 'project-practice'),
                'submissionPolicy': {'version': 1, 'mode': 'project-practice', 'primaryRole': 'course-task'}}
        (plans / (self.plan_id + '.json')).write_text(json.dumps(plan))
        self.dirty = []
        self.bound_plan = self.plan_id
        self.completions = []
        self.service = CourseSubmission(self.root, self.db, self.binding,
            record_completion=lambda *values: self.completions.append(values))

    def binding(self, learner, binding_id):
        if learner != 'local' or binding_id != 'binding':
            raise ValueError('未关联')
        return {'planId': self.bound_plan, 'root': self.workspace,
                'guard': lambda paths: {'valid': True, 'authorizedPaths': ['main.py', 'helper.py'],
                                       'dirtyPaths': self.dirty, 'buffersFresh': True}}

    def submit(self, key='click'):
        return self.service.submit(learner='local', plan_id=self.plan_id, lesson_id='lesson-1',
                                   binding_id='binding', request_key=key, evaluator_key='b' * 64)

    def test_multifile_submit_dedup_evaluate_and_read(self):
        first = self.submit()
        self.assertEqual(self.submit('second-click')['id'], first['id'])
        consent = SubmissionConsent(self.db)
        consent.approve('local', first['id'])
        calls = []
        def evaluate(contract, materials, evaluator):
            calls.append(1)
            self.assertEqual(len(materials['snapshot']['files']), 2)
            return {'scores': {'criterion-1': 1}, 'quote': 'print(1)', 'feedback': '静态结构符合要求', 'nextStep': '请运行验证'}
        run_one(self.db, load=lambda job: queue.load_materials(self.db, job), authorize=consent.authorize, evaluate=evaluate)
        self.assertEqual(self.service.status('local', first['id'])['assessment']['outcome'], 'passed')
        self.assertEqual(self.completions[-1], ('local', self.plan_id, 'lesson-1', first['id'], getattr(self, 'expected_role', 'course-task')))
        sidebar = self.service.binding_status('binding')
        self.assertEqual(sidebar, {'id': first['id'], 'status': 'completed', 'outcome': 'passed'})
        self.assertIsNone(self.service.binding_status('other-binding'))
        self.service.delete_archived_materials('local')
        self.assertEqual(self.service.binding_status('binding'), sidebar)
        self.assertIsNone(run_one(self.db, load=None, authorize=None, evaluate=None))
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            self.service.status('other', first['id'])

    def test_dirty_or_wrong_course_never_enqueued(self):
        self.dirty = ['main.py']
        with self.assertRaises(ValueError):
            self.submit()
        self.dirty = []
        self.bound_plan = 'c' * 64
        with self.assertRaises(ValueError):
            self.submit()
        self.assertIsNone(queue.claim_next(self.db))
