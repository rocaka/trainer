"""Thin v2 HTTP boundary. No migration or business logic in request parsing."""
import json
import socket
from learning_loop_service import MAX_BODY_BYTES, error


def dispatch(handler):
    if not handler.path.startswith('/v2/'):
        return False

    def respond(status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        handler.send_response(status)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(data)))
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('X-Content-Type-Options', 'nosniff')
        handler.send_header('Connection', 'close')
        handler.end_headers()
        handler.close_connection = True
        handler.wfile.write(data)
        return True

    pairing = handler.path == '/v2/pairings' or handler.path.startswith('/v2/pairings/')
    service = getattr(handler.server, 'pairing_service' if pairing else 'loop_service', None)
    if service is None:
        return respond(*error(503, 'feature_not_enabled', '学习闭环尚未启用；旧课程功能不受影响'))
    tokens = handler.headers.get_all('X-Trainer-Session', [])
    native_required = not pairing or service.requires_native(handler.command, handler.path)
    if len(tokens) > 1 or (native_required and (len(tokens) != 1 or not service.authorized(tokens[0]))):
        return respond(*error(401, 'unauthorized', '需要有效的 Trainer 会话'))
    # Native clients do not send Origin. Browser origins must not use this API.
    if handler.headers.get('Origin') is not None:
        return respond(*error(403, 'origin_not_allowed', '此接口仅供已配对的本地客户端'))
    if handler.command not in ('GET', 'POST'):
        return respond(*error(405, 'method_not_allowed', '请求方法不支持'))
    lengths = handler.headers.get_all('Content-Length', [])
    if handler.headers.get('Transfer-Encoding') or len(lengths) > 1:
        return respond(*error(400, 'invalid_request', '不支持此请求编码'))
    try:
        raw_length = lengths[0] if lengths else '0'
        if not raw_length.isascii() or not raw_length.isdigit(): raise ValueError()
        length = int(raw_length)
    except ValueError:
        return respond(*error(400, 'invalid_request', '请求长度无效'))
    if length > MAX_BODY_BYTES:
        return respond(*error(413, 'payload_too_large', '请求超过 64 KiB'))
    if handler.command == 'GET' and length:
        return respond(*error(400, 'invalid_request', '读取请求不能包含正文'))
    if length and handler.headers.get_content_type() != 'application/json':
        return respond(*error(415, 'unsupported_media_type', '请发送 application/json'))
    previous_timeout = handler.connection.gettimeout()
    try:
        handler.connection.settimeout(5)
        body = handler.rfile.read(length)
        if len(body) != length: return respond(*error(400, 'invalid_request', '请求正文不完整'))
    except (TimeoutError, socket.timeout):
        return respond(*error(408, 'request_timeout', '读取请求超时'))
    finally:
        handler.connection.settimeout(previous_timeout)
    return respond(*service.handle(handler.command, handler.path, tokens[0] if tokens else '', body))
