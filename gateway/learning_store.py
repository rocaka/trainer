"""Local SQLite learner evidence store; no model conversations or secrets are retained."""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


from storage import DATA
DATABASE = DATA / "trainer-learning.sqlite3"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connection() -> sqlite3.Connection:
    database = sqlite3.connect(DATABASE, factory=ClosingConnection)
    database.row_factory = sqlite3.Row
    database.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY,
            learner_id TEXT NOT NULL,
            concept_id TEXT NOT NULL,
            level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 6),
            evidence_type TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    database.execute("""
        CREATE TABLE IF NOT EXISTS course_completions (
            learner_id TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            lesson_id TEXT NOT NULL,
            submission_id TEXT NOT NULL UNIQUE,
            task_role TEXT NOT NULL CHECK(task_role IN ('course-task','coach-exercise')),
            passed_at TEXT NOT NULL,
            PRIMARY KEY (learner_id, plan_id, lesson_id)
        )
    """)
    database.execute("""
        CREATE TABLE IF NOT EXISTS github_insights (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            login TEXT NOT NULL,
            refreshed_at TEXT NOT NULL,
            repository_count INTEGER NOT NULL,
            languages_json TEXT NOT NULL,
            activity_json TEXT NOT NULL,
            total_contributions INTEGER NOT NULL,
            commit_count INTEGER NOT NULL,
            pull_request_count INTEGER NOT NULL,
            issue_count INTEGER NOT NULL
        )
    """)
    if 'language' not in {row[1] for row in database.execute('PRAGMA table_info(evidence)')}:
        database.execute("ALTER TABLE evidence ADD COLUMN language TEXT NOT NULL DEFAULT ''")
    return database


def record_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    learner_id = str(payload.get("learnerId", "local"))
    concept_id = str(payload.get("conceptId", "")).strip()
    evidence_type = str(payload.get("evidenceType", "reflection")).strip()
    note = str(payload.get("note", "")).strip()
    level = int(payload.get("level", 0))
    language = normalize_language(payload.get('language', ''))
    if not concept_id or not note:
        raise ValueError("conceptId and note are required.")
    if evidence_type not in {'reflection', 'reading', 'writing', 'debugging', 'transfer'}:
        raise ValueError("Unsupported evidenceType.")
    if not 0 <= level <= 6:
        raise ValueError("level must be between 0 and 6.")
    created_at = datetime.now(timezone.utc).isoformat()
    with connection() as database:
        cursor = database.execute(
            "INSERT INTO evidence (learner_id, concept_id, level, evidence_type, note, created_at, language) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (learner_id, concept_id, level, evidence_type, note, created_at, language),
        )
    refresh_account_snapshot()
    return {"id": cursor.lastrowid, "conceptId": concept_id, "level": level, "createdAt": created_at}


def learner_profile(learner_id: str = "local") -> list[dict[str, Any]]:
    with connection() as database:
        rows = database.execute("""
            SELECT concept_id, MAX(level) AS level, MAX(created_at) AS last_evidence_at, COUNT(*) AS evidence_count
            FROM evidence WHERE learner_id = ? GROUP BY concept_id ORDER BY last_evidence_at DESC
        """, (learner_id,)).fetchall()
    return [dict(row) for row in rows]

def record_course_completion(learner_id, plan_id, lesson_id, submission_id, task_role):
    import re
    if not re.fullmatch('[a-f0-9]{64}', str(plan_id)):
        raise ValueError('Invalid plan id.')
    if not all(isinstance(value, str) and value and len(value) <= 200
               for value in (learner_id, lesson_id, submission_id)):
        raise ValueError('Invalid completion identity.')
    if task_role not in ('course-task', 'coach-exercise'):
        raise ValueError('Invalid task role.')
    passed_at = datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute('''INSERT OR IGNORE INTO course_completions
            (learner_id,plan_id,lesson_id,submission_id,task_role,passed_at)
            VALUES (?,?,?,?,?,?)''', (learner_id, plan_id, lesson_id, submission_id, task_role, passed_at))
    refresh_account_snapshot()
    return {'planId': plan_id, 'lessonId': lesson_id, 'taskRole': task_role, 'passedAt': passed_at}


def course_progress(plan_id, lesson_id=None):
    import re
    if not re.fullmatch('[a-f0-9]{64}', plan_id):
        raise ValueError('Invalid plan id.')
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS course_progress (plan_id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL)')
        if lesson_id is not None:
            if not isinstance(lesson_id, str) or not lesson_id or len(lesson_id) > 200:
                raise ValueError('Invalid lesson id.')
            db.execute('INSERT OR REPLACE INTO course_progress VALUES (?,?)', (plan_id, lesson_id))
        row = db.execute('SELECT lesson_id FROM course_progress WHERE plan_id=?', (plan_id,)).fetchone()
        prefix = ':' + plan_id + ':'
        records = [r['concept_id'].split(prefix, 1)[1] for r in db.execute(
            "SELECT DISTINCT concept_id FROM evidence WHERE learner_id='local' AND concept_id LIKE ?", ('%' + prefix + '%',))]
        passed = [r['lesson_id'] for r in db.execute(
            "SELECT lesson_id FROM course_completions WHERE learner_id='local' AND plan_id=? ORDER BY passed_at", (plan_id,))]
    if lesson_id is not None: refresh_account_snapshot()
    return {'lessonId': row['lesson_id'] if row else None, 'recorded': records, 'passed': passed}


def dashboard():
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS profile (id TEXT PRIMARY KEY, name TEXT, bio TEXT, avatar TEXT)')
        row = db.execute("SELECT * FROM profile WHERE id='local'").fetchone()
        profile = dict(row) if row else {'id': 'local', 'name': '学习者', 'bio': '', 'avatar': '🧑‍💻'}
        records = [dict(row) for row in db.execute("SELECT concept_id, evidence_type, note, created_at, language FROM evidence WHERE learner_id='local' ORDER BY id DESC")]
        completions = [dict(row) for row in db.execute("SELECT plan_id,lesson_id,task_role,passed_at FROM course_completions WHERE learner_id='local' ORDER BY passed_at DESC")]
    unique = {row['concept_id'] for row in records}
    verified_practice = len({(row['plan_id'], row['lesson_id']) for row in completions})
    xp = len(unique) * 10 + verified_practice * 20
    dimensions = [{'name': name, 'count': (verified_practice if kind == 'writing' else sum(row['evidence_type'] == kind for row in records))} for name, kind in [('概念回讲', 'reflection'), ('代码阅读', 'reading'), ('代码编写', 'writing'), ('调试验证', 'debugging'), ('迁移应用', 'transfer')]]
    activity = activity_summary(records)
    github = github_summary()
    return {'profile': profile, 'xp': xp, 'level': 1 + xp // 100, 'conceptCount': len(unique), 'evidenceCount': len(records),
            'dimensions': dimensions, 'languages': language_summary(records, github.get('languages', []) if github else []), 'github': github, **activity,
            'verifiedPracticeCount': verified_practice,
            'recent': records[:20], 'achievements': achievement_summary(records, activity, completions), 'storagePath': str(DATA)}


def record_github_insights(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist only the GitHub aggregates the native app already displayed.

    GitHub OAuth tokens, source files, repository names, commit messages and file paths
    never pass through this local endpoint.
    """
    import re
    login = str(payload.get('login', '')).strip()
    if not re.fullmatch(r'[A-Za-z0-9-]{1,39}', login):
        raise ValueError('Invalid GitHub login.')
    repository_count = payload.get('repositoryCount', 0)
    if not isinstance(repository_count, int) or not 0 <= repository_count <= 100_000:
        raise ValueError('Invalid repository count.')
    totals = {}
    for key in ('totalContributions', 'commitCount', 'pullRequestCount', 'issueCount'):
        value = payload.get(key, 0)
        if not isinstance(value, int) or not 0 <= value <= 100_000_000:
            raise ValueError(f'Invalid {key}.')
        totals[key] = value
    language_totals: dict[str, dict[str, int]] = {}
    source_languages = payload.get('languages', [])
    if not isinstance(source_languages, list) or len(source_languages) > 80:
        raise ValueError('Invalid GitHub languages.')
    for item in source_languages:
        if not isinstance(item, dict):
            raise ValueError('Invalid GitHub language item.')
        name = normalize_language(item.get('name', ''))
        bytes_used = item.get('bytes', 0)
        repositories = item.get('repositories', 0)
        if not name:
            continue
        if not isinstance(bytes_used, int) or not 0 <= bytes_used <= 10**15:
            raise ValueError('Invalid GitHub language byte count.')
        if not isinstance(repositories, int) or not 0 <= repositories <= repository_count:
            raise ValueError('Invalid GitHub language repository count.')
        current = language_totals.setdefault(name, {'name': name, 'bytes': 0, 'repositories': 0})
        current['bytes'] += bytes_used
        current['repositories'] += repositories
    activities = []
    source_activity = payload.get('activity', [])
    if not isinstance(source_activity, list) or len(source_activity) > 400:
        raise ValueError('Invalid GitHub contribution activity.')
    seen_days = set()
    for item in source_activity:
        if not isinstance(item, dict) or not isinstance(item.get('day'), str) or not isinstance(item.get('count'), int):
            raise ValueError('Invalid GitHub contribution day.')
        try:
            day = datetime.fromisoformat(item['day']).date().isoformat()
        except ValueError as error:
            raise ValueError('Invalid GitHub contribution day.') from error
        if day in seen_days or not 0 <= item['count'] <= 10_000_000:
            raise ValueError('Invalid GitHub contribution day.')
        seen_days.add(day)
        activities.append({'day': day, 'count': item['count']})
    refreshed_at = datetime.now(timezone.utc).isoformat()
    languages = sorted(language_totals.values(), key=lambda item: (-item['bytes'], item['name']))
    activity = sorted(activities, key=lambda item: item['day'])
    with connection() as database:
        database.execute('''INSERT OR REPLACE INTO github_insights
            (id, login, refreshed_at, repository_count, languages_json, activity_json,
             total_contributions, commit_count, pull_request_count, issue_count)
             VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (login, refreshed_at, repository_count, json.dumps(languages), json.dumps(activity),
             totals['totalContributions'], totals['commitCount'], totals['pullRequestCount'], totals['issueCount']))
    return github_summary() or {}


def github_summary() -> dict[str, Any] | None:
    with connection() as database:
        row = database.execute('SELECT * FROM github_insights WHERE id = 1').fetchone()
    if not row:
        return None
    try:
        languages = json.loads(row['languages_json'])
        activity = json.loads(row['activity_json'])
    except (TypeError, json.JSONDecodeError):
        return None
    return {'login': row['login'], 'refreshedAt': row['refreshed_at'],
            'repositoryCount': row['repository_count'], 'languages': languages, 'activity': activity,
            'totalContributions': row['total_contributions'], 'commitCount': row['commit_count'],
            'pullRequestCount': row['pull_request_count'], 'issueCount': row['issue_count'],
            'privacy': '仅保存仓库语言字节聚合与贡献日历；不保存源码、仓库名、文件路径、提交信息或 OAuth 令牌。'}


def achievement_summary(records, activity, completions=()):
    unique = len({row['concept_id'] for row in records})
    languages = len({row.get('language') for row in records if row.get('language')})
    rules = [(title, unique, target, f'记录 {target} 个不同学习点', 'books.vertical')
             for title, target in [('首次记录', 1), ('持续探索', 5), ('十项足迹', 10), ('学习积累', 30), ('百课足迹', 100)]]
    rules += [(title, activity['longestStreak'], target, f'连续 {target} 天提交学习凭据', 'flame.fill')
              for title, target in [('三日同行', 3), ('一周坚持', 7), ('月度坚持', 30)]]
    rules += [('语言探索者', languages, 2, '为 2 种语言记录学习凭据', 'curlybraces'),
              ('多语言足迹', languages, 5, '为 5 种语言记录学习凭据', 'globe')]
    verified = len({(row['plan_id'], row['lesson_id']) for row in completions})
    for kind, title in [('reading', '阅读观察者'), ('writing', '动手实践者'), ('debugging', '调试记录者'), ('transfer', '迁移尝试者')]:
        count = verified if kind == 'writing' else len({row['concept_id'] for row in records if row['evidence_type'] == kind})
        detail = '在 5 个不同学习点通过代码任务静态评审' if kind == 'writing' else '在 5 个不同学习点提交该类型凭据（自述记录）'
        rules.append((title, count, 5, detail, 'pencil.and.list.clipboard'))
    # Preserve the original 14 milestones; add 86 deterministic, evidence-backed tiers.
    for target in [2, 3, 8, 15, 20, 40, 50, 75, 150, 200, 300, 500]:
        rules.append((f'学习足迹 · {target}', unique, target, f'记录 {target} 个不同学习点', 'books.vertical'))
    for target in [2, 5, 10, 14, 21, 45, 60, 90, 180, 365]:
        rules.append((f'连续学习 · {target} 天', activity['longestStreak'], target, f'连续 {target} 天提交凭据', 'flame'))
    for target in [1, 3, 4, 6, 8, 10]:
        rules.append((f'语言足迹 · {target}', languages, target, f'为 {target} 种语言提交记录，不代表掌握', 'globe'))
    for target in [1, 3, 7, 14, 30, 60, 100, 180]:
        rules.append((f'活跃积累 · {target} 天', activity['activeDays'], target, f'累计 {target} 天提交凭据，无需连续', 'calendar'))
    for kind, label in [('reflection', '概念回讲'), ('reading', '代码阅读'), ('writing', '代码编写'), ('debugging', '调试验证'), ('transfer', '迁移应用')]:
        count = verified if kind == 'writing' else len({row['concept_id'] for row in records if row['evidence_type'] == kind})
        for target in [1, 2, 3, 10, 15, 20, 30, 50, 75, 100]:
            detail = (f'在 {target} 个不同学习点通过代码任务静态评审' if kind == 'writing'
                      else f'在 {target} 个不同学习点提交{label}记录（自述，非能力认证）')
            rules.append((f'{label} · {target}', count, target, detail, 'pencil.and.list.clipboard'))
    return [{'title': title, 'unlocked': count >= target, 'current': min(count, target),
             'target': target, 'detail': detail, 'icon': icon} for title, count, target, detail, icon in rules]


def activity_summary(records, today=None):
    today = today or datetime.now().astimezone().date()
    days = {}
    for row in records:
        try:
            day = datetime.fromisoformat(row['created_at']).astimezone().date()
        except (ValueError, TypeError):
            continue
        if day <= today:
            days[day] = days.get(day, 0) + 1
    longest = run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    dates = [today - timedelta(days=364 - index) for index in range(365)]
    return {'activity': [{'day': day.isoformat(), 'count': days.get(day, 0)} for day in dates],
            'currentStreak': current, 'longestStreak': longest, 'activeDays': len(days)}


def normalize_language(value):
    names = ['Python', 'JavaScript', 'TypeScript', 'SQL', 'Swift', 'Rust', 'Go', 'Java', 'C', 'C++', 'C#', 'Kotlin', 'Ruby', 'PHP', 'Solidity', 'Dart', 'R', 'Bash']
    aliases = {name.lower(): name for name in names}
    aliases.update({'python3': 'Python', 'js': 'JavaScript', 'ts': 'TypeScript', 'golang': 'Go', 'csharp': 'C#'})
    text = str(value).strip()
    if text.lower() in aliases:
        return aliases[text.lower()]
    # Preserve additional course-declared languages without a fixed count cap.
    # Common frameworks and ambiguous combined labels are not language axes.
    if text.lower() in {'next.js', 'nextjs', 'react', 'vue', 'fastapi', 'django', 'node.js', 'langgraph', 'postgresql', 'unknown', '未识别'}:
        return ''
    import re
    return text if re.fullmatch(r'[A-Za-z][A-Za-z0-9+# .-]{0,39}', text) else ''


def language_summary(records, github_languages=()):
    names = []
    for record in records:
        language = normalize_language(record.get('language', ''))
        if language and language not in names:
            names.append(language)
    # Practice and self-reports do not establish an assessed proficiency score.
    from assessments import language_estimates
    estimates = language_estimates()
    names.extend(name for name in estimates if name and name not in names)
    github_by_name = {normalize_language(item.get('name', '')): item for item in github_languages
                      if isinstance(item, dict) and normalize_language(item.get('name', ''))}
    names.extend(name for name in github_by_name if name not in names)
    return [{'name': name, 'evidenceCount': sum(normalize_language(r.get('language', '')) == name for r in records),
             'score': estimates.get(name, {}).get('score'),
             'githubBytes': github_by_name.get(name, {}).get('bytes', 0),
             'githubRepositoryCount': github_by_name.get(name, {}).get('repositories', 0),
             'status': f"AI 课堂评估 · {estimates[name]['count']} 项" if name in estimates
                       else ('GitHub 项目语言信号' if name in github_by_name else '待评估')}
            for name in names]


def save_profile(payload):
    dashboard()
    name = str(payload.get('name', '')).strip()[:60] or '学习者'
    bio = str(payload.get('bio', ''))[:500]
    avatar = str(payload.get('avatar', '🧑‍💻'))
    if avatar.startswith('local-image:'):
        from uuid import UUID
        avatar = 'local-image:' + str(UUID(avatar.removeprefix('local-image:'))).upper()
    elif avatar not in ['🧑‍💻', '👩‍🚀', '🦊', '🐼', '🌱']:
        raise ValueError('请选择内置头像或上传有效的本地图片。')
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO profile VALUES (?, ?, ?, ?)', ('local', name, bio, avatar))
    refresh_account_snapshot()
    return dashboard()


def refresh_account_snapshot():
    """Keep the local outbox current after account claim; never blocks learning writes."""
    try:
        from account_store import prepare_sync
        prepare_sync()
    except (ImportError, ValueError, sqlite3.Error):
        pass
