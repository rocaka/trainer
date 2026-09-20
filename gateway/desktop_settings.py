"""Authenticated desktop settings. Never persist or return a secret."""
import json
import os
from pathlib import Path
import tempfile
from model_transport import normalize_settings, key_service


def public_settings(data, read_secret):
    path = Path(data) / 'ai-service.json'
    value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    result = {'enabled': bool(value.get('enabled')), 'protocol': value.get('protocol', 'chat-completions'),
              'endpoint': value.get('endpoint', ''), 'model': value.get('model', ''), 'hasKey': False}
    if result['endpoint'] and result['model']:
        result['hasKey'] = bool(read_secret(key_service(normalize_settings(result)), 'Trainer'))
    return result


def save_settings(data, payload, read_secret, write_secret):
    if not isinstance(payload, dict) or set(payload) != {'endpoint', 'model', 'protocol', 'secret', 'consent'}:
        raise ValueError('设置字段不完整或包含不支持的字段')
    if payload['consent'] is not True:
        raise ValueError('请明确允许向此 AI 服务发送课程与已授权材料')
    for name, limit in [('endpoint', 2048), ('model', 200), ('protocol', 32), ('secret', 2560)]:
        if not isinstance(payload[name], str) or len(payload[name]) > limit:
            raise ValueError('配置字段格式或长度不正确')
    settings = normalize_settings({key: payload[key] for key in ('endpoint', 'model', 'protocol')})
    service = key_service(settings)
    settings['enabled'] = True
    if payload['secret']:
        write_secret(service, 'Trainer', payload['secret'])
    elif not read_secret(service, 'Trainer'):
        raise ValueError('此服务尚未保存密钥，请输入密钥')
    root = Path(data)
    root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.ai-service-', dir=root)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(settings, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, root / 'ai-service.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'saved': True, 'settings': {**settings, 'hasKey': True}}
