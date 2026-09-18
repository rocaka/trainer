"""Local-first account identity, device registry and bounded sync outbox.

OAuth credentials remain in the native Keychain. This store only receives the
verified GitHub login and records privacy-safe learning data prepared for an
optional cloud adapter.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from learning_store import connection
from storage import DATA


def now():
    return datetime.now(timezone.utc).isoformat()


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS account_state (
        id INTEGER PRIMARY KEY CHECK(id=1), account_id TEXT NOT NULL,
        provider TEXT NOT NULL, subject TEXT NOT NULL, login TEXT NOT NULL,
        claimed_at TEXT NOT NULL, last_sync_at TEXT, sync_enabled INTEGER NOT NULL DEFAULT 1)''')
    db.execute('''CREATE TABLE IF NOT EXISTS account_devices (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, platform TEXT NOT NULL,
        created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)''')
    db.execute('''CREATE TABLE IF NOT EXISTS sync_outbox (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, version INTEGER NOT NULL,
        updated_at TEXT NOT NULL, payload_json TEXT NOT NULL, dirty INTEGER NOT NULL DEFAULT 1)''')
    db.execute('''CREATE TABLE IF NOT EXISTS local_identity (
        id INTEGER PRIMARY KEY CHECK(id=1), device_id TEXT NOT NULL)''')
    # Remove legacy answer bodies before any cloud upload becomes possible.
    for row in db.execute("SELECT id,payload_json FROM sync_outbox WHERE kind='evidence'").fetchall():
        value = json.loads(row['payload_json'])
        if 'note' in value:
            value.pop('note')
            value['concept_id'] = hashlib.sha256(value['concept_id'].encode()).hexdigest()
            db.execute('UPDATE sync_outbox SET payload_json=?,dirty=1 WHERE id=?',
                       (json.dumps(value,ensure_ascii=False),row['id']))


def current_device(db):
    initialize(db)
    row = db.execute('SELECT device_id FROM local_identity WHERE id=1').fetchone()
    if row:
        device_id = row['device_id']
    else:
        device_id = secrets.token_hex(16)
        db.execute('INSERT INTO local_identity VALUES (1,?)', (device_id,))
    stamp = now()
    name = platform.node().strip()[:80] or '这台 Mac'
    db.execute('''INSERT INTO account_devices(id,name,platform,created_at,last_seen_at,revoked)
        VALUES(?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET name=excluded.name,
        platform=excluded.platform,last_seen_at=excluded.last_seen_at,revoked=0''',
        (device_id, name, f'{platform.system()} {platform.machine()}', stamp, stamp))
    return device_id


def safe_login(value):
    login = str(value or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9-]{1,39}', login):
        raise ValueError('GitHub 账户身份无效')
    return login


def queue(db, kind, identity, payload):
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    if len(encoded.encode()) > 256 * 1024:
        raise ValueError('同步记录过大')
    record_id = hashlib.sha256(f'{kind}:{identity}'.encode()).hexdigest()
    row = db.execute('SELECT version,payload_json FROM sync_outbox WHERE id=?', (record_id,)).fetchone()
    if row and row['payload_json'] == encoded:
        return
    version = (row['version'] if row else 0) + 1
    db.execute('''INSERT OR REPLACE INTO sync_outbox(id,kind,version,updated_at,payload_json,dirty)
        VALUES(?,?,?,?,?,1)''', (record_id, kind, version, now(), encoded))


def snapshot(db, preferences=None):
    db.execute('CREATE TABLE IF NOT EXISTS profile (id TEXT PRIMARY KEY, name TEXT, bio TEXT, avatar TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS course_progress (plan_id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL)')
    profile = db.execute("SELECT name,bio,avatar FROM profile WHERE id='local'").fetchone()
    if profile:
        value = dict(profile)
        if value['avatar'] not in ('🧑‍💻','👩‍🚀','🦊','🐼','🌱'): value['avatar'] = '🧑‍💻'
        queue(db, 'profile', 'local', value)
    for row in db.execute("SELECT concept_id,level,evidence_type,note,created_at,language FROM evidence WHERE learner_id='local'"):
        identity = hashlib.sha256(json.dumps(dict(row), sort_keys=True).encode()).hexdigest()
        value = {key: row[key] for key in ('concept_id','level','evidence_type','created_at','language')}
        value['concept_id'] = hashlib.sha256(value['concept_id'].encode()).hexdigest()
        queue(db, 'evidence', identity, value)
    for row in db.execute("SELECT plan_id,lesson_id,submission_id,task_role,passed_at FROM course_completions WHERE learner_id='local'"):
        queue(db, 'course-completion', row['submission_id'], dict(row))
    for row in db.execute('SELECT plan_id,lesson_id FROM course_progress'):
        queue(db, 'course-progress', row['plan_id'], dict(row))
    # A plan is course material generated for Trainer, never a workspace copy.
    # Only complete, structurally validated plans are allowed onto the sync path.
    from teaching_plan import validate_plan
    plans = DATA / 'learning-plans'
    if plans.is_dir():
        for path in plans.glob('[0-9a-f]' * 64 + '.json'):
            try:
                plan_id = path.stem
                document = path.read_text(encoding='utf-8')
                if len(document.encode()) > 240_000:
                    continue
                plan = validate_plan(json.loads(document), aggregate=True)
                # Project-import plans may reference a project *conceptually*,
                # but their course JSON has no workspace paths or source files.
                queue(db, 'course-plan', plan_id, {'plan_id': plan_id,
                                                    'document': json.dumps(plan, ensure_ascii=False, separators=(',', ':'))})
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
    if isinstance(preferences, dict):
        allowed = {key: preferences[key] for key in ('readingSize','readingStyle','codeSize','motion') if key in preferences}
        queue(db, 'preference', 'appearance', allowed)


def claim(login, preferences=None, github_id=None):
    login = safe_login(login)
    if not isinstance(github_id, str) or not re.fullmatch('[0-9]{1,24}', github_id):
        raise ValueError('需要经过 GitHub 验证的稳定账户 ID')
    subject = hashlib.sha256(('github:' + github_id).encode()).hexdigest()
    account_id = subject[:32]
    stamp = now()
    with connection() as db:
        initialize(db)
        db.execute('CREATE TABLE IF NOT EXISTS profile_owner (id INTEGER PRIMARY KEY CHECK(id=1), subject TEXT NOT NULL)')
        existing = db.execute('SELECT subject FROM profile_owner WHERE id=1').fetchone()
        if existing and existing['subject'] != subject:
            raise ValueError('本机档案属于另一账户，请先导出备份并使用独立 macOS 用户档案')
        db.execute('INSERT OR IGNORE INTO profile_owner VALUES (1,?)', (subject,))
        db.execute('''INSERT OR REPLACE INTO account_state
            (id,account_id,provider,subject,login,claimed_at,last_sync_at,sync_enabled)
            VALUES(1,?,?,?,?,?,COALESCE((SELECT last_sync_at FROM account_state WHERE id=1),NULL),1)''',
            (account_id, 'github', subject, login, stamp))
        current_device(db)
        snapshot(db, preferences)
    return status()


def status():
    with connection() as db:
        initialize(db)
        account = db.execute('SELECT * FROM account_state WHERE id=1').fetchone()
        if not account:
            return {'signedIn': False, 'mode': 'local-only', 'message': '尚未登录；学习数据只保存在本机。',
                    'devices': [], 'pendingChanges': 0, 'lastSyncAt': None}
        device_id = current_device(db)
        devices = [{'id': row['id'], 'name': row['name'], 'platform': row['platform'],
                    'createdAt': row['created_at'], 'lastSeenAt': row['last_seen_at'], 'current': row['id'] == device_id} for row in db.execute(
            'SELECT id,name,platform,created_at,last_seen_at FROM account_devices WHERE revoked=0 ORDER BY last_seen_at DESC')]
        pending = db.execute('SELECT count(*) FROM sync_outbox WHERE dirty=1').fetchone()[0]
        return {'signedIn': True, 'accountId': account['account_id'], 'provider': account['provider'],
                'login': account['login'], 'claimedAt': account['claimed_at'], 'lastSyncAt': account['last_sync_at'],
                'mode': 'local-first', 'pendingChanges': pending, 'devices': devices,
                'message': '本机档案已认领；云端未配置时，待同步记录只保存在本机。'}


def prepare_sync(preferences=None):
    with connection() as db:
        initialize(db)
        if not db.execute('SELECT 1 FROM account_state WHERE id=1').fetchone():
            raise ValueError('请先使用 GitHub 登录并认领档案')
        current_device(db)
        snapshot(db, preferences)
        changes = db.execute('SELECT count(*) FROM sync_outbox WHERE dirty=1').fetchone()[0]
    result = status()
    result['preparedChanges'] = changes
    return result


def sign_out():
    with connection() as db:
        initialize(db)
        db.execute('DELETE FROM account_state')
    return status()


def delete_account(confirmed=False):
    if confirmed is not True:
        raise ValueError('需要确认删除账户关系')
    with connection() as db:
        initialize(db)
        db.execute('DELETE FROM account_state')
        db.execute('DELETE FROM sync_outbox')
        db.execute('UPDATE account_devices SET revoked=1')
    return {'deleted': True, 'localLearningDataPreserved': True}
