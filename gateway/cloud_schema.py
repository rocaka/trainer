"""Allowlisted wire format: excludes answers, local paths and project source.

Course plans are deliberately included: they are authored teaching material, not
workspace files.  The receiving desktop validates and restores them as courses.
"""
import json
import re


def validate_record(record):
    if not isinstance(record, dict) or set(record) != {'id','kind','payload','baseRevision'}: raise ValueError()
    if not isinstance(record['id'], str) or not re.fullmatch('[a-f0-9]{64}', record['id']): raise ValueError()
    if type(record['baseRevision']) is not int or record['baseRevision'] < 0: raise ValueError()
    schemas = {
        'profile': {'name': str, 'bio': str, 'avatar': str},
        'evidence': {'concept_id': str, 'level': int, 'evidence_type': str, 'created_at': str, 'language': str},
        'course-completion': {'plan_id': str, 'lesson_id': str, 'submission_id': str, 'task_role': str, 'passed_at': str},
        'course-progress': {'plan_id': str, 'lesson_id': str},
        'course-plan': {'plan_id': str, 'document': str},
        'preference': {'readingSize': (int,float), 'readingStyle': str, 'codeSize': (int,float), 'motion': bool},
    }
    spec = schemas.get(record['kind']); payload = record['payload']
    if not spec or not isinstance(payload, dict) or set(payload) != set(spec): raise ValueError()
    for key, value in payload.items():
        expected = spec[key] if isinstance(spec[key], tuple) else (spec[key],)
        if type(value) not in expected: raise ValueError()
        if isinstance(value, str) and len(value) > (240_000 if key == 'document' else 500 if key == 'bio' else 200): raise ValueError()
    if 'plan_id' in payload and not re.fullmatch('[a-f0-9]{64}', payload['plan_id']): raise ValueError()
    if record['kind'] == 'evidence':
        if not re.fullmatch('[a-f0-9]{64}', payload['concept_id']) or not 0 <= payload['level'] <= 6: raise ValueError()
        if payload['evidence_type'] not in ('reflection','reading','writing','debugging','transfer'): raise ValueError()
    if record['kind'] == 'profile' and payload['avatar'] not in ('🧑‍💻','👩‍🚀','🦊','🐼','🌱'): raise ValueError()
    if record['kind'] == 'preference':
        if not 13 <= payload['readingSize'] <= 22 or not 12 <= payload['codeSize'] <= 22: raise ValueError()
        if payload['readingStyle'] not in ('system','rounded','serif'): raise ValueError()
    if record['kind'] == 'course-completion' and payload['task_role'] not in ('course-task','coach-exercise'): raise ValueError()
    if record['kind'] == 'course-plan':
        try:
            document = json.loads(payload['document'])
        except (TypeError, ValueError): raise ValueError() from None
        if not isinstance(document, dict) or not isinstance(document.get('lessons'), list) or not 3 <= len(document['lessons']) <= 320:
            raise ValueError()
    return record
