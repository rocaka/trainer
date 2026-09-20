"""Read-only, metadata-minimal views of the existing saved course library.

This is the same learning-plans catalog exposed to workspace pairing. Opening a
course never generates content, initializes stores, or updates the saved plan.
Only complete plans accepted by the canonical teaching validator are exposed.
"""
import json
import re
import stat
from itertools import islice
from pathlib import Path

from teaching_plan import validate_plan

MAX_PLAN_BYTES = 16 * 1024 * 1024
MAX_COURSES = 1000
LESSON_FIELDS = ('id', 'title', 'objective', 'language', 'code', 'explanation',
                 'syntax', 'rationale', 'exercise', 'reflection', 'contentType')


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def _read_plan(data, plan_id):
    if not isinstance(plan_id, str) or not re.fullmatch('[a-f0-9]{64}', plan_id):
        raise ValueError('课程编号无效。')
    root = Path(data) / 'learning-plans'
    path = root / (plan_id + '.json')
    try:
        if _linked(root) or _linked(path):
            raise ValueError('课程文件不可用。')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PLAN_BYTES:
            raise ValueError('课程文件过大或不可读取。')
        with path.open('rb') as stream:
            raw = stream.read(MAX_PLAN_BYTES + 1)
        if len(raw) > MAX_PLAN_BYTES:
            raise ValueError('课程文件过大。')
        return validate_plan(json.loads(raw), aggregate=True)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        # Do not expose absolute paths, decoding excerpts, or stored metadata.
        raise ValueError('课程不存在或内容不完整，请刷新课程列表。') from error


def _title(plan):
    for field in ('title', 'skillTitle', 'skillId'):
        value = plan.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()[:160]
    modules = plan.get('moduleTitles')
    if isinstance(modules, list) and modules and isinstance(modules[0], str) and modules[0].strip():
        return ('完整课程 · ' + re.sub(r'^\s*\d+[.、]\s*', '', modules[0]))[:160]
    return plan['lessons'][0]['title'].strip()[:160]


def list_courses(data):
    root = Path(data) / 'learning-plans'
    if _linked(root):
        raise ValueError('课程目录不可用。')
    # Checkpoint, maintenance and outline files are deliberately excluded.
    paths = list(islice((p for p in root.glob('*.json')
                        if re.fullmatch('[a-f0-9]{64}', p.stem)), MAX_COURSES + 1))
    if len(paths) > MAX_COURSES:
        raise ValueError('课程数量超出当前读取上限，请使用原版管理课程。')
    courses = []
    for path in sorted(paths):
        try:
            plan = _read_plan(data, path.stem)
            courses.append({'id': path.stem, 'title': _title(plan),
                            'lessonCount': len(plan['lessons'])})
        except ValueError:
            continue
    return {'courses': courses}


def read_course(data, plan_id):
    plan = _read_plan(data, plan_id)
    lessons = []
    for lesson in plan['lessons']:
        item = {key: lesson[key] for key in LESSON_FIELDS}
        if 'practiceTask' in lesson:
            task = lesson['practiceTask']
            item['practiceTask'] = {'prompt': task['prompt'],
                                    'requiredFiles': list(task['requiredFiles']),
                                    'acceptance': list(task['acceptance'])}
        lessons.append(item)
    return {'id': plan_id, 'title': _title(plan), 'lessons': lessons}
