"""P1 learning-loop primitives. Not wired to HTTP or the live database yet.

Callers must authenticate and resolve a valid course before calling save_exercise.
No network, source-code collection, execution, or automatic runtime migration.
"""
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class ContractError(ValueError):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


DDL = [
    'CREATE TABLE loop_schema(version INTEGER PRIMARY KEY CHECK(version=1), migrated_at TEXT NOT NULL)',
    '''CREATE TABLE loop_exercises(id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
       contract TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(id,revision))''',
    '''CREATE TABLE loop_submissions(id TEXT PRIMARY KEY, learner TEXT NOT NULL, exercise_id TEXT NOT NULL,
       revision INTEGER NOT NULL, request_key TEXT NOT NULL, payload TEXT NOT NULL,
       status TEXT NOT NULL CHECK(status IN ('queued','evaluating','passed','needs_revision','failed','cancelled','insufficient_evidence')),
       created_at TEXT NOT NULL, UNIQUE(learner,request_key),
       FOREIGN KEY(exercise_id,revision) REFERENCES loop_exercises(id,revision))''',
    '''CREATE TABLE loop_results(submission_id TEXT PRIMARY KEY REFERENCES loop_submissions(id),
       result TEXT NOT NULL, model TEXT NOT NULL, method TEXT NOT NULL CHECK(method='static_review'), created_at TEXT NOT NULL)''',
    '''CREATE TABLE loop_rewards(learner TEXT NOT NULL, exercise_id TEXT NOT NULL, kind TEXT NOT NULL,
       xp INTEGER NOT NULL CHECK(xp>=0), submission_id TEXT NOT NULL REFERENCES loop_submissions(id),
       PRIMARY KEY(learner,exercise_id,kind))''',
    '''CREATE TABLE loop_events(id INTEGER PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES loop_submissions(id),
       kind TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(submission_id,kind))''',
    '''CREATE TABLE loop_legacy_records(source TEXT NOT NULL CHECK(source IN ('legacy_self_report','legacy_ai_review')),
       source_id INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(source,source_id))''',
]


def migrate(path):
    """Additive transactional migration with pre-migration SQLite backup.

    Explicit path only; caller must quiesce writes before production rollout.
    Failed DDL rolls back. Backups are never overwritten.
    """
    path = Path(path)
    existed = path.exists()
    with connect(path) as db:
        if db.execute("SELECT name FROM sqlite_master WHERE name='loop_schema'").fetchone():
            if [row[0] for row in db.execute('SELECT version FROM loop_schema')] != [1]:
                raise ContractError('不支持的学习闭环数据库版本')
            return None
        backup = None
        if existed:
            backup = path.with_name(path.name + '.before-loop-' + uuid.uuid4().hex + '.sqlite3')
            with connect(backup) as destination:
                db.backup(destination)
        db.execute('BEGIN IMMEDIATE')
        for statement in DDL:
            db.execute(statement)
        for table, source in [('evidence', 'legacy_self_report'), ('assessments', 'legacy_ai_review')]:
            if db.execute('SELECT name FROM sqlite_master WHERE name=?', (table,)).fetchone():
                columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
                if 'id' not in columns:
                    raise ValueError('旧数据缺少记录 ID；迁移已取消')
                for row in db.execute(f'SELECT * FROM {table}'):
                    db.execute('INSERT INTO loop_legacy_records VALUES(?,?,?)', (source, row['id'], encode(dict(row))))
        db.execute('INSERT INTO loop_schema VALUES(1,?)', (now(),))
    return backup


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ContractError('字段缺失或包含未允许字段')


def text(value, limit=16000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractError('文本为空或超过长度限制')


def validate_exercise(value):
    optional = ''.join(' ' + name for name in ('requiredFiles', 'taskSource') if isinstance(value, dict) and name in value)
    fields(value, 'exerciseId revision planId lessonId kind prompt learningObjectives submissionSpec contextHints rubric passRule verificationRequirement' + optional)
    if 'taskSource' in value:
        source = value['taskSource']
        fields(source, 'mode role taskId')
        if source['mode'] not in ('project-practice', 'project-import', 'course'):
            raise ContractError('学习入口无效')
        if source['role'] not in ('course-task', 'coach-exercise'):
            raise ContractError('任务来源无效')
        text(source['taskId'], 200)
    if 'requiredFiles' in value:
        from submission_snapshot import checked_path
        paths = value['requiredFiles']
        if not isinstance(paths, list) or len(paths) > 100 or len(set(map(str, paths))) != len(paths):
            raise ContractError('题目文件清单无效')
        for path in paths:
            checked_path(path)
            if any(char in path for char in '*?[]'):
                raise ContractError('题目文件清单必须是明确路径')
    for name in ('exerciseId', 'lessonId'): text(value[name], 200)
    if not re.fullmatch('[A-Za-z0-9_.-]{1,200}', value['exerciseId']): raise ContractError('练习 ID 包含无效字符')
    if type(value['revision']) is not int or value['revision'] < 1: raise ContractError('修订号无效')
    if not isinstance(value['planId'], str) or not re.fullmatch('[a-f0-9]{64}', value['planId']): raise ContractError('课程 ID 无效')
    if value['kind'] not in ('reflection', 'reading', 'writing', 'debugging', 'transfer'): raise ContractError('练习类型无效')
    if value['verificationRequirement'] not in ('static_review', 'user_report', 'trusted_execution'): raise ContractError('验证来源无效')
    text(value['prompt'])
    for name in ('learningObjectives', 'contextHints'):
        items = value[name]
        if not isinstance(items, list) or len(items) > 100 or (name == 'learningObjectives' and not items): raise ContractError('目标或上下文无效')
        for item in items: text(item, 1000)
    spec = value['submissionSpec']; fields(spec, 'answer code report')
    if any(type(v) is not bool for v in spec.values()) or not any(spec.values()): raise ContractError('提交要求无效')
    if value['kind'] in ('writing', 'debugging', 'transfer') and not spec['code']: raise ContractError('此练习必须要求代码')
    if value['kind'] in ('reflection', 'reading') and not spec['answer']: raise ContractError('此练习必须要求解释')
    if value['verificationRequirement'] == 'user_report' and not spec['report']: raise ContractError('此练习必须要求报告')
    rubric = value['rubric']
    if not isinstance(rubric, list) or not 1 <= len(rubric) <= 20: raise ContractError('评分标准无效')
    ids = set(); maximum = 0
    for item in rubric:
        fields(item, 'id description maxScore'); text(item['id'], 100); text(item['description'], 2000)
        if item['id'] in ids or type(item['maxScore']) is not int or not 1 <= item['maxScore'] <= 100: raise ContractError('评分项无效')
        ids.add(item['id']); maximum += item['maxScore']
    fields(value['passRule'], 'minimumScore')
    threshold = value['passRule']['minimumScore']
    if type(threshold) is not int or not 1 <= threshold <= maximum: raise ContractError('通过条件无效')


def save_exercise(path, value):
    validate_exercise(value)
    encoded = encode(value)
    with connect(path) as db:
        row = db.execute('SELECT contract FROM loop_exercises WHERE id=? AND revision=?', (value['exerciseId'], value['revision'])).fetchone()
        if row and row['contract'] != encoded: raise ContractError('已存在的题目修订不可覆盖')
        db.execute('INSERT OR IGNORE INTO loop_exercises VALUES(?,?,?,?)', (value['exerciseId'], value['revision'], encoded, now()))


def submit(path, learner, payload):
    fields(payload, 'exerciseId revision answer idempotencyKey')
    text(learner, 200); text(payload['exerciseId'], 200); text(payload['idempotencyKey'], 200); text(payload['answer'])
    if type(payload['revision']) is not int or payload['revision'] < 1: raise ContractError('修订号无效')
    encoded = encode(payload)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT id,payload FROM loop_submissions WHERE learner=? AND request_key=?', (learner, payload['idempotencyKey'])).fetchone()
        if existing:
            if existing['payload'] != encoded: raise ContractError('幂等键已用于不同内容')
            return existing['id']
        row = db.execute('SELECT contract FROM loop_exercises WHERE id=? AND revision=?', (payload['exerciseId'], payload['revision'])).fetchone()
        if not row: raise ContractError('题目或修订不存在')
        contract = json.loads(row['contract'])
        if contract['submissionSpec']['code'] or contract['submissionSpec']['report'] or contract['verificationRequirement'] != 'static_review':
            raise ContractError('文件/运行材料通道尚未接通；不能以文本替代必要证据')
        sid = uuid.uuid4().hex
        db.execute('INSERT INTO loop_submissions VALUES(?,?,?,?,?,?,?,?)', (sid, learner, payload['exerciseId'], payload['revision'], payload['idempotencyKey'], encoded, 'queued', now()))
        db.execute('INSERT INTO loop_events(submission_id,kind,created_at) VALUES(?,?,?)', (sid, 'submitted', now()))
        return sid


def start(path, submission_id):
    with connect(path) as db:
        changed = db.execute("UPDATE loop_submissions SET status='evaluating' WHERE id=? AND status='queued'", (submission_id,)).rowcount
        if not changed: raise ContractError('提交不在待评估状态')


def finish(path, submission_id, result, model):
    """Trusted worker entry only; never accept a client-provided pass/XP value."""
    fields(result, 'scores quote feedback nextStep')
    text(model, 200)
    for name in ('quote', 'feedback', 'nextStep'): text(result[name])
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM loop_submissions WHERE id=?', (submission_id,)).fetchone()
        if not row: raise ContractError('提交不存在')
        old = db.execute('SELECT result,model FROM loop_results WHERE submission_id=?', (submission_id,)).fetchone()
        if old:
            if old['result'] != encode(result) or old['model'] != model: raise ContractError('已结束的评估不可覆盖')
            return row['status']
        if row['status'] != 'evaluating': raise ContractError('提交尚未开始评估')
        contract = json.loads(db.execute('SELECT contract FROM loop_exercises WHERE id=? AND revision=?', (row['exercise_id'], row['revision'])).fetchone()[0])
        scores = result['scores']; rubric = contract['rubric']
        if not isinstance(scores, dict) or set(scores) != {item['id'] for item in rubric}: raise ContractError('评分项不匹配')
        for item in rubric:
            score = scores[item['id']]
            if type(score) is not int or not 0 <= score <= item['maxScore']: raise ContractError('评分越界')
        if result['quote'] not in json.loads(row['payload'])['answer']: raise ContractError('评估引用不在提交中')
        status = 'passed' if sum(scores.values()) >= contract['passRule']['minimumScore'] else 'needs_revision'
        db.execute('INSERT INTO loop_results VALUES(?,?,?,?,?)', (submission_id, encode(result), model, 'static_review', now()))
        db.execute('UPDATE loop_submissions SET status=? WHERE id=?', (status, submission_id))
        db.execute('INSERT INTO loop_events(submission_id,kind,created_at) VALUES(?,?,?)', (submission_id, status, now()))
        if status == 'passed':
            db.execute('INSERT OR IGNORE INTO loop_rewards VALUES(?,?,?,?,?)', (row['learner'], row['exercise_id'], 'first_pass', 10, submission_id))
        return status
