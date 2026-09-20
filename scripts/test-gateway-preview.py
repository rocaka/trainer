"""Integration smoke test: real isolated process, storage and parent EOF cleanup."""
import json
from pathlib import Path
import subprocess
import sys
import time
import secrets
from urllib.request import Request
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler

root = Path(__file__).resolve().parent.parent
child = subprocess.Popen([sys.executable, str(root / 'scripts/gateway-preview.py'), '--managed'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
folder = None
token = secrets.token_urlsafe(32)
child.stdin.write(json.dumps({'session': token}).encode() + b'\n')
child.stdin.flush()
try:
    opener = build_opener(ProxyHandler({}))
    for attempt in range(60):
        if child.poll() is not None:
            raise AssertionError('preview exited before readiness')
        try:
            with opener.open('http://127.0.0.1:18787/v1/me', timeout=1) as response:
                data = json.load(response)
            break
        except OSError:
            time.sleep(.1)
    else:
        raise AssertionError('preview readiness timeout')
    assert data['evidenceCount'] == 0
    runtime = 'http://127.0.0.1:18787/v1/desktop/runtime'
    try:
        opener.open(runtime, timeout=1)
        raise AssertionError('unauthenticated runtime accepted')
    except HTTPError as error:
        assert error.code == 401
    with opener.open(Request(runtime, headers={'X-Trainer-Session': token}), timeout=1) as response:
        status = json.load(response)
    assert status['owned'] and status['isolated'] and not status['settingsWritable']
    folder = Path(data['storagePath']).parent.parent
    # storagePath is the actual database path; find the temporary preview root.
    database = Path(data['storagePath'])
    folder = next(p for p in database.parents if p.name.startswith('trainer-preview-'))
    with opener.open('http://127.0.0.1:18787/health', timeout=1) as response:
        health = json.load(response)
    assert health['configured'] is False, 'preview must not read host API keys'
    if health['secureSubmissionSupported']:
        assert health['submissionReady'] is True
        assert (folder / 'credentials/submissions/submissions.sqlite3').is_file(), 'submission storage not initialized'
    else:
        assert health['submissionReady'] is False
        assert not (folder / 'credentials/pairings.sqlite3').exists(), 'unsupported platform must not create unprotected pairing tokens'
    child.stdin.close()
    child.wait(timeout=12)
    output = child.stdout.read().decode()
    assert 'automatic submission unavailable' not in output
    assert not folder.exists(), 'temporary folder was not reclaimed'
    print('PASS: isolated dashboard, private submission DB, parent EOF cleanup')
finally:
    if child.poll() is None:
        if not child.stdin.closed:
            child.stdin.close()
        child.wait(timeout=12)
