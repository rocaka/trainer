"""Runtime data lives outside the replaceable application bundle."""
import os
import shutil
from pathlib import Path
from contextlib import closing

from platform_paths import assets_directory, data_directory

ASSETS = assets_directory()
DATA = data_directory()

def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    marker = DATA / '.migration-v1-complete'
    if marker.exists():
        return
    # The installed bundle may contain newer user data than the development tree.
    legacy_bundle = ASSETS / 'dist/Trainer.app/Contents/Resources'
    sources = [legacy_bundle, ASSETS] if legacy_bundle.is_dir() else [ASSETS]
    for name in ('skills', 'pending-approvals', 'learning-plans', 'job-history'):
        for assets in sources:
            source, destination = assets / name, DATA / name
            if source.exists():
                for path in source.rglob('*'):
                    if path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents):
                        target = destination / path.relative_to(source)
                        if not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(path, target)
    old = next((root / 'gateway/trainer-learning.sqlite3' for root in sources if (root / 'gateway/trainer-learning.sqlite3').exists()), ASSETS / 'gateway/trainer-learning.sqlite3')
    target = DATA / 'trainer-learning.sqlite3'
    if old.exists() and not target.exists():
        import sqlite3
        with closing(sqlite3.connect(old)) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
    marker.write_text('Runtime data migrated; original assets preserved.\n')

def merge_legacy_evidence():
    """Merge developer-era records too; never replace current profile or evidence."""
    import sqlite3
    marker = DATA / '.evidence-migration-v2-complete'
    if marker.exists():
        return
    roots = [ASSETS, ASSETS / 'dist/Trainer.app/Contents/Resources']
    if ASSETS.name == 'Resources' and len(ASSETS.parents) > 3:
        development = ASSETS.parents[3]
        if (development / 'gateway/storage.py').is_file():
            roots.append(development)
    columns = 'learner_id, concept_id, level, evidence_type, note, created_at'
    for root in roots:
        old = root / 'gateway/trainer-learning.sqlite3'
        if not old.is_file():
            continue
        with closing(sqlite3.connect(f'file:{old}?mode=ro', uri=True)) as source:
            if not source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence'").fetchone():
                continue
            records = source.execute(f'SELECT {columns} FROM evidence').fetchall()
        with closing(sqlite3.connect(DATA / 'trainer-learning.sqlite3')) as target, target:
            target.execute('CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY, learner_id TEXT NOT NULL, concept_id TEXT NOT NULL, level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 6), evidence_type TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)')
            for record in records:
                found = target.execute('SELECT 1 FROM evidence WHERE learner_id=? AND concept_id=? AND level=? AND evidence_type=? AND note=? AND created_at=?', record).fetchone()
                if not found:
                    target.execute(f'INSERT INTO evidence ({columns}) VALUES (?, ?, ?, ?, ?, ?)', record)
    marker.write_text('Legacy evidence merged without replacing current records.\n')


initialize()
merge_legacy_evidence()
