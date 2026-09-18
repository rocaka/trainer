import unittest
import threading
import test_course_submission as fixtures
from submission_consent import SubmissionConsent
from submission_dispatcher import SubmissionDispatcher


class DispatcherTests(unittest.TestCase):
    setUp = fixtures.CourseSubmissionTests.setUp
    binding = fixtures.CourseSubmissionTests.binding
    submit = fixtures.CourseSubmissionTests.submit

    def test_async_job_specific_dedup(self):
        first = self.submit()
        # Another queued task must not be consumed without explicit dispatch.
        (self.workspace / 'main.py').write_text('print(2)')
        other = self.submit('second')
        entered, release = threading.Event(), threading.Event()
        calls = []
        def evaluate(*args):
            calls.append(1)
            entered.set()
            if not release.wait(3):
                raise TimeoutError('test worker did not release')
            return {'scores': {'criterion-1': 1}, 'quote': 'print(1)', 'feedback': '符合静态要求', 'nextStep': '运行验证'}
        dispatcher = SubmissionDispatcher(self.service, SubmissionConsent(self.db), evaluate)
        try:
            dispatcher.dispatch('local', first['id'])
            self.assertTrue(entered.wait(3))
            dispatcher.dispatch('local', first['id'])
            self.assertEqual(self.service.status('local', other['id'])['status'], 'queued')
        finally:
            release.set()
            dispatcher.close()
        self.assertEqual(len(calls), 1)
        # Completion must be delivered even when the UI never polls this result.
        self.assertEqual(len(self.completions), 1)
        self.assertEqual(self.service.status('local', first['id'])['status'], 'completed')
        self.assertEqual(len(self.completions), 1)

    def test_completion_survives_projection_failure_and_material_cleanup(self):
        import submission_queue as queue
        from submission_worker import run_one
        first = self.submit()
        consent = SubmissionConsent(self.db)
        consent.approve('local', first['id'])
        run_one(self.db, load=lambda job: queue.load_materials(self.db, job), authorize=consent.authorize,
                evaluate=lambda *args: {'scores': {'criterion-1': 1}, 'quote': 'print(1)',
                    'feedback': '通过', 'nextStep': '运行验证'})
        def unavailable(*args):
            raise OSError('learning database temporarily unavailable')
        with self.assertRaises(OSError):
            queue.deliver_completions(self.db, unavailable)
        queue.delete_archived_materials(self.db, 'local')
        queue.initialize(self.db)
        self.service.sync_completions()
        self.service.sync_completions()
        self.assertEqual(self.completions, [('local', self.plan_id, 'lesson-1', first['id'], 'course-task')])
