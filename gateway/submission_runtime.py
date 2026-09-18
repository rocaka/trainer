"""Production component assembly; initialization never reads projects or runs AI."""
from pathlib import Path
from urllib.parse import urlsplit

from course_submission import CourseSubmission
from submission_storage import private_database
from submission_consent import SubmissionConsent
from submission_dispatcher import SubmissionDispatcher
from submission_provider import evaluator_key
import submission_queue as queue


class SubmissionRuntime:
    def __init__(self, data, credentials, pairing_service, settings, evaluate):
        root = Path(credentials) / 'submissions'
        if root.is_symlink():
            raise ValueError('提交存储不能是符号链接')
        root.mkdir(mode=0o700, exist_ok=True)
        database = private_database(root)
        queue.initialize(database)
        self.settings = settings
        self.service = CourseSubmission.from_pairing(data, database, pairing_service)
        self.service.sync_completions()
        pairing_service.submission_status = self.service.binding_status
        self.consent = SubmissionConsent(database)
        self.dispatcher = SubmissionDispatcher(self.service, self.consent, evaluate)

    def evaluator_key(self):
        provider, model, endpoint, secret = self.settings()
        if not secret or provider not in ('deepseek', 'okai', 'custom-chat', 'custom-responses'):
            raise ValueError('未配置支持的评判服务')
        return evaluator_key(provider, model, endpoint)

    def disclosure(self):
        provider, model, endpoint, secret = self.settings()
        if not secret or provider not in ('deepseek', 'okai', 'custom-chat', 'custom-responses'):
            raise ValueError('未配置支持的评判服务')
        # Never expose credentials, URL userinfo, query strings or API keys.
        host = urlsplit(endpoint).hostname
        if not host:
            raise ValueError('评判服务地址无效')
        return {'provider': provider, 'model': model, 'host': host,
                'evaluatorKey': evaluator_key(provider, model, endpoint),
                'method': 'static_review', 'executesCode': False,
                'notice': '点击提交并评判后，将发送本课要求且已授权的代码材料；可能产生模型费用。不会运行代码。'}

    def close(self):
        self.dispatcher.close()
