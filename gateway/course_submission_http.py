"""Native-only unified submission route. Runtime absent => explicit 503.

Runtime supplies service, dispatcher and current evaluator_key() from local config.
The native UI must disclose provider/material scope before sending consent=true.
"""
import hmac
import json
import os
import re

from learning_loop import fields, text
from learning_loop_service import unique_object


def dispatch(handler):
    if not handler.path.startswith('/v1/course-submissions'):
        return False
    def respond(status, value):
        handler.send_json(status, value)
        return True
    if handler.headers.get('Origin') is not None:
        return respond(403, {'error': '仅限原生客户端'})
    values = handler.headers.get_all('X-Trainer-Session', [])
    expected = os.environ.get('TRAINER_GATEWAY_SESSION_TOKEN', '')
    if len(values) != 1 or not expected or not hmac.compare_digest(values[0].encode(), expected.encode()):
        return respond(401, {'error': '需要当前 Trainer 会话'})
    runtime = getattr(handler.server, 'course_submission_runtime', None)
    if runtime is None:
        return respond(503, {'error': '自动提交服务尚未启用'})
    try:
        if handler.command == 'GET' and handler.path == '/v1/course-submissions/config':
            return respond(200, runtime.disclosure())
        if handler.command == 'GET' and handler.path == '/v1/course-submissions/storage':
            return respond(200, runtime.service.material_storage('local'))
        if handler.command == 'DELETE' and handler.path == '/v1/course-submissions/storage':
            lengths = handler.headers.get_all('Content-Length', [])
            if handler.headers.get('Transfer-Encoding') is not None or len(lengths) != 1:
                raise ValueError('请求长度无效')
            length = int(lengths[0])
            if not 0 < length <= 1024:
                return respond(413, {'error': '请求大小无效'})
            payload = json.loads(handler.rfile.read(length), object_pairs_hook=unique_object)
            fields(payload, 'confirm preserveFeedback')
            if payload['confirm'] is not True or payload['preserveFeedback'] is not True:
                return respond(403, {'error': '需要确认清理材料并保留历史反馈'})
            return respond(200, runtime.service.delete_archived_materials('local'))
        match = re.fullmatch(r'/v1/course-submissions/([a-f0-9]{32})', handler.path)
        if handler.command == 'GET' and match:
            return respond(200, runtime.service.status('local', match[1]))
        if handler.command != 'POST' or handler.path != '/v1/course-submissions':
            return respond(404, {'error': '接口不存在'})
        lengths = handler.headers.get_all('Content-Length', [])
        if handler.headers.get('Transfer-Encoding') is not None or len(lengths) != 1:
            raise ValueError('请求长度无效')
        length = int(lengths[0])
        if not 0 < length <= 65536:
            return respond(413, {'error': '请求大小无效'})
        payload = json.loads(handler.rfile.read(length), object_pairs_hook=unique_object)
        fields(payload, 'planId lessonId bindingId requestKey evaluatorKey answer consent')
        for key in ('planId', 'lessonId', 'bindingId', 'requestKey', 'evaluatorKey'):
            text(payload[key], 200)
        if type(payload['answer']) is not str or len(payload['answer']) > 16000:
            raise ValueError('说明无效')
        if payload['consent'] is not True:
            return respond(403, {'error': '需要明确确认将本次材料发送至评判服务'})
        if payload['evaluatorKey'] != runtime.evaluator_key():
            return respond(409, {'error': '评判配置已变化，请刷新后重新确认'})
        job = runtime.service.submit(learner='local', plan_id=payload['planId'], lesson_id=payload['lessonId'],
            binding_id=payload['bindingId'], request_key=payload['requestKey'], evaluator_key=payload['evaluatorKey'], answer=payload['answer'])
        return respond(202, runtime.dispatcher.dispatch('local', job['id']))
    except (ValueError, TypeError, KeyError) as error:
        from submission_snapshot import SnapshotBlocked
        if isinstance(error, SnapshotBlocked):
            reasons = {
                'authorization_required': '请在连接管理中授权本课任务文件后重试。',
                'unsaved_files': '本课文件还有未保存的修改，请在 VS Code 保存后再次提交。',
                'buffer_status_unavailable': '尚未收到最新保存状态，请保持 VS Code 连接后重试。',
                'missing_file_contract': '本课缺少任务文件清单，请先完善课程任务。',
                'execution_evidence_unavailable': '此任务要求运行验证，当前静态评审无法完成这项验收。',
            }
            for code, message in reasons.items():
                if code in str(error):
                    return respond(400, {'error': message})
        return respond(400, {'error': '任务、关联、授权或保存状态未满足提交要求'})
    except Exception:
        return respond(503, {'error': '提交服务暂不可用，请保留本次请求标识重试'})
