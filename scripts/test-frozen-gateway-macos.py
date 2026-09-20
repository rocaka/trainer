"""Smoke-test the self-contained macOS Gateway and parent-pipe shutdown."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler

if sys.platform != 'darwin':
    raise SystemExit('Frozen macOS smoke test requires macOS.')
root = Path(__file__).resolve().parent.parent
executable = root / 'dist/mac-gateway/trainer-gateway/trainer-gateway'
assert executable.is_file(), 'frozen executable missing'
with tempfile.TemporaryDirectory(prefix='trainer-macos-smoke-') as temporary:
    environment = dict(os.environ, HOME=temporary, TRAINER_GATEWAY_PORT='18788')
    token = secrets.token_hex(32)
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    try:
        process.stdin.write(json.dumps({'session': token}).encode() + b'\n')
        process.stdin.flush()
        opener = build_opener(ProxyHandler({}))
        def get(path):
            with opener.open(Request('http://127.0.0.1:18788' + path,
                                     headers={'X-Trainer-Session': token}), timeout=2) as response:
                return json.load(response)
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError('frozen backend exited before readiness')
            try:
                health = get('/health')
                break
            except OSError:
                time.sleep(.2)
        else:
            raise AssertionError('frozen backend readiness timeout')
        assert health['ok']
        assert isinstance(get('/v1/skills')['skills'], list)
        process.stdin.close()
        process.wait(timeout=15)
        assert process.returncode == 0, 'backend shutdown failed'
        print('PASS: frozen macOS Gateway, authenticated API and parent-pipe shutdown')
    finally:
        if process.poll() is None:
            if not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
