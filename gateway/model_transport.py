"""Responses adapter for the explicitly configured Trainer relay."""
import json
import hashlib
import socket
import ssl
import time
import uuid
import sys
import subprocess
from io import BytesIO
from email.parser import Parser
from copy import deepcopy
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener, Request
from storage import DATA

class NoRelayRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a supplied credential to a redirect destination.
        return None

def relay_open(request, timeout):
    if sys.platform == 'darwin':
        return native_open(request, timeout)
    return build_opener(NoRelayRedirect()).open(request, timeout=timeout)

def native_open(request, timeout):
    """Use macOS' installed TLS/network stack, with no shell or secret argv.

    -q ignores user curl config (which could enable redirects/insecure TLS).
    Credentials and body only travel through stdin. No automatic retries.
    Response/header buffers are bounded; redirect responses remain errors.
    """
    url = urlparse(request.full_url)
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('远程请求必须使用 HTTPS')
    config = 'url = ' + json.dumps(request.full_url) + '\n'
    config += 'request = ' + json.dumps(request.get_method()) + '\n'
    for name, value in request.header_items():
        if '\r' in value or '\n' in value:
            raise ValueError('请求头不能包含换行')
        config += 'header = ' + json.dumps(name + ': ' + value) + '\n'
    if request.data is not None:
        config += 'data = ' + json.dumps(request.data.decode('utf-8'), ensure_ascii=False) + '\n'
    try:
        result = subprocess.run(
            ['/usr/bin/curl', '-q', '--silent', '--show-error', '--globoff',
             '--max-time', str(timeout), '--connect-timeout', str(min(timeout, 15)),
             '--max-filesize', '16777216', '--proto', '=https,http',
             '--dump-header', '/dev/stderr', '--write-out', '\n%{http_code}', '--config', '-'],
            input=config.encode('utf-8'), capture_output=True, timeout=timeout + 2)
    except subprocess.TimeoutExpired:
        raise TimeoutError('上游请求超时') from None
    if result.returncode:
        if result.returncode == 28:
            raise TimeoutError('上游请求超时')
        if result.returncode in (51, 58, 60, 77, 83, 90, 91):
            raise URLError(ssl.SSLError('系统 TLS 校验失败'))
        # Never return curl stderr: it can contain reflected sensitive headers.
        raise URLError(f'macOS 网络请求失败（curl {result.returncode}）')
    body, _, status_text = result.stdout.rpartition(b'\n')
    try:
        status = int(status_text)
    except ValueError:
        raise ValueError('网络响应缺少 HTTP 状态') from None
    blocks = result.stderr.decode('iso-8859-1').replace('\r\n', '\n').split('\n\n')
    header_block = next((block for block in reversed(blocks) if block.startswith('HTTP/')), '')
    headers = Parser().parsestr(header_block.partition('\n')[2])
    if status < 200 or status >= 300:
        raise HTTPError(request.full_url, status, 'Upstream request failed', headers, BytesIO(body))
    response = BytesIO(body)
    response.headers = headers
    response.status = status
    return response

def build_request(provider, endpoint, key, body, session=None):
    """One authenticated request path for diagnostics and all teaching calls.

    Identify Trainer honestly; never impersonate a browser or another agent.
    Job IDs survive module retries. Other callers supply a lesson/conversation ID.
    """
    from jobs import current_id
    payload = request_body(provider, body)
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
               'Accept': 'application/json', 'User-Agent': 'Trainer/0.1.1'}
    url = urlparse(endpoint)
    if url.scheme == 'https' and url.hostname == 'opencode.ai' and url.path.startswith('/zen/go/'):
        identity = current_id() or session or str(uuid.uuid4())
        headers['x-opencode-session'] = 'trainer-' + hashlib.sha256(identity.encode()).hexdigest()
        if provider == 'custom-chat':
            payload['temperature'] = 1
    return Request(endpoint, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')

def http_failure(error):
    """Report diagnostic metadata, never arbitrary upstream text or credentials."""
    # Some compatible services return billing errors as HTTP 401 and label
    # their JSON as text/plain. Read only a bounded body and map known codes;
    # never echo upstream messages (which can contain account URLs or secrets).
    try:
        raw = error.read(16385)
        value = json.loads(raw) if len(raw) <= 16384 else {}
        detail = value.get('error', {}) if isinstance(value, dict) else {}
        kind = detail.get('type') or detail.get('code') if isinstance(detail, dict) else None
        if kind in ('CreditsError', 'insufficient_quota', 'insufficient_balance'):
            return f'HTTP {error.code}：AI 服务账户余额或可用额度不足，请在服务商控制台检查余额与套餐后重试。无需仅因此更换 API 密钥。'
    except (ValueError, TypeError, OSError, AttributeError):
        pass
    messages = {401: '鉴权失败：密钥无效或不属于此服务。', 403: '服务拒绝访问；仅凭状态码不能确定是账号权限、网络还是服务策略。',
                404: '接口路径或模型不存在。', 429: '额度不足或请求限流。',
                400: '服务不接受此模型、协议或请求参数。', 405: '接口方法不支持。'}
    content_type = (error.headers or {}).get('Content-Type', '').lower()
    kind = 'JSON' if 'json' in content_type else '非 JSON'
    return f'HTTP {error.code}（{kind} 响应）：' + messages.get(error.code, '上游异常或拒绝重定向；未转发密钥。')

def normalize_settings(value):
    value = dict(value)
    protocol = value.get('protocol', 'responses')
    if protocol not in ('responses', 'chat-completions'):
        raise ValueError('请选择 Responses 或 Chat Completions 兼容协议。')
    url = urlparse(str(value.get('endpoint', '')).strip())
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('端点不能携带账号、密码、查询参数或片段。')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('远程服务必须使用 HTTPS；HTTP 仅限本机端点。')
    suffix = '/responses' if protocol == 'responses' else '/chat/completions'
    path = url.path.rstrip('/')
    if not path.endswith(suffix):
        if path.endswith(('/responses', '/chat/completions')):
            raise ValueError('端点路径与所选协议不一致。')
        path = (path or '/v1') + suffix
    value['endpoint'] = url._replace(path=path).geturl()
    value['protocol'] = protocol
    value['model'] = str(value.get('model', '')).strip()
    if not value['model']:
        raise ValueError('请填写服务商提供的精确模型 ID。')
    return value

def key_service(value):
    url = urlparse(value['endpoint'])
    # Match native settings: credentials are scoped to scheme/host/port, not a
    # user-editable service name. Never carry a relay key to a different host.
    if url.scheme == 'https' and url.hostname == 'okai.la' and url.port in (None, 443):
        return 'trainer-okai-api-key'
    origin = f'{url.scheme}://{url.hostname}:{url.port or (443 if url.scheme == "https" else 80)}'
    return 'trainer-ai-' + hashlib.sha256(origin.encode()).hexdigest()

def relay_settings():
    path = DATA / 'ai-service.json'
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if not value.get('enabled'):
        return None
    return normalize_settings(value)

def request_body(provider, body):
    if provider == 'custom-chat':
        value = deepcopy(body)
        value.pop('thinking', None)
        for tool in value.get('tools', []):
            tool.get('function', {}).pop('strict', None)
        return value
    if provider not in ('okai', 'custom-responses'):
        return body
    value = {'model': body['model'], 'store': False, 'stream': False,
            'max_output_tokens': body.get('max_tokens', 8192), 'input': body['messages'],
            }
    if body.get('tools'):
        tool = body['tools'][0]['function']
        value['tools'] = [{'type': 'function', 'name': tool['name'], 'description': tool.get('description', ''), 'parameters': tool['parameters']}]
        value['tool_choice'] = {'type': 'function', 'name': tool['name']}
    return value

def response_body(provider, result):
    if provider not in ('okai', 'custom-responses'):
        return result
    if result.get('status') == 'incomplete':
        return {'choices': [{'finish_reason': 'length', 'message': {}}]}
    if result.get('status') not in (None, 'completed'):
        raise ValueError('AI 服务未完成请求，请检查服务配置或稍后重试。')
    calls = [{'function': {'name': item.get('name'), 'arguments': item['arguments']}} for item in result.get('output', []) if item.get('type') == 'function_call']
    if not calls:
        raise ValueError('AI 服务没有返回要求的结构化工具结果，请确认模型支持 Responses 函数调用。')
    return {'model': result.get('model'), 'choices': [{'finish_reason': 'stop', 'message': {'tool_calls': calls}}]}

def diagnose(settings, key):
    settings = normalize_settings(settings)
    if not key:
        return {'ok': False, 'message': '未找到此服务的密钥，请填写并保存。'}
    provider = 'custom-chat' if settings['protocol'] == 'chat-completions' else 'custom-responses'
    body = {'model': settings['model'], 'messages': [{'role': 'user', 'content': 'Connectivity test only. Call connection_test with ok=true.'}], 'max_tokens': 512,
            'tools': [{'type': 'function', 'function': {'name': 'connection_test', 'parameters': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}}}],
            'tool_choice': {'type': 'function', 'function': {'name': 'connection_test'}}, 'stream': False}
    started = time.monotonic()
    stage = '普通回复'
    session = str(uuid.uuid4())
    try:
        basic = {'model': settings['model'], 'messages': [{'role': 'user', 'content': 'Trainer coding tutor connection test: reply OK.'}], 'max_tokens': 512, 'stream': False}
        with relay_open(build_request(provider, settings['endpoint'], key, basic, session), timeout=25) as response:
            result = json.loads(response.read(1024 * 1024))
        if provider == 'custom-chat':
            content = result['choices'][0]['message'].get('content')
        else:
            content = ''.join(part.get('text', '') for item in result.get('output', []) for part in item.get('content', []) if part.get('type') == 'output_text')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('没有文本回复')
        stage = '结构化输出（普通回复已通过）'
        request = build_request(provider, settings['endpoint'], key, body, session)
        with relay_open(request, timeout=25) as response:
            result = response_body(provider, json.loads(response.read(1024 * 1024)))
        choice = result['choices'][0]
        call = choice['message']['tool_calls'][0]['function']
        if call['name'] != 'connection_test' or json.loads(call['arguments']).get('ok') is not True:
            raise ValueError('未通过工具调用检查')
        return {'ok': True, 'message': f'连接、鉴权、模型及结构化工具调用通过（{time.monotonic() - started:.1f} 秒）。', 'endpoint': settings['endpoint']}
    except HTTPError as error:
        return {'ok': False, 'stage': stage, 'message': stage + '失败：' + http_failure(error)}
    except (TimeoutError, socket.timeout):
        return {'ok': False, 'stage': stage, 'message': stage + '超过 25 秒；未自动重发。'}
    except URLError as error:
        reason = error.reason
        label = 'TLS 证书验证失败' if isinstance(reason, ssl.SSLError) else ('DNS 解析失败' if isinstance(reason, socket.gaierror) else '网络连接失败（代理、防火墙或服务不可达）')
        return {'ok': False, 'message': label + '；没有忽略证书验证。'}
    except (ValueError, KeyError, IndexError, TypeError):
        return {'ok': False, 'stage': stage, 'message': stage + '失败：服务有响应，但结果与协议不兼容。'}
