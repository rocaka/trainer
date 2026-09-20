"""Single internal course-submit use case; production adapters remain unmounted.

Native controller supplies learner and configured evaluator identity. The trusted
binding resolver returns root/planId/guard after checking ownership. Client input
contains IDs and optional explanation, never paths, contracts or passed results.
"""
import json

from course_task_lookup import course_task
from learning_loop import connect
from submission_materials import prepare_materials
import submission_queue as queue


class CourseSubmission:
    @classmethod
    def from_pairing(cls, data, database, pairing_service):
        """Wire live grant/state stores without any extra user confirmation step.

        Database must already be provisioned privately by the native runtime.
        This factory does not start a worker, grant AI consent or mount HTTP.
        """
        from submission_binding import SubmissionBindings
        if pairing_service.workspaces is None or pairing_service.sources is None:
            raise ValueError('工作区服务尚未启用')
        resolver = SubmissionBindings(pairing_service.workspaces, pairing_service.sources,
                                      pairing_service.latest_buffers)
        from learning_store import record_course_completion
        return cls(data, database, resolver, record_completion=record_course_completion)

    def __init__(self, data, database, resolve_binding, record_completion=None):
        self.data = data
        self.database = database
        self.resolve_binding = resolve_binding
        self.record_completion = record_completion

    def sync_completions(self):
        if self.record_completion is not None:
            queue.deliver_completions(self.database, self.record_completion)

    def submit(self, *, learner, plan_id, lesson_id, binding_id, request_key,
               evaluator_key, answer=''):
        contract = course_task(self.data, plan_id, lesson_id)
        binding = self.resolve_binding(learner, binding_id)
        if binding['planId'] != plan_id:
            raise ValueError('工作区关联课程与提交课程不一致')
        materials = prepare_materials(contract, binding['root'], answer=answer, guard=binding['guard'])
        job = queue.enqueue(self.database, learner, request_key, materials['materialFingerprint'],
                            evaluator_key, prepared=(contract, materials), retry_failed=True)
        with connect(self.database) as db:
            db.execute('DELETE FROM submission_bindings WHERE binding_id=? AND job_id=?', (binding_id, job['id']))
            db.execute('INSERT INTO submission_bindings VALUES(?,?)', (binding_id, job['id']))
        return self.status(learner, job['id'])

    def binding_status(self, binding_id):
        """Minimal metadata for an already authorized extension binding."""
        with connect(self.database) as db:
            row = db.execute('''SELECT j.id,j.status,r.result FROM submission_bindings b
                JOIN material_jobs j ON j.id=b.job_id
                LEFT JOIN material_results r ON r.job_id=j.id
                WHERE b.binding_id=? AND j.learner='local' ORDER BY b.rowid DESC LIMIT 1''',
                (binding_id,)).fetchone()
        if row is None:
            return None
        result = json.loads(row['result']) if row['result'] else {}
        return {'id': row['id'], 'status': row['status'], 'outcome': result.get('outcome')}

    def status(self, learner, job_id):
        with connect(self.database) as db:
            job = db.execute('''SELECT j.id,j.status,s.payload FROM material_jobs j
                LEFT JOIN material_snapshots s ON s.learner=j.learner AND s.fingerprint=j.fingerprint
                WHERE j.id=? AND j.learner=?''',
                             (job_id, learner)).fetchone()
            if job is None:
                raise ValueError('提交不存在')
            result = db.execute('SELECT result FROM material_results WHERE job_id=?', (job_id,)).fetchone()
            failure = db.execute('SELECT code FROM submission_failures WHERE job_id=?', (job_id,)).fetchone()
        assessment = json.loads(result['result']) if result else None
        self.sync_completions()
        from submission_worker import FAILURE_MESSAGES
        code = failure['code'] if failure else 'unknown'
        return {'id': job['id'], 'status': job['status'], 'assessment': assessment,
                'failureCode': code if job['status'] == 'failed' else None,
                'failureMessage': FAILURE_MESSAGES.get(code, FAILURE_MESSAGES['unknown']) if job['status'] == 'failed' else None}

    def material_storage(self, learner):
        return queue.material_storage(self.database, learner)

    def delete_archived_materials(self, learner):
        return queue.delete_archived_materials(self.database, learner)
