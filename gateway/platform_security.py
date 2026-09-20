"""Fail closed until native Windows handle/ACL validation is implemented."""
import os


def supports_secure_submission():
    return (os.name == 'posix' and hasattr(os, 'getuid') and
            all(hasattr(os, flag) for flag in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK')) and
            os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd)


def require_secure_submission():
    if not supports_secure_submission():
        raise ValueError('当前平台的安全文件读取与提交存储尚未适配，代码提交已禁用。')
