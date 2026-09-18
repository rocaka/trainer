"""Deployable Trainer account service. Run behind HTTPS, never expose Gateway.

Only this module and cloud_schema.py are required on the server. GitHub tokens
are validated directly with GitHub and discarded; sessions are stored hashed.
"""
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.request import Request, build_opener, HTTPRedirectHandler
from cloud_schema import validate_record


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def github_identity(token):
    if not isinstance(token, str) or not 10 <= len(token) <= 512 or any(c.isspace() for c in token):
        raise ValueError('Invalid GitHub credential')
    request = Request('https://api.github.com/user', headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
        'User-Agent': 'Trainer-Account', 'X-GitHub-Api-Version': '2022-11-28'})
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        value = json.loads(response.read(65537))
    if type(value.get('id')) is not int or value['id'] <= 0 or not isinstance(value.get('login'), str):
        raise ValueError('GitHub identity missing')
    return str(value['id']), value['login']


class ServiceError(Exception):
    def __init__(self, status, message): self.status, self.message = status, message


class AccountService:
    def __init__(self, database, verify=github_identity, clock=time.time):
        self.database, self.verify, self.clock = str(database), verify, clock
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, login TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS devices(user_id TEXT, id TEXT, name TEXT, seen REAL,
                    revoked INTEGER DEFAULT 0, PRIMARY KEY(user_id,id));
                CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,user_id TEXT,device_id TEXT,expires REAL);
                CREATE TABLE IF NOT EXISTS records(user_id TEXT,id TEXT,kind TEXT,payload TEXT,
                    revision INTEGER,PRIMARY KEY(user_id,id));
                CREATE TABLE IF NOT EXISTS revisions(user_id TEXT PRIMARY KEY,value INTEGER);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def authenticate(self, db, token):
        row = db.execute('''SELECT s.user_id,s.device_id FROM sessions s JOIN devices d
            ON d.user_id=s.user_id AND d.id=s.device_id WHERE s.hash=? AND s.expires>? AND d.revoked=0''',
            (hashlib.sha256(token.encode()).hexdigest(), self.clock())).fetchone()
        if not row: raise ServiceError(401, 'Session expired or device signed out')
        db.execute('UPDATE devices SET seen=? WHERE user_id=? AND id=?', (self.clock(), *row))
        return row['user_id'], row['device_id']

    def handle(self, path, body, token=''):
        if not isinstance(body, dict): raise ServiceError(400, 'Invalid request')
        if path == '/v1/session':
            device = body.get('deviceId', '')
            if not isinstance(device, str) or len(device) != 32 or any(c not in '0123456789abcdef' for c in device):
                raise ServiceError(400, 'Invalid device')
            name = body.get('deviceName', 'Mac')
            if not isinstance(name, str) or not 1 <= len(name) <= 80: raise ServiceError(400, 'Invalid name')
            try: user_id, login = self.verify(body.get('githubToken'))
            except Exception: raise ServiceError(401, 'GitHub authentication failed') from None
            session = secrets.token_urlsafe(32)
            with self.db() as db:
                db.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (user_id, login))
                db.execute('INSERT OR REPLACE INTO devices VALUES (?,?,?,?,0)', (user_id, device, name, self.clock()))
                db.execute('DELETE FROM sessions WHERE expires<? OR (user_id=? AND device_id=?)', (self.clock(), user_id, device))
                db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                           (hashlib.sha256(session.encode()).hexdigest(), user_id, device, self.clock() + 2592000))
            return {'token': session, 'userId': user_id, 'login': login}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            user, device = self.authenticate(db, token)
            if path == '/v1/sync':
                changes, cursor = body.get('changes', []), body.get('cursor', 0)
                if not isinstance(changes, list) or len(changes) > 100 or type(cursor) is not int or cursor < 0:
                    raise ServiceError(400, 'Invalid sync batch')
                accepted, conflicts = [], []
                for change in changes:
                    try: validate_record(change)
                    except ValueError: raise ServiceError(400, 'Invalid sync record') from None
                    row = db.execute('SELECT * FROM records WHERE user_id=? AND id=?', (user, change['id'])).fetchone()
                    payload = json.dumps(change['payload'], sort_keys=True, ensure_ascii=False)
                    if row and row['kind'] != change['kind']: raise ServiceError(400, 'Record kind mismatch')
                    if row and row['payload'] == payload:
                        accepted.append({'id': row['id'], 'revision': row['revision']}); continue
                    if (row['revision'] if row else 0) != change['baseRevision']:
                        conflicts.append(change['id']); continue
                    if row and change['kind'] in ('evidence', 'course-completion'):
                        conflicts.append(change['id']); continue
                    count = db.execute('SELECT count(*) FROM records WHERE user_id=?', (user,)).fetchone()[0]
                    if not row and count >= 100000: raise ServiceError(413, 'Account record limit reached')
                    db.execute('INSERT INTO revisions VALUES (?,1) ON CONFLICT(user_id) DO UPDATE SET value=value+1', (user,))
                    revision = db.execute('SELECT value FROM revisions WHERE user_id=?', (user,)).fetchone()[0]
                    db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)', (user, change['id'], change['kind'], payload, revision))
                    accepted.append({'id': change['id'], 'revision': revision})
                rows = db.execute('SELECT * FROM records WHERE user_id=? AND revision>? ORDER BY revision LIMIT 101', (user, cursor)).fetchall()
                page = rows[:100]
                return {'accepted': accepted, 'conflicts': conflicts,
                        'records': [{'id': r['id'], 'kind': r['kind'], 'payload': json.loads(r['payload']), 'revision': r['revision']} for r in page],
                        'cursor': page[-1]['revision'] if page else cursor, 'hasMore': len(rows) > 100}
            if path == '/v1/devices':
                return {'devices': [dict(r) | {'current': r['id'] == device} for r in db.execute(
                    'SELECT id,name,seen,revoked FROM devices WHERE user_id=?', (user,))]}
            if path in ('/v1/sign-out', '/v1/devices/revoke'):
                target = device if path.endswith('sign-out') else body.get('deviceId')
                db.execute('UPDATE devices SET revoked=1 WHERE user_id=? AND id=?', (user, target))
                db.execute('DELETE FROM sessions WHERE user_id=? AND device_id=?', (user, target))
                return {'ok': True}
            if path == '/v1/account/delete':
                if body.get('confirmed') is not True: raise ServiceError(400, 'Confirmation required')
                for table in ('records', 'devices', 'sessions', 'revisions'):
                    db.execute(f'DELETE FROM {table} WHERE user_id=?', (user,))
                db.execute('DELETE FROM users WHERE id=?', (user,))
                return {'deleted': True}
            raise ServiceError(404, 'Not found')


class Application:
    def __init__(self, service): self.service = service
    def __call__(self, environ, start_response):
        try:
            if environ.get('REQUEST_METHOD') != 'POST': raise ServiceError(405, 'POST required')
            if environ.get('HTTP_ORIGIN'): raise ServiceError(403, 'Browser requests are not supported')
            size = int(environ.get('CONTENT_LENGTH') or '0')
            if not 0 < size <= 1048576: raise ServiceError(413, 'Request too large')
            token = environ.get('HTTP_AUTHORIZATION', '').removeprefix('Bearer ')
            result = self.service.handle(environ.get('PATH_INFO'), json.loads(environ['wsgi.input'].read(size)), token)
            status = 200
        except ServiceError as error: status, result = error.status, {'error': error.message}
        except (ValueError, TypeError): status, result = 400, {'error': 'Invalid request'}
        except Exception: status, result = 503, {'error': 'Service unavailable'}
        data = json.dumps(result, ensure_ascii=False).encode()
        from http import HTTPStatus
        start_response(f'{status} {HTTPStatus(status).phrase}', [('Content-Type','application/json'),
            ('Content-Length',str(len(data))), ('Cache-Control','no-store')])
        return [data]


def create_app():
    return Application(AccountService(os.environ.get('TRAINER_ACCOUNT_DATABASE', '/data/accounts.sqlite3')))
