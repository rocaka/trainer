"""Internal click-submit preparation; not mounted on HTTP and never sends to AI.

The trusted caller resolves the exercise and root from the binding. guard must
recheck binding identity, source consent and fresh editor metadata each time.
Fingerprint is material identity, not permission to reuse failed evaluations.
"""
import hashlib

from learning_loop import encode
from submission_plan import plan_materials
from submission_snapshot import collect_snapshot, SnapshotBlocked


def prepare_materials(contract, root, *, answer='', report='', guard):
    # Freeze caller-owned values before validation and filesystem work.
    import json
    contract = json.loads(encode(contract))
    paths = sorted(contract.get('requiredFiles', []))

    def check():
        state = guard(paths)
        if not isinstance(state, dict) or state.get('valid') is not True:
            raise SnapshotBlocked('工作区关联或源码授权已失效')
        plan = plan_materials(contract, state.get('authorizedPaths', []),
                              state.get('dirtyPaths', []),
                              buffers_fresh=state.get('buffersFresh') is True,
                              answer=answer, report=report)
        if not plan['readyForSnapshot']:
            raise SnapshotBlocked('提交材料检查未通过：' + ', '.join(i['code'] for i in plan['issues']))

    for value in (answer, report):
        if not isinstance(value, str) or len(value) > 16000:
            raise SnapshotBlocked('说明或报告格式无效或超过长度限制')
    check()
    snapshot = collect_snapshot(root, paths) if paths else {'files': [], 'totalBytes': 0, 'version': 1}
    # Revocation or editing while collecting invalidates the entire result.
    check()
    identity = {'version': 1, 'contract': contract, 'answer': answer, 'report': report,
                'files': [{k: item[k] for k in ('path', 'sha256', 'bytes')} for item in snapshot['files']]}
    fingerprint = hashlib.sha256(encode(identity).encode('utf-8')).hexdigest()
    return {'exerciseId': contract['exerciseId'], 'revision': contract['revision'],
            'answer': answer, 'report': report, 'snapshot': snapshot,
            'materialFingerprint': fingerprint}
