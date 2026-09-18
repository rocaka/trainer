import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import learning_store as store
from datetime import date


class LearnerDashboardTests(unittest.TestCase):
    def test_empty_achievement_catalog_has_no_false_unlocks(self):
        result = store.achievement_summary([], store.activity_summary([]))
        self.assertEqual(len(result), 100)
        self.assertTrue(all(not a['unlocked'] and a['current'] == 0 for a in result))

    def test_language_records_are_not_proficiency_scores(self):
        self.assertEqual(store.language_summary([]), [])
        store.record_evidence({'conceptId': 'python.lesson', 'note': '我能说明返回值', 'language': 'python3', 'score': 100})
        result = store.dashboard()
        python = next(item for item in result['languages'] if item['name'] == 'Python')
        self.assertEqual(python['evidenceCount'], 1)
        self.assertIsNone(python['score'])
        self.assertEqual(python['status'], '待评估')
        self.assertEqual(store.normalize_language('Next.js'), '')
        many = store.language_summary([{'language': f'Language{i}'} for i in range(25)])
        self.assertEqual(len(many), 25)

    def test_github_language_and_activity_are_signals_not_learning_evidence(self):
        result = store.record_github_insights({
            'login': 'trainer-user', 'repositoryCount': 2,
            'languages': [
                {'name': 'Go', 'bytes': 900, 'repositories': 2},
                {'name': 'JavaScript', 'bytes': 100, 'repositories': 1},
            ],
            'activity': [{'day': '2026-09-01', 'count': 3}, {'day': '2026-09-02', 'count': 0}],
            'totalContributions': 3, 'commitCount': 2, 'pullRequestCount': 1, 'issueCount': 0,
        })
        self.assertEqual(result['login'], 'trainer-user')
        dashboard = store.dashboard()
        self.assertEqual(dashboard['xp'], 0)
        self.assertEqual(dashboard['evidenceCount'], 0)
        self.assertEqual(dashboard['github']['repositoryCount'], 2)
        go = next(item for item in dashboard['languages'] if item['name'] == 'Go')
        self.assertEqual(go['githubBytes'], 900)
        self.assertEqual(go['githubRepositoryCount'], 2)
        self.assertIsNone(go['score'])
        self.assertEqual(go['status'], 'GitHub 项目语言信号')
        with self.assertRaises(ValueError):
            store.record_github_insights({'login': 'bad login', 'languages': []})

    def test_local_avatar_reference_persists(self):
        reference = 'local-image:12345678-1234-1234-1234-123456789abc'
        result = store.save_profile({'name': '学习者', 'avatar': reference})
        self.assertEqual(result['profile']['avatar'], reference.upper().replace('LOCAL-IMAGE:', 'local-image:'))
        with self.assertRaises(ValueError):
            store.save_profile({'avatar': 'local-image:../../secret'})
        with self.assertRaises(ValueError):
            store.save_profile({'avatar': 'https://example.com/avatar.png'})

    def test_activity_calendar_and_streaks(self):
        rows = [{'created_at': f'2026-09-{day:02d}T12:00:00'} for day in [1, 2, 3, 5, 6, 6]]
        result = store.activity_summary(rows, today=date(2026, 9, 7))
        self.assertEqual(len(result['activity']), 365)
        self.assertEqual(result['currentStreak'], 2)
        self.assertEqual(result['longestStreak'], 3)
        self.assertEqual(result['activity'][-1]['count'], 0)
        self.assertEqual(result['activity'][-2]['count'], 2)
        self.assertEqual(store.activity_summary(rows, today=date(2026, 9, 8))['currentStreak'], 0)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = patch.object(store, 'DATABASE', Path(self.temp.name) / 'learning.sqlite3')
        self.override.start()

    def tearDown(self):
        self.override.stop()
        self.temp.cleanup()

    def test_profile_persists(self):
        store.save_profile({'name': '测试学习者', 'bio': '学习 Python', 'avatar': '🌱'})
        self.assertEqual(store.dashboard()['profile']['name'], '测试学习者')
        self.assertEqual(store.dashboard()['profile']['bio'], '学习 Python')

    def test_dimensions_and_unique_xp(self):
        payload = {'conceptId': 'course:one', 'note': '我读懂了函数返回值', 'level': 1, 'evidenceType': 'reading'}
        store.record_evidence(payload)
        store.record_evidence(payload)
        result = store.dashboard()
        self.assertEqual(result['xp'], 10)
        self.assertEqual(result['evidenceCount'], 2)
        self.assertEqual(result['dimensions'][1]['count'], 2)
        self.assertEqual(result['dimensions'][2]['count'], 0)
        self.assertTrue(result['achievements'][0]['unlocked'])

    def test_level_boundary_and_persisted_completion(self):
        plan = 'a' * 64
        for index in range(9):
            store.record_evidence({'conceptId': f'go:{plan}:lesson-{index}', 'note': '课堂凭据', 'language': 'Go'})
        self.assertEqual((store.dashboard()['xp'], store.dashboard()['level']), (90, 1))
        store.record_evidence({'conceptId': f'go:{plan}:lesson-9', 'note': '课堂凭据', 'language': 'Go'})
        self.assertEqual((store.dashboard()['xp'], store.dashboard()['level']), (100, 2))
        store.course_progress(plan, 'lesson-9')
        restored = store.course_progress(plan)
        self.assertEqual(restored['lessonId'], 'lesson-9')
        self.assertIn('lesson-0', restored['recorded'])
        self.assertEqual(len(restored['recorded']), 10)
        self.assertEqual(restored['passed'], [])

    def test_verified_code_completion_is_idempotent_and_drives_progress(self):
        plan = 'b' * 64
        store.record_course_completion('local', plan, 'lesson-1', 'submission-1', 'coach-exercise')
        store.record_course_completion('local', plan, 'lesson-1', 'submission-1', 'coach-exercise')
        self.assertEqual(store.course_progress(plan)['passed'], ['lesson-1'])
        result = store.dashboard()
        self.assertEqual(result['verifiedPracticeCount'], 1)
        self.assertEqual(result['dimensions'][2]['count'], 1)
        self.assertEqual(result['xp'], 20)
        writing = next(a for a in result['achievements'] if a['title'] == '代码编写 · 1')
        self.assertTrue(writing['unlocked'])

    def test_empty_profile_does_not_claim_mastery(self):
        result = store.dashboard()
        self.assertEqual(result['xp'], 0)
        self.assertTrue(all(d['count'] == 0 for d in result['dimensions']))
        with self.assertRaises(ValueError):
            store.record_evidence({'conceptId': 'one', 'note': 'test', 'evidenceType': 'invented'})

    def test_achievement_progress_is_based_on_distinct_learning_points(self):
        payload = {'conceptId': 'go:one', 'note': '代码练习', 'language': 'Go', 'evidenceType': 'writing'}
        for _ in range(6): store.record_evidence(payload)
        achievements = store.dashboard()['achievements']
        self.assertEqual(len(achievements), 100)
        self.assertEqual(len({a['title'] for a in achievements}), 100)
        self.assertTrue(all(0 <= a['current'] <= a['target'] for a in achievements))
        writing = next(a for a in achievements if a['title'] == '动手实践者')
        self.assertEqual(writing['current'], 0)
        self.assertFalse(writing['unlocked'])
        for i in range(4): store.record_evidence(dict(payload, conceptId=f'go:other-{i}'))
        self.assertFalse(next(a for a in store.dashboard()['achievements'] if a['title'] == '动手实践者')['unlocked'])
