"""Truthful configuration status for optional cloud and GitHub services."""
import os
import re
from urllib.parse import urlparse


def _https_endpoint(value):
    try:
        parsed = urlparse(value)
        return value.rstrip('/') if parsed.scheme == 'https' and parsed.netloc and not parsed.username else ''
    except (TypeError, ValueError):
        return ''


def integration_status(environ=None):
    environ = os.environ if environ is None else environ
    cloud = _https_endpoint(environ.get('TRAINER_CLOUD_ENDPOINT', ''))
    client = environ.get('TRAINER_GITHUB_CLIENT_ID', '').strip()
    # Trainer uses GitHub's Device Flow: it shows a short code in the app and
    # GitHub completes authorization in the user's browser.  This flow has no
    # redirect URI, so a valid Client ID is the only build-time requirement.
    github_ready = bool(re.fullmatch(r'[A-Za-z0-9_-]{8,128}', client))
    return {
        'cloud': {
            'state': 'sign-in-required' if cloud else 'not-configured',
            'configured': bool(cloud), 'endpoint': urlparse(cloud).netloc if cloud else None,
            'mode': 'local-first',
            'message': ('云服务已配置，登录后才会同步。' if cloud else
                        '尚未配置云服务地址；学习数据继续只保存在本机。')},
        'github': {
            'state': 'authorization-required' if github_ready else 'not-configured',
            'configured': github_ready,
            'scopes': ['read:user'],
            'optionalScopes': ['repo'],
            'collects': ['提交时间', '仓库语言统计', '提交数量'],
            'excludes': ['源码正文', '密钥', '私有仓库文件内容'],
            'message': ('GitHub OAuth 已配置，仍需用户主动授权。' if github_ready else
                        '尚缺 GitHub OAuth Client ID，不会打开授权或读取 GitHub。')}
    }
