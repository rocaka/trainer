import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import backup


class BackupTests(unittest.TestCase):
    def test_export_preserves_database_and_excludes_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(root / 'trainer-learning.sqlite3') as db:
                db.execute('CREATE TABLE sample(value TEXT)')
                db.execute("INSERT INTO sample VALUES ('retained')")
            (root / 'skills').mkdir()
            (root / 'skills/SKILL.md').write_text('course')
            (root / 'lesson-tasks').mkdir()
            (root / 'lesson-tasks/task.json').write_text('{"task": {}}')
            (root / 'private.txt').write_text('excluded')
            (root / 'skills/link.md').symlink_to(root / 'private.txt')
            with patch.object(backup, 'DATA', root):
                result = backup.create_backup()
            with zipfile.ZipFile(result['path']) as archive:
                self.assertIn('skills/SKILL.md', archive.namelist())
                self.assertIn('lesson-tasks/task.json', archive.namelist())
                self.assertNotIn('skills/link.md', archive.namelist())
                self.assertIn('backup-manifest.json', archive.namelist())
                restored = root / 'restored'
                restored.mkdir()
                archive.extract('trainer-learning.sqlite3', restored)
            with sqlite3.connect(restored / 'trainer-learning.sqlite3') as db:
                self.assertEqual(db.execute('SELECT value FROM sample').fetchone()[0], 'retained')
