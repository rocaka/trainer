"""Click-triggered preparation logic. No file reads, uploads or evaluation.

Contract comes from the registered immutable exercise, not client/AI free text.
Caller supplies freshly validated authorization and workspace buffer metadata.
Readiness here is NOT external-send consent or proof that files exist on disk.
"""
from learning_loop import validate_exercise


def plan_materials(contract, authorized_paths, dirty_paths, *, buffers_fresh=False,
                   answer='', report=''):
    validate_exercise(contract)
    required = sorted(contract.get('requiredFiles', []))
    spec = contract['submissionSpec']
    issues = []
    if spec['code'] and not required:
        issues.append({'code': 'missing_file_contract', 'message': '题目尚未指定代码材料范围，请先完善题目。'})
    unauthorized = sorted(set(required) - set(authorized_paths))
    if unauthorized:
        issues.append({'code': 'authorization_required', 'paths': unauthorized})
    if required and not buffers_fresh:
        issues.append({'code': 'buffer_status_unavailable', 'message': '请连接 VS Code 后重试保存状态检查。'})
    dirty = sorted(set(required) & set(dirty_paths))
    if dirty:
        issues.append({'code': 'unsaved_files', 'paths': dirty})
    for name, value in [('answer', answer), ('report', report)]:
        if spec[name] and (not isinstance(value, str) or not value.strip()):
            issues.append({'code': 'missing_' + name})
    if contract['verificationRequirement'] == 'trusted_execution':
        issues.append({'code': 'execution_evidence_unavailable'})
    return {'exerciseId': contract['exerciseId'], 'revision': contract['revision'],
            'paths': required, 'issues': issues, 'readyForSnapshot': not issues}
