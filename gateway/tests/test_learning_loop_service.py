import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import learning_loop as loop
from learning_loop_service import LearningLoopService
from test_learning_loop import exercise


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / 'learning.db'
        loop.migrate(self.db)
        self.service = LearningLoopService(self.db, self.root, 'test-session')

    def tearDown(self): self.temp.cleanup()

    def test_authentication_precedes_read_or_mutation(self):
        for method, route in [('GET', '/v2/submissions/missing'), ('POST', '/v2/submissions')]:
            status, result = self.service.handle(method, route, '', b'{}')
            self.assertEqual(status, 401)
            self.assertEqual(result['error']['code'], 'unauthorized')

    def test_course_must_exist_before_exercise_is_saved(self):
        with self.assertRaises(loop.ContractError): self.service.register_exercise(exercise())
        plan = {'lessons': [{'id': 'lesson-1'}]}
        (self.root / ('a' * 64 + '.json')).write_text(json.dumps(plan))
        self.service.register_exercise(exercise())
        status, data = self.service.handle('GET', '/v2/exercises/go-reading-1?revision=1', 'test-session')
        self.assertEqual(status, 200)
        self.assertEqual(data['kind'], 'reading')

    def test_submission_read_cancel_and_ownership(self):
        loop.save_exercise(self.db, exercise())
        payload = {'exerciseId': 'go-reading-1', 'revision': 1, 'answer': '返回计算结果', 'idempotencyKey': 'one'}
        status, data = self.service.handle('POST', '/v2/submissions', 'test-session', json.dumps(payload).encode())
        self.assertEqual(status, 202)
        sid = data['id']
        self.assertEqual(self.service.handle('GET', '/v2/submissions/' + sid, 'test-session')[1]['status'], 'queued')
        self.assertEqual(self.service.handle('POST', '/v2/submissions/' + sid + '/cancel', 'test-session', b'{}')[1]['status'], 'cancelled')
        with self.assertRaises(loop.ContractError): loop.start(self.db, sid)
        other = loop.submit(self.db, 'another-user', dict(payload, idempotencyKey='two'))
        self.assertEqual(self.service.handle('GET', '/v2/submissions/' + other, 'test-session')[0], 404)

    def test_oversized_and_client_scoring_rejected(self):
        self.assertEqual(self.service.handle('POST', '/v2/submissions', 'test-session', b' ' * 65537)[0], 413)
        self.assertEqual(self.service.handle('POST', '/v2/results', 'test-session', b'{}')[0], 404)
        self.assertEqual(self.service.handle('POST', '/v2/submissions', 'test-session', b'{"x":1,"x":2}')[0], 400)

    def test_backup_restore_to_new_database_and_re_migrate(self):
        old = self.root / 'old.db'
        with sqlite3.connect(old) as db:
            db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY,note TEXT)')
            db.execute("INSERT INTO evidence VALUES(1,'before migration')")
        backup = loop.migrate(old)
        restored = self.root / 'restored.db'
        # Restore into an isolated file, never overwrite a user's database.
        with sqlite3.connect(backup) as source, sqlite3.connect(restored) as destination:
            source.backup(destination)
        loop.migrate(restored)
        with loop.connect(restored) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM loop_legacy_records').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT note FROM evidence').fetchone()[0], 'before migration')
