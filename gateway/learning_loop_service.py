"""Authenticated v2 route adapter. Not mounted in the production HTTP server.

P1 uses the native app session only. Extension tokens are a separate P2 scope;
never give extensions the native app's session token.
"""
import hmac
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import learning_loop as loop

MAX_BODY_BYTES = 65536


def error(status, code, message):
    return status, {'error': {'code': code, 'message': message}}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise loop.ContractError('JSON 包含重复字段')
        result[key] = value
    return result


class LearningLoopService:
    def __init__(self, database, plans_directory, session_token):
        self.database = Path(database)
        self.plans_directory = Path(plans_directory)
        self.session_token = session_token

    def authorized(self, token):
        return isinstance(token, str) and bool(self.session_token) and hmac.compare_digest(token.encode(), self.session_token.encode())

    def register_exercise(self, contract):
        """Internal generator entry, deliberately not exposed as a client route."""
        loop.validate_exercise(contract)
        root = self.plans_directory.resolve()
        path = root / (contract['planId'] + '.json')
        if not path.is_file() or path.is_symlink() or path.resolve().parent != root:
            raise loop.ContractError('课程尚不存在，不能登记练习')
        if path.stat().st_size > 16 * 1024 * 1024:
            raise loop.ContractError('课程文件超过大小限制')
        try:
            plan = json.loads(path.read_text(encoding='utf-8'))
            if not any(item.get('id') == contract['lessonId'] for item in plan['lessons']):
                raise loop.ContractError('课程中不存在该课')
        except (ValueError, KeyError, TypeError, AttributeError):
            raise loop.ContractError('课程格式无效或课不存在') from None
        loop.save_exercise(self.database, contract)

    def handle(self, method, target, token, body=b''):
        # No DB access or parsing before authentication. No secrets in errors.
        if not self.authorized(token):
            return error(401, 'unauthorized', '请通过已授权的 Trainer 会话访问')
        if not isinstance(body, bytes) or len(body) > MAX_BODY_BYTES:
            return error(413, 'payload_too_large', '文本请求不能超过 64 KiB')
        try:
            parts = urlsplit(target)
            if parts.scheme or parts.netloc or parts.fragment: raise loop.ContractError('请求路径无效')
            route = parts.path
            payload = json.loads(body, object_pairs_hook=unique_object) if body else {}
            if not isinstance(payload, dict): raise loop.ContractError('请求必须是 JSON 对象')
            if method == 'POST' and route == '/v2/submissions' and not parts.query:
                sid = loop.submit(self.database, 'local', payload)
                return 202, {'id': sid, 'status': self.read_submission(sid)['status']}
            match = re.fullmatch(r'/v2/submissions/([a-f0-9]{32})(/cancel)?', route)
            if match and not parts.query:
                sid, action = match.groups()
                if method == 'GET' and action is None:
                    value = self.read_submission(sid)
                    return (200, value) if value else error(404, 'not_found', '提交不存在')
                if method == 'POST' and action == '/cancel':
                    if payload: raise loop.ContractError('取消请求不接受额外字段')
                    with loop.connect(self.database) as db:
                        db.execute('BEGIN IMMEDIATE')
                        row = db.execute('SELECT status FROM loop_submissions WHERE id=? AND learner=?', (sid, 'local')).fetchone()
                        if not row: return error(404, 'not_found', '提交不存在')
                        if row['status'] not in ('queued', 'evaluating', 'cancelled'):
                            return error(409, 'invalid_state', '已结束的评估不能取消')
                        db.execute("UPDATE loop_submissions SET status='cancelled' WHERE id=?", (sid,))
                        db.execute('INSERT OR IGNORE INTO loop_events(submission_id,kind,created_at) VALUES(?,?,?)', (sid, 'cancelled', loop.now()))
                    return 200, {'id': sid, 'status': 'cancelled'}
            match = re.fullmatch(r'/v2/exercises/([A-Za-z0-9_.-]{1,200})', route)
            if method == 'GET' and match:
                query = parse_qs(parts.query, keep_blank_values=True)
                if set(query) != {'revision'} or len(query['revision']) != 1 or not re.fullmatch('[1-9][0-9]{0,8}', query['revision'][0]):
                    raise loop.ContractError('需要唯一的有效 revision')
                with loop.connect(self.database) as db:
                    row = db.execute('SELECT contract FROM loop_exercises WHERE id=? AND revision=?', (match[1], int(query['revision'][0]))).fetchone()
                return (200, json.loads(row['contract'])) if row else error(404, 'not_found', '练习不存在')
            return error(404, 'not_found', '接口不存在')
        except (ValueError, TypeError, UnicodeError):
            return error(400, 'invalid_request', '字段、材料、题目修订或幂等键无效；请检查提交要求')
        except sqlite3.Error:
            return error(503, 'storage_unavailable', '存储暂不可用；请勿更换幂等键重复提交')

    def read_submission(self, sid):
        with loop.connect(self.database) as db:
            row = db.execute('SELECT * FROM loop_submissions WHERE id=? AND learner=?', (sid, 'local')).fetchone()
            if not row: return None
            result = db.execute('SELECT result,model,method FROM loop_results WHERE submission_id=?', (sid,)).fetchone()
            contract = db.execute('SELECT contract FROM loop_exercises WHERE id=? AND revision=?', (row['exercise_id'], row['revision'])).fetchone()
        return {'id': sid, 'exerciseId': row['exercise_id'], 'revision': row['revision'], 'status': row['status'],
                'kind': json.loads(contract['contract'])['kind'], 'answer': json.loads(row['payload'])['answer'],
                'createdAt': row['created_at'], 'assessment': None if not result else
                {'result': json.loads(result['result']), 'model': result['model'], 'method': result['method']}}
