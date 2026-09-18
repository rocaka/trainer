"""Internal native-controller consent store; no HTTP endpoint or implicit grant.

approve is called only after explicit user confirmation of material and provider.
Fingerprint/evaluator key come from the saved job, never from model instructions.
Revocation stops future checks, not requests already sent to an external service.
"""
import time

from learning_loop import connect


class SubmissionConsent:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        with connect(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS material_send_consents (
                job_id TEXT PRIMARY KEY REFERENCES material_jobs(id),
                learner TEXT NOT NULL, fingerprint TEXT NOT NULL, evaluator_key TEXT NOT NULL,
                expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)''')

    def approve(self, learner, job_id, *, lifetime=900):
        if type(lifetime) is not int or not 1 <= lifetime <= 3600:
            raise ValueError('授权有效期无效')
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('''SELECT j.* FROM material_jobs j JOIN material_snapshots s
                ON s.learner=j.learner AND s.fingerprint=j.fingerprint
                WHERE j.id=? AND j.learner=? AND j.status='queued' ''', (job_id, learner)).fetchone()
            if job is None:
                raise ValueError('待提交任务或材料不存在')
            db.execute('''INSERT INTO material_send_consents VALUES(?,?,?,?,?,0)
                ON CONFLICT(job_id) DO UPDATE SET expires=excluded.expires,revoked=0''',
                (job_id, learner, job['fingerprint'], job['evaluator_key'], self.clock() + lifetime))

    def authorize(self, job):
        with connect(self.path) as db:
            row = db.execute('''SELECT c.job_id FROM material_send_consents c
                JOIN material_jobs j ON j.id=c.job_id
                WHERE c.job_id=? AND c.learner=? AND c.fingerprint=? AND c.evaluator_key=?
                AND c.revoked=0 AND c.expires>? AND j.status='evaluating'
                AND j.claim=? AND j.learner=c.learner AND j.fingerprint=c.fingerprint
                AND j.evaluator_key=c.evaluator_key''',
                (job['id'], job['learner'], job['fingerprint'], job['evaluator_key'],
                 self.clock(), job['claim'])).fetchone()
        return row is not None

    def revoke(self, learner, job_id):
        with connect(self.path) as db:
            return bool(db.execute('''UPDATE material_send_consents SET revoked=1
                WHERE job_id=? AND learner=? AND revoked=0''', (job_id, learner)).rowcount)
