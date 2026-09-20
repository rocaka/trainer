"""Internal queue with optional immutable materials; not mounted in production.

Caller must supply authorized prepared materials and recheck AI-send consent
before processing. This module does not collect workspace files or send to AI.
Storage is SQLite plaintext: caller must provision a private directory/database
outside portable learning backups before any production use.
No automatic retry/reclaim: interrupted external requests have unknown outcomes.
"""
import re
import uuid
import json

from learning_loop import connect, text, encode


def initialize(path):
    """Explicit additive setup on a caller-selected database; no import side effects."""
    with connect(path) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS material_jobs (
            id TEXT PRIMARY KEY, learner TEXT NOT NULL, fingerprint TEXT NOT NULL,
            evaluator_key TEXT NOT NULL, status TEXT NOT NULL
            CHECK(status IN ('queued','evaluating','completed','failed','cancelled')),
            claim TEXT, UNIQUE(learner,fingerprint,evaluator_key))''')
        db.execute('''CREATE TABLE IF NOT EXISTS material_requests (
            learner TEXT NOT NULL, request_key TEXT NOT NULL,
            job_id TEXT NOT NULL REFERENCES material_jobs(id),
            PRIMARY KEY(learner,request_key))''')
        db.execute('''CREATE TABLE IF NOT EXISTS material_results (
            job_id TEXT PRIMARY KEY REFERENCES material_jobs(id), result TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS material_snapshots (
            learner TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(learner,fingerprint))''')
        db.execute('''CREATE TABLE IF NOT EXISTS completion_outbox (
            job_id TEXT PRIMARY KEY, learner TEXT NOT NULL, plan_id TEXT NOT NULL,
            lesson_id TEXT NOT NULL, task_role TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS submission_bindings (
            binding_id TEXT NOT NULL, job_id TEXT NOT NULL,
            PRIMARY KEY(binding_id,job_id))''')
        db.execute('CREATE TABLE IF NOT EXISTS submission_failures (job_id TEXT PRIMARY KEY, code TEXT NOT NULL)')
        # Recover pre-outbox results while their source snapshots still exist.
        for row in db.execute('''SELECT j.id,j.learner,s.payload FROM material_jobs j
            JOIN material_results r ON r.job_id=j.id
            JOIN material_snapshots s ON s.learner=j.learner AND s.fingerprint=j.fingerprint
            WHERE j.status='completed' AND json_extract(r.result,'$.outcome')='passed' ''').fetchall():
            _completion_event(db, row['id'], row['learner'], row['payload'])


def _completion_event(db, job_id, learner, payload):
    contract = json.loads(payload)[0]
    source = contract.get('taskSource', {})
    if source.get('role') in ('course-task', 'coach-exercise'):
        db.execute('''INSERT OR IGNORE INTO completion_outbox
            (job_id,learner,plan_id,lesson_id,task_role) VALUES(?,?,?,?,?)''',
            (job_id, learner, contract['planId'], contract['lessonId'], source['role']))


def deliver_completions(path, record):
    """Replay idempotently after a crash, without rereading source or invoking AI."""
    with connect(path) as db:
        pending = db.execute('SELECT * FROM completion_outbox WHERE delivered=0').fetchall()
    for event in pending:
        record(event['learner'], event['plan_id'], event['lesson_id'], event['job_id'], event['task_role'])
        with connect(path) as db:
            db.execute('UPDATE completion_outbox SET delivered=1 WHERE job_id=?', (event['job_id'],))


def load_materials(path, job):
    """Internal worker loader, scoped by the claimed job's owner and fingerprint."""
    with connect(path) as db:
        row = db.execute('SELECT payload FROM material_snapshots WHERE learner=? AND fingerprint=?',
                         (job['learner'], job['fingerprint'])).fetchone()
    if row is None:
        raise ValueError('提交材料不存在')
    return json.loads(row['payload'])


def recover_interrupted(path):
    """Called once by the owning runtime at startup; never resends to AI."""
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT OR REPLACE INTO submission_failures SELECT id,'interrupted' FROM material_jobs WHERE status IN ('queued','evaluating')")
        db.execute("UPDATE material_jobs SET status='failed',claim=NULL WHERE status IN ('queued','evaluating')")


def complete(path, job_id, claim, result):
    """Trusted worker only: commit validated result and completion together."""
    payload = encode(result)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        changed = db.execute("UPDATE material_jobs SET status='completed' WHERE id=? AND claim=? AND status='evaluating'",
                             (job_id, claim)).rowcount
        if not changed:
            raise ValueError('任务领取标识或状态无效')
        db.execute('INSERT INTO material_results VALUES(?,?)', (job_id, payload))
        if result.get('outcome') == 'passed':
            snapshot = db.execute('''SELECT j.learner,s.payload FROM material_jobs j
                JOIN material_snapshots s ON s.learner=j.learner AND s.fingerprint=j.fingerprint
                WHERE j.id=?''', (job_id,)).fetchone()
            if snapshot:
                _completion_event(db, job_id, snapshot['learner'], snapshot['payload'])


def enqueue(path, learner, request_key, fingerprint, evaluator_key, *, prepared=None, retry_failed=False):
    text(learner, 200)
    text(request_key, 200)
    # Evaluator key hashes provider/model/prompt-version/settings, not API secrets.
    for value in (fingerprint, evaluator_key):
        if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
            raise ValueError('材料或评判配置指纹无效')
    payload = None
    if prepared is not None:
        # Trusted prepared=(registered contract, snapshot), never raw client input.
        from submission_worker import validate_materials
        payload = encode(prepared)
        if len(payload.encode('utf-8')) > 16 * 1024 * 1024:
            raise ValueError('提交材料超过存储限制')
        frozen = json.loads(payload)
        if not isinstance(frozen, list) or len(frozen) != 2:
            raise ValueError('提交材料格式无效')
        validate_materials(*frozen, fingerprint)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if payload is not None:
            snapshot = db.execute('SELECT payload FROM material_snapshots WHERE learner=? AND fingerprint=?',
                                  (learner, fingerprint)).fetchone()
            if snapshot and snapshot['payload'] != payload:
                raise ValueError('已保存材料不可覆盖')
            db.execute('INSERT OR IGNORE INTO material_snapshots VALUES(?,?,?)', (learner, fingerprint, payload))
        old = db.execute('''SELECT j.* FROM material_requests r JOIN material_jobs j
            ON j.id=r.job_id WHERE r.learner=? AND r.request_key=?''',
            (learner, request_key)).fetchone()
        if old:
            if old['fingerprint'] != fingerprint or old['evaluator_key'] != evaluator_key:
                raise ValueError('请求标识已用于其他材料或评判配置')
            return dict(old)
        db.execute('''INSERT OR IGNORE INTO material_jobs VALUES(?,?,?,?, 'queued',NULL)''',
                   (uuid.uuid4().hex, learner, fingerprint, evaluator_key))
        job = db.execute('''SELECT * FROM material_jobs WHERE learner=? AND fingerprint=?
            AND evaluator_key=?''', (learner, fingerprint, evaluator_key)).fetchone()
        # Only a new explicit submission may retry. Replayed request keys above
        # remain idempotent, and running/completed jobs are never resent.
        if retry_failed and prepared is not None and job['status'] in ('failed', 'cancelled'):
            db.execute("UPDATE material_jobs SET status='queued',claim=NULL WHERE id=?", (job['id'],))
            db.execute('DELETE FROM submission_failures WHERE job_id=?', (job['id'],))
            job = db.execute('SELECT * FROM material_jobs WHERE id=?', (job['id'],)).fetchone()
        db.execute('INSERT INTO material_requests VALUES(?,?,?)', (learner, request_key, job['id']))
        return dict(job)


def claim_next(path, job_id=None):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        job = (db.execute("SELECT * FROM material_jobs WHERE status='queued' AND id=?", (job_id,)).fetchone()
               if job_id is not None else db.execute("SELECT * FROM material_jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone())
        if job is None:
            return None
        claim = uuid.uuid4().hex
        db.execute("UPDATE material_jobs SET status='evaluating',claim=? WHERE id=?", (claim, job['id']))
        return {**dict(job), 'status': 'evaluating', 'claim': claim}


def finish(path, job_id, claim, status, failure_code=None):
    if status not in ('completed', 'failed') or not isinstance(claim, str) or not claim:
        raise ValueError('任务结束状态无效')
    with connect(path) as db:
        changed = db.execute('''UPDATE material_jobs SET status=? WHERE id=? AND claim=?
            AND status='evaluating' ''', (status, job_id, claim)).rowcount
        if not changed:
            raise ValueError('任务未在评判中或领取标识已失效')
        if status == 'failed' and failure_code:
            db.execute('INSERT OR REPLACE INTO submission_failures VALUES (?,?)', (job_id, failure_code))


def cancel(path, learner, job_id):
    with connect(path) as db:
        # In-flight external requests cannot safely be claimed as cancelled here.
        changed = db.execute("UPDATE material_jobs SET status='cancelled' WHERE id=? AND learner=? AND status='queued'",
                             (job_id, learner)).rowcount
        return bool(changed)


def material_storage(path, learner):
    """Return private material usage without exposing filenames or source text."""
    text(learner, 200)
    with connect(path) as db:
        totals = db.execute('''SELECT count(*) AS count,
            coalesce(sum(length(CAST(payload AS BLOB))),0) AS bytes
            FROM material_snapshots WHERE learner=?''', (learner,)).fetchone()
        protected = db.execute('''SELECT count(*) FROM material_snapshots s
            WHERE s.learner=? AND EXISTS (
                SELECT 1 FROM material_jobs j WHERE j.learner=s.learner
                AND j.fingerprint=s.fingerprint AND j.status IN ('queued','evaluating'))''',
            (learner,)).fetchone()[0]
        feedback = db.execute('''SELECT count(*) FROM material_results r JOIN material_jobs j
            ON j.id=r.job_id WHERE j.learner=?''', (learner,)).fetchone()[0]
    return {'snapshotCount': totals['count'], 'snapshotBytes': totals['bytes'],
            'protectedCount': protected, 'feedbackCount': feedback,
            'automaticCleanup': False}


def delete_archived_materials(path, learner):
    """Explicitly remove non-active source snapshots while preserving job/results."""
    text(learner, 200)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        removable = db.execute('''SELECT count(*) AS count,
            coalesce(sum(length(CAST(s.payload AS BLOB))),0) AS bytes
            FROM material_snapshots s WHERE s.learner=? AND NOT EXISTS (
                SELECT 1 FROM material_jobs j WHERE j.learner=s.learner
                AND j.fingerprint=s.fingerprint AND j.status IN ('queued','evaluating'))''',
            (learner,)).fetchone()
        db.execute('''DELETE FROM material_snapshots WHERE learner=? AND NOT EXISTS (
            SELECT 1 FROM material_jobs j WHERE j.learner=material_snapshots.learner
            AND j.fingerprint=material_snapshots.fingerprint
            AND j.status IN ('queued','evaluating'))''', (learner,))
        protected = db.execute('SELECT count(*) FROM material_snapshots WHERE learner=?',
                               (learner,)).fetchone()[0]
    return {'removedCount': removable['count'], 'removedBytes': removable['bytes'],
            'protectedCount': protected, 'feedbackPreserved': True}
