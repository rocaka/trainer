import tempfile
import unittest
from pathlib import Path

from submission_snapshot import collect_snapshot, SnapshotBlocked


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.joinpath('main.go').write_text('package main\n', encoding='utf-8')

    def collect(self, paths, **kwargs):
        return collect_snapshot(self.root, paths, **kwargs)

    def test_multiple_files_frozen_and_deterministic(self):
        self.root.joinpath('test.go').write_text('package main\n// test\n')
        result = self.collect(['test.go', 'main.go'])
        self.assertEqual(result, self.collect(['main.go', 'test.go', 'main.go']))
        self.assertEqual(len(result['files']), 2)
        self.root.joinpath('main.go').write_text('changed')
        self.assertEqual(result['files'][0]['content'], 'package main\n')
        self.assertNotEqual(result['digest'], self.collect(['test.go', 'main.go'])['digest'])

    def test_path_escape_and_symlink_blocked(self):
        self.root.joinpath('link.go').symlink_to(self.root / 'main.go')
        for path in ['../secret', '/etc/passwd', 'link.go', 'a/../main.go', 'a\\b', '']:
            with self.subTest(path=path), self.assertRaises(SnapshotBlocked):
                self.collect([path])

    def test_sensitive_names_and_contents_block_entire_snapshot(self):
        self.root.joinpath('.env').write_text('SECRET=value')
        self.root.joinpath('token.go').write_text('key = "sk-' + 'a' * 40 + '"')
        for path in ['.env', 'token.go']:
            with self.assertRaises(SnapshotBlocked) as failure:
                self.collect(['main.go', path])
            self.assertNotIn('a' * 40, str(failure.exception))

    def test_binary_and_limits_no_truncation(self):
        self.root.joinpath('binary').write_bytes(b'\x00hello')
        self.root.joinpath('invalid').write_bytes(b'\xff')
        for path in ['binary', 'invalid']:
            with self.assertRaises(SnapshotBlocked): self.collect([path])
        with self.assertRaises(SnapshotBlocked): self.collect(['main.go'], max_file_bytes=2)
        self.root.joinpath('two').write_text('123456789')
        with self.assertRaises(SnapshotBlocked): self.collect(['main.go', 'two'], max_total_bytes=15)
        with self.assertRaises(SnapshotBlocked): self.collect(['main.go', 'two'], max_files=1)

    def test_empty_missing_and_directory_are_blocked(self):
        with self.assertRaises(SnapshotBlocked): self.collect([])
        with self.assertRaises(SnapshotBlocked): self.collect(['missing'])
        self.root.joinpath('folder').mkdir()
        with self.assertRaises(SnapshotBlocked): self.collect(['folder'])

    def test_linked_parent_hardlink_and_fifo_blocked(self):
        import os
        self.root.joinpath('nested').mkdir()
        self.root.joinpath('alias').symlink_to(self.root / 'nested', target_is_directory=True)
        with self.assertRaises(SnapshotBlocked):
            collect_snapshot(self.root / 'alias', ['file'])
        os.link(self.root / 'main.go', self.root / 'hard.go')
        with self.assertRaises(SnapshotBlocked): self.collect(['hard.go'])
        os.mkfifo(self.root / 'pipe')
        with self.assertRaises(SnapshotBlocked): self.collect(['pipe'])

    def test_file_mutation_during_read_blocks_batch(self):
        from unittest.mock import patch
        import submission_snapshot as snapshot
        original = snapshot.os.read
        def mutate(fd, length):
            result = original(fd, length)
            if result: self.root.joinpath('main.go').write_text('different content')
            return result
        with patch.object(snapshot.os, 'read', side_effect=mutate):
            with self.assertRaises(SnapshotBlocked): self.collect(['main.go'])
