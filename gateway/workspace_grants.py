"""Workspace identity approval only; no source reading or external-send grant.

Internal API: approve/revoke belong to the authenticated native controller.
Not mounted in production until course lookup and both approval UIs are ready.
"""
import re
import secrets
from pathlib import Path
from extension_pairing import PairingError, digest
from learning_loop import connect


def identity(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('工作区路径无效')
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('需要绝对工作区路径')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('工作区路径不能包含符号链接')
    path = path.resolve(strict=True)
    if path in (Path('/'), Path.home().resolve()) or not path.is_dir():
        raise ValueError('请选择具体项目目录')
    stat = path.stat()
    return str(path), stat.st_dev, stat.st_ino


class WorkspaceGrants:
    def __init__(self, pairings):
        self.pairings = pairings
        self.path = pairings.path
        with connect(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS workspace_grants (
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL REFERENCES extension_tokens(hash),
                root TEXT NOT NULL, device INTEGER NOT NULL, inode INTEGER NOT NULL,
                plan_id TEXT NOT NULL, scope TEXT NOT NULL, created REAL NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0, revoked INTEGER NOT NULL DEFAULT 0)''')

    def request(self, token, root, plan_id):
        if not self.pairings.authorize(token, 'workspace:bind'):
            raise PairingError('配对已失效')
        if not isinstance(plan_id, str) or not re.fullmatch('[a-f0-9]{64}', plan_id):
            raise ValueError('课程标识无效')
        root, device, inode = identity(root)
        grant_id = secrets.token_hex(16)
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute('SELECT count(*) FROM workspace_grants WHERE token_hash=? AND revoked=0 AND approved=0 AND created>?',
                               (digest(token), self.pairings.clock() - 300)).fetchone()[0]
            if count >= 5: raise ValueError('待确认工作区过多')
            db.execute('INSERT INTO workspace_grants(id,token_hash,root,device,inode,plan_id,scope,created) VALUES(?,?,?,?,?,?,?,?)',
                       (grant_id, digest(token), root, device, inode, plan_id, 'workspace:metadata', self.pairings.clock()))
        return {'id': grant_id, 'root': root, 'planId': plan_id, 'scope': 'workspace:metadata'}

    def pending(self):
        with connect(self.path) as db:
            rows = db.execute('''SELECT w.id,w.root,w.plan_id,w.scope FROM workspace_grants w
                JOIN extension_tokens t ON t.hash=w.token_hash
                WHERE w.approved=0 AND w.revoked=0 AND w.created>? AND t.revoked=0 AND t.expires>?''',
                (self.pairings.clock() - 300, self.pairings.clock())).fetchall()
        return [dict(row) for row in rows]

    def approve(self, grant_id):
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT w.* FROM workspace_grants w JOIN extension_tokens t ON t.hash=w.token_hash
                WHERE w.id=? AND w.revoked=0 AND w.created>? AND t.revoked=0 AND t.expires>?''',
                (grant_id, self.pairings.clock() - 300, self.pairings.clock())).fetchone()
            if not row or identity(row['root']) != (row['root'], row['device'], row['inode']):
                raise ValueError('工作区请求已失效或目录已改变')
            # A physical workspace has one current course. Rebinding supersedes
            # every older grant for the same directory, including duplicates.
            db.execute('UPDATE workspace_grants SET revoked=1 WHERE root=? AND id<>? AND revoked=0',
                       (row['root'], grant_id))
            db.execute('UPDATE workspace_grants SET approved=1 WHERE id=?', (grant_id,))

    def active(self):
        with connect(self.path) as db:
            rows = db.execute('''SELECT w.id,w.root,w.plan_id,w.scope,w.device,w.inode FROM workspace_grants w
                JOIN extension_tokens t ON t.hash=w.token_hash
                WHERE w.approved=1 AND w.revoked=0 AND t.revoked=0 AND t.expires>?
                ORDER BY w.created DESC''', (self.pairings.clock(),)).fetchall()
        result = []
        for row in rows:
            item = {key: row[key] for key in ('id', 'root', 'plan_id', 'scope')}
            try: item['valid'] = identity(row['root']) == (row['root'], row['device'], row['inode'])
            except (OSError, ValueError): item['valid'] = False
            result.append(item)
        return result

    def authorize(self, token, grant_id):
        if not self.pairings.authorize(token, 'workspace:bind'): return False
        with connect(self.path) as db:
            row = db.execute('SELECT * FROM workspace_grants WHERE id=? AND token_hash=? AND approved=1 AND revoked=0',
                             (grant_id, digest(token))).fetchone()
        if not row: return False
        try:
            return identity(row['root']) == (row['root'], row['device'], row['inode'])
        except (OSError, ValueError):
            return False

    def revoke(self, grant_id):
        with connect(self.path) as db:
            db.execute('UPDATE workspace_grants SET revoked=1 WHERE id=?', (grant_id,))
