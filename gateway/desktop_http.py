"""Strict native desktop routes. Ownership handshake precedes all UI writes."""
import hmac
import json
import os
import sys
from desktop_settings import public_settings, save_settings
from system_credentials import read_secret, write_windows
from learning_loop_service import unique_object


def dispatch(handler, data):
    if not handler.path.startswith('/v1/desktop/'):
        return False
    def reply(status, body):
        handler.send_json(status, body)
        return True
    if handler.headers.get('Origin') is not None:
        return reply(403, {'error': '仅允许桌面原生会话'})
    tokens = handler.headers.get_all('X-Trainer-Session', [])
    expected = os.environ.get('TRAINER_GATEWAY_SESSION_TOKEN', '')
    if len(tokens) != 1 or not expected or not hmac.compare_digest(tokens[0].encode(), expected.encode()):
        return reply(401, {'error': '桌面会话不匹配，请重新启动客户端'})
    isolated = os.environ.get('TRAINER_DESKTOP_ISOLATED') == '1'
    writable = sys.platform == 'win32' and not isolated
    try:
        if handler.command == 'GET' and handler.path == '/v1/desktop/runtime':
            return reply(200, {'owned': True, 'isolated': isolated,
                               'settingsWritable': writable, 'platform': sys.platform})
        if handler.command == 'GET' and handler.path == '/v1/desktop/dashboard':
            from learning_store import dashboard
            return reply(200, dashboard())
        if handler.command == 'GET' and handler.path == '/v1/desktop/health':
            from server import provider_settings
            from platform_security import supports_secure_submission
            provider, model, _, key = provider_settings()
            return reply(200, {'ok': True, 'provider': provider, 'model': model, 'configured': bool(key),
                               'secureSubmissionSupported': supports_secure_submission(),
                               'submissionReady': getattr(handler.server, 'course_submission_runtime', None) is not None})
        if handler.command == 'GET' and handler.path == '/v1/desktop/courses':
            from desktop_courses import list_courses
            return reply(200, list_courses(data))
        if handler.command == 'GET' and handler.path.startswith('/v1/desktop/courses/'):
            from desktop_courses import read_course
            return reply(200, read_course(data, handler.path.removeprefix('/v1/desktop/courses/')))
        if handler.command == 'GET' and handler.path == '/v1/desktop/settings':
            return reply(200, public_settings(data, (lambda *args: '') if isolated else read_secret))
        if handler.command == 'POST' and handler.path == '/v1/desktop/settings':
            if not writable:
                return reply(403, {'error': '当前运行模式不允许修改系统凭据；隔离预览不会保存真实密钥'})
            lengths = handler.headers.get_all('Content-Length', [])
            if handler.headers.get('Transfer-Encoding') is not None or len(lengths) != 1:
                return reply(400, {'error': '请求长度无效'})
            length = int(lengths[0])
            if not 0 < length <= 16384:
                return reply(413, {'error': '设置请求过大'})
            payload = json.loads(handler.rfile.read(length), object_pairs_hook=unique_object)
            from jobs import list_jobs
            if any(job.get('status') in ('queued', 'running') or job.get('inFlight') for job in list_jobs(archived=False)):
                return reply(409, {'error': '请等待生成任务结束后再切换服务'})
            return reply(200, save_settings(data, payload, read_secret, write_windows))
        return reply(404, {'error': '桌面接口不存在'})
    except (ValueError, TypeError, KeyError, RecursionError):
        return reply(400, {'error': '配置未保存，请检查协议、服务地址、模型、密钥与授权'})
    except OSError:
        return reply(503, {'error': '系统存储暂不可用，配置未切换'})
