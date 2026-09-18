"""Separate native approval from proof-of-possession extension requests."""
import hmac
import json
import sqlite3
import re
import threading
import time
import secrets
from pathlib import Path
from workspace_grants import WorkspaceGrants
from source_grants import SourceGrants
from extension_pairing import PairingError, digest
from learning_loop import connect, fields
from learning_loop_service import error, unique_object, MAX_BODY_BYTES


class PairingService:
    public_posts = frozenset(['/v2/pairings', '/v2/pairings/redeem', '/v2/pairings/session', '/v2/pairings/disconnect', '/v2/pairings/workspaces', '/v2/pairings/workspaces/status', '/v2/pairings/workspaces/courses'])

    def __init__(self, store, native_token, plans_directory=None):
        self.store = store
        self.submission_status = lambda binding_id: None
        self.last_seen = {}
        self.buffer_states = {}
        self.buffer_checks = {}
        self.heartbeat_lock = threading.Lock()
        self.native_token = native_token
        self.plans_directory = Path(plans_directory) if plans_directory else None
        self.workspaces = WorkspaceGrants(store) if plans_directory else None
        self.sources = SourceGrants(self.workspaces) if self.workspaces else None

    def latest_buffers(self, binding_id):
        """Native internal read; caller still checks authorization and freshness."""
        with self.heartbeat_lock:
            state = self.buffer_states.get(binding_id)
            return {**state, 'dirtyPaths': list(state['dirtyPaths'])} if state else None

    def begin_buffer_check(self, binding_id):
        """Internal native submit coordinator only; never an extension request."""
        active = {b['id'] for b in self.workspaces.active() if b['valid']}
        if binding_id not in active:
            raise ValueError('工作区关联失效')
        check_id = secrets.token_hex(16)
        with self.heartbeat_lock:
            self.buffer_checks = {k: v for k, v in self.buffer_checks.items()
                                  if k in active and time.monotonic() - v['started'] < 30}
            self.buffer_checks[binding_id] = {'id': check_id, 'started': time.monotonic()}
            self.buffer_states.pop(binding_id, None)
        return check_id

    def checked_buffers(self, binding_id, check_id):
        with self.heartbeat_lock:
            check = self.buffer_checks.get(binding_id)
            state = self.buffer_states.get(binding_id)
            if (not check or check['id'] != check_id or time.monotonic() - check['started'] >= 30
                    or not state or state.get('checkId') != check_id):
                return None
            return {**state, 'dirtyPaths': list(state['dirtyPaths'])}

    def check_plan(self, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch('[a-f0-9]{64}', plan_id): raise ValueError()
        path = self.plans_directory / (plan_id + '.json')
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024: raise ValueError()
        plan = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(plan, dict) or not isinstance(plan.get('lessons'), list) or not plan['lessons']: raise ValueError()
        return plan

    def course_catalog(self):
        courses = []
        for path in sorted(self.plans_directory.glob('*.json')):
            try:
                plan = self.check_plan(path.stem)
                first = plan['lessons'][0]
                modules = plan.get('moduleTitles')
                module = modules[0] if isinstance(modules, list) and modules and isinstance(modules[0], str) else None
                title = plan.get('title') or plan.get('skillTitle') or plan.get('skillId')
                if not title and module:
                    title = '完整课程 · ' + re.sub(r'^\s*\d+[.、]\s*', '', module)
                if not title:
                    title = (first.get('title') if isinstance(first, dict) else None) or '已保存课程'
                if not isinstance(title, str): title = '已保存课程'
                language = first.get('language') if isinstance(first, dict) else None
                item = {'id': path.stem, 'title': title[:160], 'lessonCount': len(plan['lessons'])}
                if isinstance(language, str) and language.strip(): item['language'] = language.strip()[:40]
                courses.append(item)
            except (ValueError, OSError): continue
        return courses

    def requires_native(self, method, path):
        if method == 'POST' and path == '/v2/pairings/workspaces/buffers': return False
        if method == 'POST' and path == '/v2/pairings/workspaces/summary': return False
        return not (method == 'POST' and path in self.public_posts)

    def authorized(self, token):
        return isinstance(token, str) and bool(self.native_token) and hmac.compare_digest(token.encode(), self.native_token.encode())

    def handle(self, method, path, token, body=b''):
        if self.requires_native(method, path) and not self.authorized(token):
            return error(401, 'unauthorized', '只有 Trainer 可以确认配对')
        if len(body) > MAX_BODY_BYTES: return error(413, 'payload_too_large', '请求过大')
        try:
            payload = json.loads(body, object_pairs_hook=unique_object) if body else {}
            if method == 'POST' and path == '/v2/pairings/clear':
                fields(payload, '')
                with connect(self.store.path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    count = db.execute('SELECT count(*) FROM extension_tokens WHERE revoked=0').fetchone()[0]
                    db.execute('UPDATE extension_tokens SET revoked=1 WHERE revoked=0')
                    db.execute('UPDATE pairings SET consumed=1 WHERE consumed=0')
                with self.heartbeat_lock: self.last_seen.clear()
                return 200, {'disconnected': count, 'cleared': True}
            if path == '/v2/pairings/source-grants' or path.startswith('/v2/pairings/source-grants/'):
                if not self.sources: return error(503, 'feature_not_enabled', '源码授权尚未启用')
                if method == 'GET' and path == '/v2/pairings/source-grants':
                    return 200, {'grants': self.sources.list_native()}
                if method == 'POST' and path == '/v2/pairings/source-grants/approve':
                    fields(payload, 'bindingId paths')
                    binding = next((g for g in self.workspaces.active() if g['id'] == payload['bindingId'] and g['valid']), None)
                    if not binding: raise ValueError()
                    self.check_plan(binding['plan_id'])
                    grant = self.sources.approve(payload['bindingId'], payload['paths'])
                    return 201, {'id': grant, 'scope': 'source:read', 'externalSend': False}
                if method == 'POST' and path == '/v2/pairings/source-grants/revoke':
                    fields(payload, 'id')
                    if not isinstance(payload['id'], str): raise ValueError()
                    self.sources.revoke(payload['id'])
                    return 200, {'revoked': True}
                return error(404, 'not_found', '接口不存在')
            if method == 'GET' and path == '/v2/pairings/connection-status':
                now = self.store.clock()
                with connect(self.store.path) as db:
                    tokens = {row[0] for row in db.execute('SELECT hash FROM extension_tokens WHERE revoked=0 AND expires>?', (now,))}
                with self.heartbeat_lock:
                    self.last_seen = {key: seen for key, seen in self.last_seen.items() if key in tokens and now - seen < 45}
                    online = len(self.last_seen)
                active = self.workspaces.active() if self.workspaces else []
                return 200, {'paired': len(tokens), 'online': online, 'linked': sum(item['valid'] for item in active)}
            if path.startswith('/v2/pairings/workspaces'):
                if not self.workspaces: return error(503, 'feature_not_enabled', '工作区绑定尚未启用')
                if method == 'GET' and path == '/v2/pairings/workspaces':
                    return 200, {'pending': self.workspaces.pending(), 'active': self.workspaces.active()}
                if method != 'POST': return error(404, 'not_found', '接口不存在')
                if path == '/v2/pairings/workspaces/buffers':
                    fields(payload, 'token bindingId dirtyPaths untitled trusted local' + (' checkId' if 'checkId' in payload else ''))
                    binding_id = payload['bindingId']
                    if not isinstance(binding_id, str) or not self.workspaces.authorize(payload['token'], binding_id):
                        return error(401, 'unauthorized', '关联已失效')
                    # Invalidate prior clean status even when new metadata is invalid.
                    with self.heartbeat_lock:
                        self.buffer_states.pop(binding_id, None)
                        pending = self.buffer_checks.get(binding_id)
                        if 'checkId' in payload and (not pending or payload['checkId'] != pending['id'] or
                                                    time.monotonic() - pending['started'] >= 30):
                            raise ValueError('检查编号已失效')
                    paths = payload['dirtyPaths']
                    if (not isinstance(paths, list) or len(paths) > 1000 or
                            any(not isinstance(p, str) or not p or len(p) > 1024 or p.startswith('/') or '\\' in p or
                                any(c in ('', '.', '..') for c in p.split('/')) for p in paths)):
                        raise ValueError('文件元数据无效')
                    if type(payload['untitled']) is not int or not 0 <= payload['untitled'] <= 10000:
                        raise ValueError('未命名文件计数无效')
                    if type(payload['trusted']) is not bool or type(payload['local']) is not bool:
                        raise ValueError('窗口状态无效')
                    active_ids = {b['id'] for b in self.workspaces.active() if b['valid']}
                    with self.heartbeat_lock:
                        self.buffer_states = {k: v for k, v in self.buffer_states.items() if k in active_ids}
                        self.buffer_states[binding_id] = {'bindingId': binding_id, 'dirtyPaths': sorted(set(paths)),
                            'untitled': payload['untitled'], 'trusted': payload['trusted'], 'local': payload['local'],
                            'receivedAt': time.monotonic(), 'checkId': payload.get('checkId')}
                    return 200, {'received': True}
                if path == '/v2/pairings/workspaces/summary':
                    fields(payload, 'token roots')
                    if not self.store.authorize(payload['token'], 'workspace:bind'): return error(401, 'unauthorized', '请重新配对')
                    roots = payload['roots']
                    if not isinstance(roots, list) or len(roots) > 100 or any(not isinstance(root, str) or len(root) > 4096 for root in roots): raise ValueError()
                    with connect(self.store.path) as db:
                        rows = db.execute('SELECT id,root FROM workspace_grants WHERE token_hash=? AND approved=1 AND revoked=0', (digest(payload['token']),)).fetchall()
                    bindings = [{'id': row['id'], 'root': row['root']} for row in rows if row['root'] in roots and self.workspaces.authorize(payload['token'], row['id'])]
                    for binding in bindings:
                        binding['submission'] = self.submission_status(binding['id'])
                    with self.heartbeat_lock:
                        for binding in bindings:
                            check = self.buffer_checks.get(binding['id'])
                            if check and time.monotonic() - check['started'] < 30:
                                binding['checkId'] = check['id']
                    return 200, {'linked': len({item['root'] for item in bindings}), 'bindings': bindings}
                if path == '/v2/pairings/workspaces/courses':
                    fields(payload, 'token')
                    if not self.store.authorize(payload['token'], 'workspace:bind'): return error(401, 'unauthorized', '请重新配对')
                    return 200, {'courses': self.course_catalog()}
                if path == '/v2/pairings/workspaces':
                    fields(payload, 'token root planId')
                    if not self.store.authorize(payload['token'], 'workspace:bind'): return error(401, 'unauthorized', '请重新配对')
                    self.check_plan(payload['planId'])
                    return 201, self.workspaces.request(payload['token'], payload['root'], payload['planId'])
                if path.endswith('/status'):
                    fields(payload, 'token id')
                    return 200, {'approved': self.workspaces.authorize(payload['token'], payload['id'])}
                if path.endswith('/approve'):
                    fields(payload, 'id')
                    item = next((item for item in self.workspaces.pending() if item['id'] == payload['id']), None)
                    if not item: raise ValueError()
                    self.check_plan(item['plan_id'])
                    self.workspaces.approve(payload['id'])
                    return 200, {'approved': True}
                if path.endswith('/revoke'):
                    fields(payload, 'id'); self.workspaces.revoke(payload['id'])
                    return 200, {'revoked': True}
                return error(404, 'not_found', '接口不存在')
            if method == 'GET' and path == '/v2/pairings':
                with connect(self.store.path) as db:
                    rows = db.execute('SELECT id,name,expires,approved FROM pairings WHERE consumed=0 AND expires>? AND attempts<5', (self.store.clock(),)).fetchall()
                return 200, {'pending': [dict(row) for row in rows]}
            if method != 'POST': return error(404, 'not_found', '接口不存在')
            if path == '/v2/pairings':
                fields(payload, 'name')
                return 201, self.store.request(payload['name'])
            if path == '/v2/pairings/approve':
                fields(payload, 'id code'); self.store.approve(payload['id'], payload['code'])
                return 200, {'approved': True}
            if path == '/v2/pairings/redeem':
                fields(payload, 'id claimSecret')
                return 200, {'token': self.store.redeem(payload['id'], payload['claimSecret']), 'scope': 'workspace:bind'}
            if path in ('/v2/pairings/session', '/v2/pairings/disconnect'):
                fields(payload, 'token')
                if not self.store.authorize(payload['token'], 'workspace:bind'):
                    return error(401, 'unauthorized', '连接已失效，请重新配对')
                with self.heartbeat_lock:
                    if path.endswith('/disconnect'): self.last_seen.pop(digest(payload['token']), None)
                    else: self.last_seen[digest(payload['token'])] = self.store.clock()
                if path.endswith('/disconnect'): self.store.revoke(payload['token'])
                return 200, {'connected': not path.endswith('/disconnect'), 'scope': 'workspace:bind'}
            return error(404, 'not_found', '接口不存在')
        except PairingError:
            return error(409, 'pairing_unavailable', '配对未确认、已失效或次数受限；请核对配对码或重新连接')
        except (ValueError, TypeError, UnicodeError, OSError):
            return error(400, 'invalid_request', '请求无效：请核对课程、目录和授权有效期')
        except sqlite3.Error:
            return error(503, 'storage_unavailable', '配对存储暂不可用')
