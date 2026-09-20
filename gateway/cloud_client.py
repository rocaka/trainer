"""Native-session-only account adapter; no remote call before explicit login.

Cloud sessions stay in process memory. Restarting Gateway requires a deliberate
cloud sign-in; this prevents silently replacing remotely revoked sessions.
"""
import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request
from urllib.error import HTTPError
from model_transport import relay_open
from learning_store import connection
import account_store as store
from cloud_schema import validate_record

LOCK = threading.RLock()
SESSION = None
RUNTIME = {'lastBackgroundSyncAt': None, 'lastBackgroundError': None}


def endpoint():
    value = os.environ.get('TRAINER_CLOUD_ENDPOINT', '').rstrip('/')
    p = urlparse(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('请先配置 HTTPS 云服务地址')
    return value


def call(path, payload, token='', base=None):
    request = Request((base or endpoint()) + path, data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    try:
        with relay_open(request, timeout=25) as response:
            raw = response.read(1048577)
        if len(raw) > 1048576: raise ValueError('云端响应过大')
        return json.loads(raw)
    except HTTPError as error:
        raise ValueError('云账户会话已失效，请重新登录' if error.code == 401 else f'云服务请求失败（{error.code}）') from None
    except (OSError, TimeoutError): raise ValueError('云服务暂时无法连接；本机数据已保留') from None


def github_token():
    from system_credentials import read_secret
    token = read_secret('com.trainer.github', 'oauth')
    if not token: raise ValueError('请先连接 GitHub')
    return token


def identity(token):
    request = Request('https://api.github.com/user', headers={'Authorization':'Bearer ' + token,
        'Accept':'application/vnd.github+json', 'User-Agent':'Trainer-Account'})
    try:
        with relay_open(request, timeout=20) as response: value = json.loads(response.read(65537))
    except Exception: raise ValueError('GitHub 身份验证失败，请重新连接') from None
    if type(value.get('id')) is not int or value['id'] <= 0: raise ValueError('GitHub 身份无效')
    return str(value['id']), store.safe_login(value.get('login'))


def login(preferences=None, cloud=False):
    global SESSION
    with LOCK:
        token = github_token()
        user_id, name = identity(token)
        state = store.claim(name, preferences, user_id)
        if cloud:
            base = endpoint()
            with connection() as db: device = store.current_device(db)
            remote = call('/v1/session', {'githubToken':token,'deviceId':device,'deviceName':'Trainer Mac'}, base=base)
            if remote.get('userId') != user_id: raise ValueError('云端账户身份不一致')
            SESSION = {'token':remote['token'], 'base':base, 'user':user_id}
        return state


def tables(db):
    db.execute('''CREATE TABLE IF NOT EXISTS cloud_mirror
        (id TEXT PRIMARY KEY, kind TEXT, payload TEXT, revision INTEGER)''')
    db.execute('CREATE TABLE IF NOT EXISTS cloud_cursor (id INTEGER PRIMARY KEY CHECK(id=1),value INTEGER)')
    db.execute('''CREATE TABLE IF NOT EXISTS cloud_conflicts
        (id TEXT PRIMARY KEY,local_payload TEXT,remote_payload TEXT)''')


def synchronize(preferences=None):
    with LOCK:
        if SESSION is None: raise ValueError('请先登录云同步；应用重启后需要重新确认登录')
        store.prepare_sync(preferences)
        # Network runs outside SQLite transactions. Dirty rows are cleared only
        # when the exact payload acknowledged by the server still matches.
        with connection() as db:
            tables(db)
            changes = []
            for row in db.execute('SELECT * FROM sync_outbox WHERE dirty=1 AND id NOT IN (SELECT id FROM cloud_conflicts) ORDER BY id LIMIT 100'):
                base = db.execute('SELECT revision FROM cloud_mirror WHERE id=?', (row['id'],)).fetchone()
                change = {'id':row['id'],'kind':row['kind'],'payload':json.loads(row['payload_json']),
                          'baseRevision':base['revision'] if base else 0}
                validate_record(change); changes.append(change)
            cursor_row = db.execute('SELECT value FROM cloud_cursor WHERE id=1').fetchone()
            cursor = cursor_row['value'] if cursor_row else 0
        result = call('/v1/sync', {'changes':changes,'cursor':cursor}, SESSION['token'], SESSION['base'])
        sent = {item['id']:item for item in changes}
        with connection() as db:
            tables(db)
            for record in result['records']:
                validate_record({'id':record['id'],'kind':record['kind'],'payload':record['payload'],'baseRevision':record['revision']})
                encoded = json.dumps(record['payload'], ensure_ascii=False, separators=(',', ':'))
                local = db.execute('SELECT * FROM sync_outbox WHERE id=?', (record['id'],)).fetchone()
                if local and local['dirty'] and json.loads(local['payload_json']) != record['payload']:
                    db.execute('INSERT OR REPLACE INTO cloud_conflicts VALUES (?,?,?)', (record['id'],local['payload_json'],encoded))
                else:
                    apply_remote(db, record)
                db.execute('INSERT OR REPLACE INTO cloud_mirror VALUES (?,?,?,?)', (record['id'],record['kind'],encoded,record['revision']))
            for ack in result['accepted']:
                item = sent[ack['id']]
                local = db.execute('SELECT payload_json FROM sync_outbox WHERE id=?', (ack['id'],)).fetchone()
                if local and json.loads(local['payload_json']) == item['payload']:
                    db.execute('UPDATE sync_outbox SET dirty=0 WHERE id=?', (ack['id'],))
                encoded = json.dumps(item['payload'], ensure_ascii=False, separators=(',', ':'))
                db.execute('''INSERT INTO cloud_mirror VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    revision=excluded.revision,payload=excluded.payload WHERE excluded.revision>=cloud_mirror.revision''',
                    (item['id'],item['kind'],encoded,ack['revision']))
            db.execute('INSERT OR REPLACE INTO cloud_cursor VALUES (1,?)', (result['cursor'],))
            conflicts = db.execute('SELECT count(*) FROM cloud_conflicts').fetchone()[0]
            if not result['hasMore']:
                db.execute('UPDATE account_state SET last_sync_at=? WHERE id=1', (store.now(),))
        state = store.status()
        state.update(hasMore=result['hasMore'], conflicts=conflicts,
                     message=f'本批同步完成；{conflicts} 项冲突已保留双方内容' if conflicts else '本批同步完成')
        return state


def background_synchronize():
    """Best-effort heartbeat; errors are retained for the settings card.

    It never signs a user in, retries aggressively, or discards local changes.
    """
    if SESSION is None:
        return None
    try:
        result = synchronize()
        RUNTIME.update(lastBackgroundSyncAt=store.now(), lastBackgroundError=None)
        return result
    except ValueError as error:
        RUNTIME['lastBackgroundError'] = str(error)
        return None


def runtime_status():
    with LOCK:
        state = store.status()
        state.update(cloudSessionActive=SESSION is not None,
                     lastBackgroundSyncAt=RUNTIME['lastBackgroundSyncAt'],
                     lastBackgroundError=RUNTIME['lastBackgroundError'])
        with connection() as db:
            tables(db)
            state['conflicts'] = db.execute('SELECT count(*) FROM cloud_conflicts').fetchone()[0]
        return state


def apply_remote(db, record, force=False):
    p, kind = record['payload'], record['kind']
    if kind == 'profile':
        db.execute('INSERT OR REPLACE INTO profile VALUES (?,?,?,?)', ('local',p['name'],p['bio'],p['avatar']))
    elif kind == 'course-progress':
        db.execute('INSERT OR REPLACE INTO course_progress VALUES (?,?)', (p['plan_id'],p['lesson_id']))
    elif kind == 'course-plan':
        from teaching_plan import validate_plan
        try:
            document = json.loads(p['document'])
            validate_plan(document, aggregate=True)
        except (ValueError, TypeError, json.JSONDecodeError):
            raise ValueError('云端课程不完整，未恢复到本机') from None
        from platform_paths import data_directory
        root = data_directory()
        plans, saved = root / 'learning-plans', root / 'saved-courses'
        plans.mkdir(parents=True, exist_ok=True); saved.mkdir(parents=True, exist_ok=True)
        destination = plans / (p['plan_id'] + '.json')
        encoded_document = json.dumps(document, ensure_ascii=False)
        if destination.exists() and not force:
            try:
                existing = json.loads(destination.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                existing = None
            if json.dumps(existing, sort_keys=True, ensure_ascii=False) != json.dumps(document, sort_keys=True, ensure_ascii=False):
                raise ValueError('本机课程版本不同，已保留为同步冲突')
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(encoded_document, encoding='utf-8')
        os.replace(temporary, destination)
        reference = saved / (p['plan_id'] + '.json')
        if not reference.exists() and isinstance(document.get('skillId'), str):
            reference.write_text(json.dumps({'skillId': document['skillId'], 'planId': p['plan_id'], 'createdAt': store.now()}, ensure_ascii=False), encoding='utf-8')
    # Summaries remain summaries: they never manufacture local evaluation or
    # submission proof. They can be exported/read through cloud_mirror.
    db.execute('INSERT OR REPLACE INTO sync_outbox VALUES (?,?,?,?,?,0)',
               (record['id'],kind,record['revision'],store.now(),json.dumps(p,ensure_ascii=False,separators=(',', ':'))))


def logout():
    global SESSION
    with LOCK:
        if SESSION:
            call('/v1/sign-out', {}, SESSION['token'], SESSION['base'])
            SESSION = None
        return store.sign_out()


def conflicts():
    with connection() as db:
        tables(db)
        values = []
        for row in db.execute('SELECT id,local_payload,remote_payload FROM cloud_conflicts ORDER BY id'):
            local, remote = json.loads(row['local_payload']), json.loads(row['remote_payload'])
            kind = db.execute('SELECT kind FROM sync_outbox WHERE id=?', (row['id'],)).fetchone()
            values.append({'id': row['id'], 'kind': kind['kind'] if kind else 'unknown',
                           'localSummary': conflict_summary(local), 'remoteSummary': conflict_summary(remote)})
        return {'conflicts': values}


def conflict_summary(value):
    if not isinstance(value, dict): return '记录格式无效'
    if 'plan_id' in value: return '课程 ' + str(value['plan_id'])[:8]
    if 'name' in value: return '个人资料：' + str(value['name'])[:80]
    if 'lesson_id' in value: return '课程进度：' + str(value['lesson_id'])[:80]
    return '学习摘要'


def resolve_conflict(record_id, decision):
    if decision not in ('keep-local', 'use-cloud'):
        raise ValueError('请选择保留本机或采用云端版本')
    with LOCK, connection() as db:
        tables(db)
        row = db.execute('SELECT * FROM cloud_conflicts WHERE id=?', (record_id,)).fetchone()
        if not row: raise ValueError('该冲突已不存在')
        remote = db.execute('SELECT * FROM cloud_mirror WHERE id=?', (record_id,)).fetchone()
        if not remote: raise ValueError('缺少云端版本，无法处理冲突')
        if decision == 'use-cloud':
            record = {'id': record_id, 'kind': remote['kind'], 'payload': json.loads(row['remote_payload']), 'revision': remote['revision']}
            apply_remote(db, record, force=True)
        else:
            # Keep local data dirty and advance its base revision so its next
            # normal sync creates the chosen version rather than overwriting it.
            db.execute('UPDATE sync_outbox SET version=?,dirty=1 WHERE id=?', (remote['revision'], record_id))
        db.execute('DELETE FROM cloud_conflicts WHERE id=?', (record_id,))
    return runtime_status()


def remote_action(path, payload):
    global SESSION
    with LOCK:
        if not SESSION: raise ValueError('请先登录云同步')
        result = call(path, payload, SESSION['token'], SESSION['base'])
        if path == '/v1/account/delete':
            SESSION = None
            store.delete_account(True)
            with connection() as db:
                tables(db)
                for table in ('cloud_mirror','cloud_cursor','cloud_conflicts'): db.execute(f'DELETE FROM {table}')
        return result
