"""P2 pairing primitives, not exposed to HTTP yet.

approve/revoke must only be called by the native app's authenticated controller.
Tokens allow binding only; file access still needs a separate workspace grant.
Store in a private, non-backed-up credentials DB, not the learning DB.
"""
import hashlib
import hmac
import secrets
import time
from pathlib import Path
from learning_loop import connect


class PairingError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Pairings:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        if self.path.is_symlink(): raise PairingError('凭据库不能是符号链接')
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        # Caller supplies a private local path; no implicit production migration.
        with connect(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS pairings (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, code_hash TEXT NOT NULL,
                claim_hash TEXT NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                approved INTEGER NOT NULL DEFAULT 0, consumed INTEGER NOT NULL DEFAULT 0)''')
            db.execute('''CREATE TABLE IF NOT EXISTS extension_tokens (
                hash TEXT PRIMARY KEY, pairing_id TEXT NOT NULL, scope TEXT NOT NULL,
                expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)''')
        self.path.chmod(0o600)

    def request(self, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80: raise PairingError('客户端名称无效')
        pair_id, claim = secrets.token_hex(16), secrets.token_urlsafe(32)
        code = f'{secrets.randbelow(1000000):06d}'
        expires = self.clock() + 300
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute('SELECT count(*) FROM pairings WHERE expires>? AND consumed=0', (self.clock(),)).fetchone()[0]
            if count >= 5: raise PairingError('待确认配对过多，请稍后重试')
            db.execute('INSERT INTO pairings(id,name,code_hash,claim_hash,expires) VALUES(?,?,?,?,?)',
                       (pair_id, name.strip(), digest(pair_id + code), digest(claim), expires))
        return {'id': pair_id, 'code': code, 'claimSecret': claim, 'expiresAt': expires}

    def approve(self, pair_id, code):
        valid = False
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM pairings WHERE id=?', (pair_id,)).fetchone()
            if row and row['expires'] > self.clock() and row['attempts'] < 5 and not row['consumed']:
                valid = isinstance(code, str) and hmac.compare_digest(row['code_hash'], digest(pair_id + code))
                db.execute('UPDATE pairings SET attempts=attempts+1, approved=? WHERE id=?', (int(valid), pair_id))
        # Raise after commit, otherwise failed attempts would roll back.
        if not valid: raise PairingError('配对码错误、过期或尝试次数超限')

    def redeem(self, pair_id, claim):
        if not isinstance(claim, str) or len(claim) > 200: raise PairingError('配对凭证无效')
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM pairings WHERE id=?', (pair_id,)).fetchone()
            if not row or not row['approved'] or row['consumed'] or row['expires'] <= self.clock() or not hmac.compare_digest(row['claim_hash'], digest(claim)):
                raise PairingError('配对尚未确认、已过期或已领取')
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO extension_tokens(hash,pairing_id,scope,expires) VALUES(?,?,?,?)', (digest(token), pair_id, 'workspace:bind', self.clock() + 30 * 86400))
            db.execute('UPDATE pairings SET consumed=1 WHERE id=?', (pair_id,))
        return token

    def authorize(self, token, scope):
        if not isinstance(token, str) or not 20 <= len(token) <= 200: return False
        with connect(self.path) as db:
            row = db.execute('SELECT * FROM extension_tokens WHERE hash=?', (digest(token),)).fetchone()
        return bool(row and not row['revoked'] and row['expires'] > self.clock() and row['scope'] == scope)

    def revoke(self, token):
        with connect(self.path) as db:
            db.execute('UPDATE extension_tokens SET revoked=1 WHERE hash=?', (digest(token),))
