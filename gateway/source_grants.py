"""Explicit source-read consent, separate from metadata binding and AI external send.

Internal only: approve/revoke must be invoked by an authenticated native controller
after a user reviews the exact file list. No production endpoint mounts this module.
Stored with private pairing credentials, never with portable learning backups.
"""
import json
import secrets
from learning_loop import connect
from submission_snapshot import checked_path


def scope_paths(paths):
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= 100:
        raise ValueError('请选择 1–100 个明确文件')
    for path in paths:
        checked_path(path)
        if any(c in path for c in '*?[]'):
            raise ValueError('源码授权仅支持明确路径，不接受通配符')
    return sorted(set(paths))


class SourceGrants:
    def __init__(self, workspaces):
        self.workspaces = workspaces
        self.path = workspaces.path
        with connect(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS source_read_grants (
                id TEXT PRIMARY KEY, binding_id TEXT NOT NULL REFERENCES workspace_grants(id),
                paths_json TEXT NOT NULL, created REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0)''')

    def approve(self, binding_id, paths):
        paths = scope_paths(paths)
        if not any(g['id'] == binding_id and g['valid'] for g in self.workspaces.active()):
            raise ValueError('目录绑定已失效，请重新确认')
        grant_id = secrets.token_hex(16)
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            # Recheck revocation/expiry in the write transaction. Read authorization
            # also rechecks directory identity and pairing at the point of use.
            active = db.execute('''SELECT w.id FROM workspace_grants w
                JOIN extension_tokens t ON t.hash=w.token_hash
                WHERE w.id=? AND w.approved=1 AND w.revoked=0 AND t.revoked=0 AND t.expires>?''',
                (binding_id, self.workspaces.pairings.clock())).fetchone()
            if not active: raise ValueError('目录绑定已失效')
            db.execute('INSERT INTO source_read_grants(id,binding_id,paths_json,created) VALUES(?,?,?,?)',
                       (grant_id, binding_id, json.dumps(paths), self.workspaces.pairings.clock()))
        return grant_id

    def authorize(self, token, grant_id, paths):
        try: requested = scope_paths(paths)
        except ValueError: return False
        with connect(self.path) as db:
            row = db.execute('SELECT * FROM source_read_grants WHERE id=? AND revoked=0', (grant_id,)).fetchone()
        if not row or not self.workspaces.authorize(token, row['binding_id']): return False
        return set(requested).issubset(json.loads(row['paths_json']))

    def revoke(self, grant_id):
        with connect(self.path) as db:
            db.execute('UPDATE source_read_grants SET revoked=1 WHERE id=?', (grant_id,))

    def list_native(self):
        """Native UI only. No tokens or source content leave the credential store."""
        bindings = {item['id']: item for item in self.workspaces.active()}
        with connect(self.path) as db:
            rows = db.execute('SELECT id,binding_id,paths_json,created FROM source_read_grants WHERE revoked=0 ORDER BY created DESC').fetchall()
        return [{'id': row['id'], 'bindingId': row['binding_id'], 'paths': json.loads(row['paths_json']),
                 'created': row['created'], 'valid': bool(bindings.get(row['binding_id'], {}).get('valid')),
                 'scope': 'source:read', 'externalSend': False} for row in rows]
