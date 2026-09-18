import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import learning_loop as loop


def exercise():
    return {'exerciseId': 'go-reading-1', 'revision': 1, 'planId': 'a' * 64,
            'lessonId': 'lesson-1', 'kind': 'reading', 'prompt': '说明返回值',
            'learningObjectives': ['读懂返回值'], 'submissionSpec': {'answer': True, 'code': False, 'report': False},
            'contextHints': [], 'rubric': [{'id': 'meaning', 'description': '准确解释返回值', 'maxScore': 4}],
            'passRule': {'minimumScore': 3}, 'verificationRequirement': 'static_review'}


class LearningLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_migration_repeat_and_legacy_backup(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, note TEXT)')
            db.execute('INSERT INTO evidence VALUES(1, ?)', ('历史内容',))
            db.execute('CREATE TABLE assessments(id INTEGER PRIMARY KEY, score INTEGER)')
            db.execute('INSERT INTO assessments VALUES(1,4)')
        backup = loop.migrate(self.path)
        self.assertTrue(backup.exists())
        self.assertIsNone(loop.migrate(self.path))
        with loop.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM loop_legacy_records').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM loop_rewards').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT note FROM evidence').fetchone()[0], '历史内容')
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute('SELECT note FROM evidence').fetchone()[0], '历史内容')
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='loop_exercises'").fetchone())

    def test_transaction_rolls_back_schema_on_bad_legacy(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE evidence(note TEXT)')
        with self.assertRaises(ValueError): loop.migrate(self.path)
        with sqlite3.connect(self.path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='loop_exercises'").fetchone())

    def test_contract_and_immutable_revision(self):
        loop.migrate(self.path)
        loop.save_exercise(self.path, exercise())
        loop.save_exercise(self.path, exercise())
        edited = exercise(); edited['prompt'] = '不同题目'
        with self.assertRaises(loop.ContractError): loop.save_exercise(self.path, edited)
        edited['revision'] = 2
        loop.save_exercise(self.path, edited)
        for change in [{'kind': 'invented'}, {'revision': True}, {'extra': 'bad'}, {'kind': 'writing'}]:
            with self.assertRaises(loop.ContractError): loop.validate_exercise(dict(exercise(), **change))

    def test_submit_cannot_choose_kind_or_reuse_key_for_new_answer(self):
        loop.migrate(self.path); loop.save_exercise(self.path, exercise())
        payload = {'exerciseId': 'go-reading-1', 'revision': 1, 'answer': '返回的是计算结果', 'idempotencyKey': 'test-submit-1'}
        first = loop.submit(self.path, 'local', payload)
        self.assertEqual(loop.submit(self.path, 'local', payload), first)
        with self.assertRaises(loop.ContractError): loop.submit(self.path, 'local', dict(payload, kind='writing'))
        with self.assertRaises(loop.ContractError): loop.submit(self.path, 'local', dict(payload, answer='改了答案'))
        with loop.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM loop_submissions').fetchone()[0], 1)

    def test_result_and_reward_are_atomic_and_unique(self):
        loop.migrate(self.path); loop.save_exercise(self.path, exercise())
        payload = {'exerciseId': 'go-reading-1', 'revision': 1, 'answer': '返回的是计算结果', 'idempotencyKey': 'key-1'}
        sid = loop.submit(self.path, 'local', payload)
        result = {'scores': {'meaning': 3}, 'quote': '计算结果', 'feedback': '解释正确', 'nextStep': '进入下一题'}
        with self.assertRaises(loop.ContractError): loop.finish(self.path, sid, result, 'model-test')
        loop.start(self.path, sid)
        with self.assertRaises(loop.ContractError): loop.finish(self.path, sid, dict(result, quote='编造引用'), 'model-test')
        self.assertEqual(loop.finish(self.path, sid, result, 'model-test'), 'passed')
        self.assertEqual(loop.finish(self.path, sid, result, 'model-test'), 'passed')
        sid2 = loop.submit(self.path, 'local', dict(payload, idempotencyKey='key-2'))
        loop.start(self.path, sid2); loop.finish(self.path, sid2, result, 'model-test')
        with loop.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM loop_results').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT sum(xp) FROM loop_rewards').fetchone()[0], 10)

    def test_file_and_execution_contracts_fail_closed_in_p1(self):
        loop.migrate(self.path)
        item = exercise(); item['kind'] = 'writing'; item['submissionSpec']['code'] = True
        loop.save_exercise(self.path, item)
        with self.assertRaises(loop.ContractError):
            loop.submit(self.path, 'local', {'exerciseId': item['exerciseId'], 'revision': 1, 'answer': '自述完成', 'idempotencyKey': 'key-1'})

    def test_reward_failure_rolls_back_result_and_status(self):
        loop.migrate(self.path); loop.save_exercise(self.path, exercise())
        sid = loop.submit(self.path, 'local', {'exerciseId': 'go-reading-1', 'revision': 1, 'answer': '返回计算结果', 'idempotencyKey': 'key-1'})
        loop.start(self.path, sid)
        with loop.connect(self.path) as db:
            db.execute("CREATE TRIGGER fail_reward BEFORE INSERT ON loop_rewards BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            loop.finish(self.path, sid, {'scores': {'meaning': 4}, 'quote': '计算结果', 'feedback': '正确', 'nextStep': '继续'}, 'test-model')
        with loop.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM loop_submissions').fetchone()[0], 'evaluating')
            self.assertEqual(db.execute('SELECT count(*) FROM loop_results').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM loop_events WHERE kind='passed'").fetchone()[0], 0)

    def test_schema_fields_match_runtime_fixture(self):
        schema = json.loads((Path(__file__).resolve().parents[2] / 'docs/contracts/learning-loop-v2.schema.json').read_text())
        self.assertEqual(set(schema['$defs']['exercise']['required']), set(exercise()))
        self.assertNotIn('kind', schema['$defs']['textSubmission']['properties'])


if __name__ == '__main__': unittest.main()
