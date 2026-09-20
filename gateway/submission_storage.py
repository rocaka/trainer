"""Provision a private local submission database; no production path selected yet.

Caller supplies a pre-created private directory outside portable backups.
Does not chmod existing files, migrate data, encrypt SQLite, or secure-delete it.
The owner must prevent same-user directory replacement during subsequent SQLite
operations; this preflight is not a sandbox against other same-user processes.
"""
import os
from pathlib import Path
import stat

from submission_snapshot import open_root


def private_database(directory):
    from platform_security import require_secure_submission
    require_secure_submission()
    root = Path(directory)
    if not root.is_absolute() or '..' in root.parts or root == Path('/'):
        raise ValueError('需要明确的私有存储目录')
    descriptor = open_root(root)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('存储目录必须属于当前用户且权限为 0700')
        name = 'submissions.sqlite3'
        try:
            file_fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              0o600, dir_fd=descriptor)
        except FileExistsError:
            file_fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        try:
            check_file(os.fstat(file_fd))
        finally:
            os.close(file_fd)
        # SQLite may reuse journal/WAL companions; reject unsafe existing ones.
        for suffix in ('-journal', '-wal', '-shm'):
            try:
                companion = os.stat(name + suffix, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            check_file(companion)
    finally:
        os.close(descriptor)
    return root / name


def check_file(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise ValueError('数据库或辅助文件类型、归属或权限不安全')
