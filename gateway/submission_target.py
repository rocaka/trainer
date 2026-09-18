"""Resolve an explicitly bound submit target, never the latest chat question.

Inputs must come from trusted persisted course/session state, not model output.
Legacy exercises without provenance cannot be guessed into a submission source.
"""
from learning_loop import validate_exercise


def resolve_target(contracts, *, mode, plan_id, lesson_id, task_id, revision, role=None):
    default_roles = {'project-practice': 'course-task', 'project-import': 'coach-exercise',
                     'course': 'course-task'}
    if mode not in default_roles or type(revision) is not int or revision < 1:
        raise ValueError('提交上下文无效')
    role = role or default_roles[mode]
    if role not in ('course-task', 'coach-exercise'):
        raise ValueError('任务来源无效')
    matches = []
    for contract in contracts:
        source = contract.get('taskSource')
        if (contract.get('planId') == plan_id and contract.get('lessonId') == lesson_id
                and contract.get('revision') == revision
                and source == {'mode': mode, 'role': role, 'taskId': task_id}):
            validate_exercise(contract)
            matches.append(contract)
    if len(matches) != 1:
        raise ValueError('提交任务未明确绑定或存在冲突，请刷新当前课程任务')
    # Return an immutable-by-copy contract; callers must still verify authorization.
    import json
    from learning_loop import encode
    return json.loads(encode(matches[0]))
