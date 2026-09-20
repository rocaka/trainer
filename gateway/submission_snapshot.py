"""Local immutable multi-file snapshot primitive; NOT a production read endpoint.

The caller must separately validate current source-read consent, workspace identity,
trust and exercise scope. Metadata pairing alone is not consent. No discovery,
network, persistence, command execution or external-send authorization occurs here.
Only explicit relative paths are read. Secret detection is deliberately best-effort.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat


class SnapshotBlocked(ValueError):
    pass


EXCLUDED_DIRS = {'.git', '.ssh', '.aws', '.azure', '.config', 'node_modules',
                 '.venv', 'venv', '__pycache__', '.build', 'build', 'dist', 'vendor'}
SECRET_NAMES = {'credentials', 'credentials.json', 'auth.json', 'id_rsa', 'id_ed25519',
                '.npmrc', '.pypirc', '.netrc', 'secrets.json', 'secrets.yaml', 'secrets.yml'}
SECRET_PATTERN = re.compile(
    r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|'
    r'\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|'
    r'\bAKIA[A-Z0-9]{16}\b|'
    r'(?i:(?:api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*["\x27][^"\x27\s]{8,}["\x27])'
)


def checked_path(value):
    if not isinstance(value, str) or not value or len(value) > 1024 or '\\' in value or '\x00' in value:
        raise SnapshotBlocked('文件路径无效')
    parts = value.split('/')
    if any(p in ('', '.', '..') for p in parts) or Path(value).is_absolute():
        raise SnapshotBlocked('只允许工作区内的相对文件路径')
    lower = [p.lower() for p in parts]
    name = lower[-1]
    if (any(p in EXCLUDED_DIRS for p in lower) or name in SECRET_NAMES or
            name == '.env' or name.startswith('.env.') or
            name.endswith(('.pem', '.key', '.p12', '.pfx', '.keystore'))):
        raise SnapshotBlocked('清单包含凭据或排除目录，请缩小提交范围')
    return parts


def read_file(root_fd, parts, limit):
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise SnapshotBlocked('只支持普通文件，不支持符号链接、硬链接或特殊文件')
            if before.st_size > limit:
                raise SnapshotBlocked('单个文件超过限制，请缩小提交范围')
            chunks, length = [], 0
            while True:
                block = os.read(descriptor, min(65536, limit + 1 - length))
                if not block: break
                chunks.append(block)
                length += len(block)
                if length > limit: raise SnapshotBlocked('文件读取时超过限制')
            after = os.fstat(descriptor)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise SnapshotBlocked('文件正在改变，请保存后重新提交')
            return b''.join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(current)


def open_root(root):
    """Anchor every directory hop; reject symlink swaps even above the project."""
    from platform_security import require_secure_submission
    require_secure_submission()
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def collect_snapshot(root, relative_paths, *, max_files=100, max_file_bytes=256 * 1024,
                     max_total_bytes=2 * 1024 * 1024):
    """Return frozen UTF-8 text and hashes, or block the entire batch (never truncate).

    Disk-only: callers must resolve unsaved editor buffers before using this result.
    Limits may only be lowered. Collection is not an atomic filesystem snapshot.
    """
    if not isinstance(relative_paths, (list, tuple)) or not relative_paths:
        raise SnapshotBlocked('需要明确的文件清单')
    if any(not isinstance(n, int) or isinstance(n, bool) or n <= 0 for n in (max_files, max_file_bytes, max_total_bytes)):
        raise SnapshotBlocked('采集限制无效')
    max_files = min(max_files, 100)
    max_file_bytes = min(max_file_bytes, 256 * 1024)
    max_total_bytes = min(max_total_bytes, 2 * 1024 * 1024)
    if len(relative_paths) > 1000: raise SnapshotBlocked('文件清单过长')
    paths = {value: checked_path(value) for value in relative_paths}
    if len(paths) > max_files: raise SnapshotBlocked('文件数量超过限制，请缩小提交范围')
    root = Path(root)
    if not root.is_absolute() or '..' in root.parts or root == Path('/') or root.resolve() == Path.home().resolve():
        raise SnapshotBlocked('需要具体的绝对项目目录')
    files, total = [], 0
    try:
        root_fd = open_root(root)
        try:
            for name, parts in sorted(paths.items()):
                raw = read_file(root_fd, parts, max_file_bytes)
                total += len(raw)
                if total > max_total_bytes: raise SnapshotBlocked('提交总大小超过限制，请缩小范围')
                if b'\x00' in raw: raise SnapshotBlocked('清单包含二进制文件')
                try: content = raw.decode('utf-8')
                except UnicodeDecodeError: raise SnapshotBlocked('只支持 UTF-8 文本文件') from None
                if SECRET_PATTERN.search(content): raise SnapshotBlocked('检测到疑似密钥，已阻断整次采集；请移除敏感内容')
                files.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(),
                              'bytes': len(raw), 'content': content, 'source': 'disk'})
        finally:
            os.close(root_fd)
    except OSError:
        raise SnapshotBlocked('文件不可读、已移动或路径包含符号链接，请检查提交范围') from None
    manifest = [{k: f[k] for k in ('path', 'sha256', 'bytes')} for f in files]
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'files': files, 'totalBytes': total, 'digest': digest, 'version': 1}
