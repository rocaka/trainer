"""Trainer-only credential access. No plaintext fallback and no secret logging.

Windows generic credentials use UTF-8 blobs, persist for the current user on
this machine, and are never included in learning-data synchronization.
"""
import ctypes
import re
import os
import subprocess
import sys


def validate(service, account):
    allowed = service in ('trainer-okai-api-key', 'trainer-deepseek-api-key', 'trainer-openai-api-key')
    allowed = allowed or bool(re.fullmatch(r'trainer-ai-[a-f0-9]{64}', service))
    if not ((allowed and account == 'Trainer') or (service == 'com.trainer.github' and account == 'oauth')):
        raise ValueError('不支持的 Trainer 凭据标识')
    return f'Trainer/{service}/{account}'


class FileTime(ctypes.Structure):
    _fields_ = [('low', ctypes.c_uint32), ('high', ctypes.c_uint32)]


class Credential(ctypes.Structure):
    _fields_ = [('Flags', ctypes.c_uint32), ('Type', ctypes.c_uint32),
                ('TargetName', ctypes.c_wchar_p), ('Comment', ctypes.c_wchar_p),
                ('LastWritten', FileTime), ('CredentialBlobSize', ctypes.c_uint32),
                ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
                ('Persist', ctypes.c_uint32), ('AttributeCount', ctypes.c_uint32),
                ('Attributes', ctypes.c_void_p), ('TargetAlias', ctypes.c_wchar_p),
                ('UserName', ctypes.c_wchar_p)]


def windows_api():
    if sys.platform != 'win32':
        raise ValueError('Windows 凭据接口仅能在 Windows 使用')
    api = ctypes.WinDLL('advapi32.dll', use_last_error=True)
    api.CredReadW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredReadW.restype = ctypes.c_int
    api.CredWriteW.argtypes = [ctypes.POINTER(Credential), ctypes.c_uint32]
    api.CredWriteW.restype = ctypes.c_int
    api.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    api.CredDeleteW.restype = ctypes.c_int
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def read_windows(service, account):
    target = validate(service, account)
    api = windows_api()
    pointer = ctypes.POINTER(Credential)()
    if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == 1168:  # ERROR_NOT_FOUND
            return ''
        raise ValueError('Windows 系统凭据暂不可读取')
    try:
        record = pointer.contents
        if record.Type != 1 or record.UserName != account or record.CredentialBlobSize > 2560:
            raise ValueError('系统凭据格式不兼容')
        if record.CredentialBlobSize == 0:
            return ''
        if not record.CredentialBlob:
            raise ValueError('系统凭据内容不可读取')
        try:
            return ctypes.string_at(record.CredentialBlob, record.CredentialBlobSize).decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError('系统凭据编码不兼容，请重新配置') from None
    finally:
        api.CredFree(pointer)


def write_windows(service, account, secret):
    target = validate(service, account)
    if not isinstance(secret, str) or not secret or '\x00' in secret:
        raise ValueError('凭据不能为空或包含空字符')
    encoded = secret.encode('utf-8')
    if len(encoded) > 2560:
        raise ValueError('凭据超过系统存储限制')
    api = windows_api()
    blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    record = Credential(Type=1, TargetName=target, CredentialBlobSize=len(encoded),
                        CredentialBlob=blob, Persist=2, UserName=account)
    try:
        if not api.CredWriteW(ctypes.byref(record), 0):
            raise ValueError('无法保存到 Windows 系统凭据，未写入普通文件')
    finally:
        ctypes.memset(blob, 0, len(encoded))


def delete_windows(service, account):
    target = validate(service, account)
    api = windows_api()
    if not api.CredDeleteW(target, 1, 0) and ctypes.get_last_error() != 1168:
        raise ValueError('无法移除 Windows 系统凭据')


def read_secret(service, account):
    validate(service, account)
    if os.environ.get('TRAINER_DESKTOP_ISOLATED') == '1':
        return ''
    if sys.platform == 'win32':
        return read_windows(service, account)
    if sys.platform != 'darwin':
        return ''  # No fallback to an unencrypted file on other platforms.
    try:
        result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-a', account,
                                 '-s', service, '-w'], capture_output=True, check=True,
                                text=True, timeout=10)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ''
