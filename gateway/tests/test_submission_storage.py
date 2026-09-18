import os
from pathlib import Path
import tempfile
import unittest

from submission_storage import private_database
import submission_queue as queue


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)

    def test_private_creation_and_reopen(self):
        path = private_database(self.root)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        queue.initialize(path)
        self.assertEqual(private_database(self.root), path)

    def test_public_directory_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            private_database(self.root)
        self.assertFalse((self.root / 'submissions.sqlite3').exists())

    def test_existing_public_file_not_chmodded(self):
        path = self.root / 'submissions.sqlite3'
        path.touch(mode=0o644)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            private_database(self.root)
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_symlink_database_rejected(self):
        target = self.root / 'other'
        target.write_text('unchanged')
        (self.root / 'submissions.sqlite3').symlink_to(target)
        with self.assertRaises((OSError, ValueError)):
            private_database(self.root)
        self.assertEqual(target.read_text(), 'unchanged')

    def test_hard_link_rejected(self):
        path = private_database(self.root)
        os.link(path, self.root / 'alias')
        with self.assertRaises(ValueError):
            private_database(self.root)

    def test_companion_symlink_rejected(self):
        private_database(self.root)
        (self.root / 'submissions.sqlite3-wal').symlink_to(self.root / 'elsewhere')
        with self.assertRaises(ValueError):
            private_database(self.root)
