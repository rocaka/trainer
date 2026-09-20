"""Windows frozen executable smoke test with disposable application data."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler

if sys.platform != 'win32':
    raise SystemExit('Frozen Windows smoke test requires Windows.')
root = Path(__file__).resolve().parent.parent
executable = root / 'dist/windows-gateway/trainer-gateway/trainer-gateway.exe'
assert executable.is_file(), 'frozen executable missing'
with tempfile.TemporaryDirectory(prefix='trainer-frozen-smoke-') as temporary:
    environment = dict(os.environ, LOCALAPPDATA=temporary)
    token = secrets.token_hex(32)
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    try:
        process.stdin.write(json.dumps({'session': token}).encode() + b'\n')
        process.stdin.flush()
        opener = build_opener(ProxyHandler({}))
        def get(path):
            with opener.open(Request('http://127.0.0.1:18787' + path,
                                     headers={'X-Trainer-Session': token}), timeout=2) as response:
                return json.load(response)
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError('frozen backend exited before readiness')
            try:
                runtime = get('/v1/desktop/runtime')
                break
            except OSError:
                time.sleep(.2)
        else:
            raise AssertionError('frozen backend readiness timeout')
        assert runtime['owned'] and runtime['settingsWritable'] and not runtime['isolated']
        health = get('/v1/desktop/health')
        assert health['ok'] and not health['submissionReady'] and not health['secureSubmissionSupported']
        assert get('/v1/desktop/dashboard')['evidenceCount'] == 0
        assert isinstance(get('/v1/desktop/courses')['courses'], list)
        process.stdin.close()
        process.wait(timeout=15)
        assert process.returncode == 0, 'backend shutdown failed'
        print('PASS: frozen Windows backend, authenticated API, empty profile, parent-pipe shutdown')
    finally:
        if process.poll() is None:
            if not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
