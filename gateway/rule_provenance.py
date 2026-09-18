"""Server-authored rule fingerprints; never a claim of content correctness."""
import hashlib
import json
import re


def compare_rules(saved, context):
    if (not isinstance(saved, dict) or saved.get('generationMode') not in ('course', 'project-practice', 'project-import')
            or not isinstance(saved.get('fingerprint'), str) or not re.fullmatch('[a-f0-9]{64}', saved['fingerprint'])):
        return {'status': 'unknown', 'message': '旧版未记录有效规则版本，无法判断是否同步；原课程仍可使用。'}
    current = provenance(context, saved['generationMode'])
    matches = saved['fingerprint'] == current['fingerprint']
    return {'status': 'current' if matches else 'changed',
            'message': '候选生成规则与当前一致；不代表内容已验证。' if matches else '候选生成规则已变化，可通过“继续优化”生成新候选；不会自动改写原版。',
            'savedFingerprint': saved['fingerprint'], 'currentFingerprint': current['fingerprint']}


def provenance(context, mode):
    sources = {name: hashlib.sha256(text.encode('utf-8')).hexdigest()
               for name, text in sorted(context.items())}
    value = {'builderVersion': 'candidate-v2', 'generationMode': mode, 'sources': sources}
    value['fingerprint'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    value['verification'] = 'rules-recorded-not-content-verified'
    return value
