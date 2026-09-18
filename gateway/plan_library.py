"""Opening a saved course is independent from model generation and rule revisions."""
import json
import re
import os
import hashlib
from copy import deepcopy
from pathlib import Path
from teaching_plan import validate_plan, PLAN_SCHEMA, TEACHING_FORMAT_RULES, IncompletePlanError, audit_coverage
from teaching_review import review_module
from jobs import checkpoint, progress, publish_partial, current_id


def preserve_course_reference(data, job):
    """Detach a completed course from task history before that history is deleted."""
    recipe = job.get('recipe') or {}
    payload = recipe.get('payload') or {}
    result = job.get('result') or {}
    skill_id, plan_id = payload.get('skillId'), result.get('planId')
    if (job.get('status') != 'completed' or recipe.get('kind') != 'plan'
            or not isinstance(skill_id, str) or not skill_id.strip()
            or not isinstance(plan_id, str) or not re.fullmatch('[0-9a-f]{64}', plan_id)):
        return False
    plan_path = Path(data) / 'learning-plans' / (plan_id + '.json')
    validate_plan(json.loads(plan_path.read_text()), aggregate=True)
    directory = Path(data) / 'saved-courses'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (plan_id + '.json')
    value = {'skillId': skill_id, 'planId': plan_id, 'createdAt': job.get('createdAt', '')}
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, destination)
    return True

def saved_plan(data, skill_id, plan_id=None):
    candidates = []
    for path in (Path(data) / 'job-history').glob('*.json'):
        try:
            job = json.loads(path.read_text())
            if job.get('recipe', {}).get('payload', {}).get('skillId') != skill_id:
                continue
            result = job.get('result') or {}
            key = result.get('planId', '')
            if job.get('status') == 'completed' and re.fullmatch('[0-9a-f]{64}', key) and (not plan_id or key == plan_id):
                candidates.append((job.get('createdAt', ''), key))
        except (ValueError, AttributeError):
            continue
    for path in (Path(data) / 'saved-courses').glob('*.json'):
        try:
            item = json.loads(path.read_text())
            key = item.get('planId', '')
            if item.get('skillId') == skill_id and re.fullmatch('[0-9a-f]{64}', key) and (not plan_id or key == plan_id):
                candidates.append((item.get('createdAt', ''), key))
        except (ValueError, AttributeError):
            continue
    for _, key in sorted(candidates, reverse=True):
        try:
            plan = validate_plan(json.loads((Path(data) / 'learning-plans' / (key + '.json')).read_text()), aggregate=True)
            return {**plan, 'planId': key, 'cached': True}
        except (OSError, ValueError, TypeError):
            continue
    raise ValueError('尚无可打开的已保存课程。请点击“生成/升级课程”；打开课程不会自动调用 AI。')

def maintain_plan(data, plan, documents, generate, supplement=False, rules=''):
    key = plan['planId']
    root = Path(data) / 'learning-plans'
    mode = 'supplement' if supplement else 'review'
    run_id = current_id() or hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    run_path = root / (key + '-maintenance-' + mode + '-' + run_id + '.json')
    def save(path, value):
        checkpoint()
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, path)
    if run_path.exists():
        state = json.loads(run_path.read_text())
    else:
        state = {'base': plan, 'responses': {}, 'rules': rules}
        save(run_path, state)
    base = state['base']
    # Cache each successful response BEFORE applying it. A resumed job replays
    # committed steps without another model request or duplicated lesson IDs.
    def request(name, prompt, schema):
        if name not in state['responses']:
            for attempt in range(2):
                checkpoint()
                try:
                    result = generate(prompt, schema)
                    if 'lessons' in schema['properties']:
                        validate_plan(result, min_lessons=1)
                        if len(result['lessons']) != 1:
                            raise IncompletePlanError('补课步骤需要恰好一课。')
                    state['responses'][name] = result
                    save(run_path, state)
                    break
                except IncompletePlanError:
                    if attempt:
                        raise IncompletePlanError('当前步骤仍返回不完整内容。成功步骤已保存，请继续本次任务，无需升级课程。')
                    progress(0, 0, '当前步骤返回不完整，正在小批重试（1/1）')
        return state['responses'][name]
    scope_by_title = {}
    outline_path = root / (key + '-outline.json')
    if outline_path.exists():
        try:
            scope_by_title = {m['title']: m['scope'] for m in json.loads(outline_path.read_text())['modules']}
        except (ValueError, KeyError, TypeError):
            pass
    groups = {}
    for lesson in base['lessons']:
        group = lesson['source'].split(' · ')[0]
        groups.setdefault(group, []).append(lesson)
    reports, additions = [], []
    def commit():
        existing = json.loads((root / (key + '.json')).read_text())
        all_lessons = {x['id']: x for x in base['lessons']}
        all_lessons.update({x['id']: x for x in existing['lessons']})
        all_lessons.update({x['id']: x for x in additions})
        updated = {**base, 'lessons': list(all_lessons.values()), 'contentReviews': list(reports), 'contentReviewVersion': 1}
        updated['coverageAudit'] = audit_coverage(updated)
        validate_plan(updated, aggregate=True)
        save(root / (key + '.json'), updated)
        publish_partial(updated)
        return updated
    for index, (label, lessons) in enumerate(groups.items()):
        checkpoint()
        progress(index, len(groups), label + ' · 正在核验（不重写原课程）')
        scope = scope_by_title.get(label, label + '\n' + '\n'.join(x['objective'] for x in lessons))
        report = review_module(label, scope, lessons, lambda p, s: request(f'{index}-review', p, s))
        missing = [f for f in report['findings'] if f['status'] == 'missing']
        reports.append(report)
        commit()
        if supplement and missing:
            schema = deepcopy(PLAN_SCHEMA)
            schema['properties']['lessons'].update(minItems=1, maxItems=1)
            added = []
            for number, finding in enumerate(missing):
                progress(index, len(groups), f'{label} · 补齐缺项 {number + 1}/{len(missing)}')
                prompt = state.get('rules', rules) + TEACHING_FORMAT_RULES + '\n仅生成一课，补以下缺项，不重复原课。保留语言、项目语境和安全边界。\n模块范围：' + scope + '\n缺项：' + json.dumps(finding, ensure_ascii=False) + '\n当前课程语言与目标：' + json.dumps([{'language': x['language'], 'objective': x['objective']} for x in lessons], ensure_ascii=False)
                extra = request(f'{index}-addition-{number}', prompt, schema)
                lesson = {**extra['lessons'][0], 'id': f'supplement-{run_id[:12]}-{index}-{number}', 'source': label + ' · 缺项补充'}
                added.append(lesson); additions.append(lesson)
                commit()
            progress(index, len(groups), label + ' · 正在复查补课结果')
            reports[-1] = review_module(label, scope, lessons + added, lambda p, s: request(f'{index}-recheck', p, s))
        updated = commit()
    unresolved = sum(f['status'] != 'covered' for r in reports for f in r['findings'])
    progress(len(groups), len(groups), f'检查完成 · {len(additions)} 课已补入 · {unresolved} 项仍待确认' if supplement else f'检查完成 · {unresolved} 项待确认，未改写原课')
    return updated
