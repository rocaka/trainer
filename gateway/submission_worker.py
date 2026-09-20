"""Internal static-review worker. No production provider or scheduler attached.

Trusted loader returns (registered contract, immutable prepared materials).
authorize must verify current consent for this learner, material and evaluator.
Provider transport failures are not retried: external outcome may be unknown.
"""
import hashlib
import json
from urllib.error import HTTPError, URLError

from learning_loop import encode, fields, text, validate_exercise
import submission_queue as queue

FAILURE_MESSAGES = {
    'interrupted': '应用重启中断了此次评判，未收到有效结果；可重新提交。',
    'materials': '提交材料校验失败，请保存任务文件后重新提交。',
    'consent': '本次提交授权已失效，请重新提交。',
    'timeout': 'AI 服务响应超时，请稍后重新提交。',
    'network': '无法连接 AI 服务，请检查网络后重新提交。',
    'authentication': 'AI 服务密钥无效或权限不足，请检查 AI 服务设置。',
    'rate_limit': 'AI 服务限流或额度不足，请检查服务账户后重试。',
    'provider': 'AI 服务请求失败，请检查模型与接口设置后重试。',
    'response': 'AI 返回的评分格式或引用未通过校验，请重新提交。',
    'score_keys': 'AI 返回的评分项与本课验收项不一致，请重新提交。',
    'score_range': 'AI 返回了无效分值，请重新提交。',
    'quote_mismatch': 'AI 引用未能对应提交原文，未保存此次评分，请重新提交。',
    'unknown': '此次评判未完成，未产生有效评分；可重新提交。',
}


def validate_materials(contract, materials, fingerprint):
    validate_exercise(contract)
    if contract['verificationRequirement'] != 'static_review':
        raise ValueError('当前执行器仅支持静态评判')
    files = materials['snapshot']['files']
    if [f['path'] for f in files] != sorted(contract.get('requiredFiles', [])):
        raise ValueError('材料文件范围与题目不一致')
    for item in files:
        raw = item['content'].encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != item['sha256'] or len(raw) != item['bytes']:
            raise ValueError('材料内容已变化')
    identity = {'version': 1, 'contract': contract, 'answer': materials['answer'],
                'report': materials['report'],
                'files': [{k: f[k] for k in ('path', 'sha256', 'bytes')} for f in files]}
    if hashlib.sha256(encode(identity).encode('utf-8')).hexdigest() != fingerprint:
        raise ValueError('提交指纹不匹配')


def validate_result(contract, materials, result):
    fields(result, 'scores quote feedback nextStep')
    for name in ('quote', 'feedback', 'nextStep'):
        text(result[name])
    rubric = contract['rubric']
    scores = result['scores']
    if not isinstance(scores, dict) or set(scores) != {r['id'] for r in rubric}:
        raise ValueError('评分项不匹配')
    for item in rubric:
        score = scores[item['id']]
        if type(score) is not int or not 0 <= score <= item['maxScore']:
            raise ValueError('评分越界')
    sources = [materials['answer'], materials['report']] + [f['content'] for f in materials['snapshot']['files']]
    if not any(result['quote'] in source for source in sources):
        raise ValueError('引用不在提交材料中')
    return {**result, 'method': 'static_review',
            'outcome': 'passed' if sum(scores.values()) >= contract['passRule']['minimumScore'] else 'needs_revision'}


def run_one(path, *, load, authorize, evaluate, job_id=None):
    job = queue.claim_next(path, job_id=job_id)
    if job is None:
        return None
    stage = 'materials'
    try:
        contract, materials = load(job)
        # Prevent callbacks from mutating the validated original.
        contract, materials = json.loads(encode([contract, materials]))
        validate_materials(contract, materials, job['fingerprint'])
        stage = 'consent'
        if authorize(dict(job)) is not True:
            raise ValueError('AI 外发许可无效')
        stage = 'provider'
        result = evaluate(*json.loads(encode([contract, materials])), job['evaluator_key'])
        stage = 'response'
        result = validate_result(contract, materials, result)
    except Exception as error:
        # Never persist provider exceptions: they can contain credentials/source.
        code = stage
        if isinstance(error, HTTPError):
            code = 'authentication' if error.code in (401, 403) else 'rate_limit' if error.code in (402, 429) else 'provider'
        elif isinstance(error, TimeoutError): code = 'timeout'
        elif isinstance(error, URLError): code = 'timeout' if isinstance(error.reason, TimeoutError) else 'network'
        elif stage == 'response':
            code = {'评分项不匹配': 'score_keys', '评分越界': 'score_range',
                    '引用不在提交材料中': 'quote_mismatch'}.get(str(error), 'response')
        queue.finish(path, job['id'], job['claim'], 'failed', code)
        return {'id': job['id'], 'status': 'failed'}
    # DB failures after an external call leave evaluating, never auto-resubmit.
    queue.complete(path, job['id'], job['claim'], result)
    return {'id': job['id'], 'status': 'completed', 'outcome': result['outcome']}
