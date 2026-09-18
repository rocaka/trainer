"""Explicitly confirmed jobs only; no startup drain or automatic retry.

Native UI must present material/provider disclosure before calling dispatch.
This scheduler is not yet mounted in the running application's request routes.
"""
from concurrent.futures import ThreadPoolExecutor
import threading

import submission_queue as queue
from submission_worker import run_one


class SubmissionDispatcher:
    def __init__(self, service, consent, evaluate):
        self.service, self.consent, self.evaluate = service, consent, evaluate
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='submission-review')
        self.lock = threading.Lock()
        self.pending = set()
        self.closed = False

    def dispatch(self, learner, job_id):
        with self.lock:
            if self.closed:
                raise ValueError('评判服务已停止')
            state = self.service.status(learner, job_id)
            if state['status'] != 'queued' or job_id in self.pending:
                return state
            if len(self.pending) >= 20:
                raise ValueError('待评判任务过多，请等待当前任务完成')
            self.consent.approve(learner, job_id)
            self.pending.add(job_id)
            try:
                self.executor.submit(self._run, job_id)
            except Exception:
                self.pending.discard(job_id)
                self.consent.revoke(learner, job_id)
                raise
            return state

    def _run(self, job_id):
        try:
            run_one(self.service.database,
                    load=lambda job: queue.load_materials(self.service.database, job),
                    authorize=self.consent.authorize, evaluate=self.evaluate, job_id=job_id)
            self.service.sync_completions()
        finally:
            with self.lock:
                self.pending.discard(job_id)

    def close(self):
        with self.lock:
            self.closed = True
        # In-flight network operations retain their transport timeout; no resend.
        self.executor.shutdown(wait=True)
