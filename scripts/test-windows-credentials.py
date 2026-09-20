"""Windows-only integration test. Creates/deletes one uniquely named fake key.

Never reads or changes real Trainer service credentials.
"""
import hashlib
from pathlib import Path
import secrets
import sys

if sys.platform != 'win32':
    raise SystemExit('此验收必须在 Windows 执行，未运行系统凭据测试。')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'gateway'))
from system_credentials import read_windows, write_windows, delete_windows

service = 'trainer-ai-' + hashlib.sha256(secrets.token_bytes(32)).hexdigest()
value = 'Trainer integration fixture 非真实密钥 ' + secrets.token_hex(8)
try:
    assert read_windows(service, 'Trainer') == ''
    write_windows(service, 'Trainer', value)
    assert read_windows(service, 'Trainer') == value
    write_windows(service, 'Trainer', value + '-updated')
    assert read_windows(service, 'Trainer') == value + '-updated'
finally:
    delete_windows(service, 'Trainer')
assert read_windows(service, 'Trainer') == ''
print('PASS: Windows credential missing/write/read/update/delete; fixture removed')
