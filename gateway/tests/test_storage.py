import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import storage


class StorageTests(unittest.TestCase):
    def test_evidence_merge_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'gateway').mkdir()
            data = root / 'data'
            data.mkdir()
            with sqlite3.connect(root / 'gateway/trainer-learning.sqlite3') as db:
                db.execute('CREATE TABLE evidence (learner_id TEXT, concept_id TEXT, level INTEGER, evidence_type TEXT, note TEXT, created_at TEXT)')
                db.execute("INSERT INTO evidence VALUES ('local', 'lesson', 1, 'reading', 'old note', '2026-09-07')")
            with patch.object(storage, 'ASSETS', root), patch.object(storage, 'DATA', data):
                storage.merge_legacy_evidence()
                (data / '.evidence-migration-v2-complete').unlink()
                storage.merge_legacy_evidence()
            with sqlite3.connect(data / 'trainer-learning.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0], 1)

    def test_migration_preserves_database_and_existing_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, data = root / 'old-app', root / 'data'
            (assets / 'skills/demo').mkdir(parents=True)
            (assets / 'skills/demo/SKILL.md').write_text('old')
            (assets / 'gateway').mkdir()
            with sqlite3.connect(assets / 'gateway/trainer-learning.sqlite3') as db:
                db.execute('CREATE TABLE sample (note TEXT)')
                db.execute("INSERT INTO sample VALUES ('preserved')")
            (data / 'skills/demo').mkdir(parents=True)
            target = data / 'skills/demo/SKILL.md'
            target.write_text('new')
            with patch.object(storage, 'ASSETS', assets), patch.object(storage, 'DATA', data):
                storage.initialize()
                self.assertEqual(target.read_text(), 'new')
                with sqlite3.connect(data / 'trainer-learning.sqlite3') as db:
                    self.assertEqual(db.execute('SELECT note FROM sample').fetchone()[0], 'preserved')
                target.unlink()
                storage.initialize()
                self.assertFalse(target.exists(), 'Cleaned assets must not reappear on restart')
                self.assertTrue((assets / 'skills/demo/SKILL.md').exists())
