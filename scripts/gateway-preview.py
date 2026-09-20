"""Run an isolated Gateway for desktop development. Never uses production data.

Usage: python3 scripts/gateway-preview.py
Stop with Ctrl+C. No credentials or learning records are copied from the host.
"""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import json


def main():
    root = Path(__file__).resolve().parent.parent
    token = secrets.token_urlsafe(32)
    if '--managed' in sys.argv:
        try:
            options = json.loads(sys.stdin.buffer.readline(4096))
            token = options['session']
            if not isinstance(token, str) or not 32 <= len(token) <= 256 or not token.isascii():
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise SystemExit('无法建立桌面会话，未启动后端。')
    # Preview uses its own port and temporary data. Refuse a collision rather
    # than connecting to, or terminating, another application's Gateway.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 18787))
        except OSError:
            raise SystemExit('预览端口 18787 已占用，未启动或停止任何服务。')
    with tempfile.TemporaryDirectory(prefix='trainer-preview-') as folder:
        # macOS /var is a system symlink; use the physical temporary directory
        # so submission storage can retain its strict no-symlink traversal.
        folder = Path(folder).resolve(strict=True)
        env = os.environ.copy()
        env.update(TRAINER_DATA_DIR=str(Path(folder) / 'data'),
                   TRAINER_CREDENTIALS_DIR=str(Path(folder) / 'credentials'),
                   TRAINER_GATEWAY_PORT='18787',
                   TRAINER_GATEWAY_SESSION_TOKEN=token,
                   TRAINER_DESKTOP_ISOLATED='1')
        for key in ('OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'TRAINER_OKAI_API_KEY'):
            env.pop(key, None)
        # Skip development-tree migration: preview must not copy user courses.
        data = Path(env['TRAINER_DATA_DIR'])
        data.mkdir()
        for marker in ('.migration-v1-complete', '.evidence-migration-v2-complete'):
            (data / marker).touch()
        print('隔离 Gateway：http://127.0.0.1:18787；退出后删除临时预览数据。', flush=True)
        # Isolated diagnostics contain no user data. Emit a stack if startup
        # stalls, rather than leaving CI with only a readiness timeout.
        bootstrap = ('import faulthandler, runpy; '
                     'faulthandler.dump_traceback_later(15, repeat=True); '
                     'runpy.run_path("server.py", run_name="__main__")')
        child = subprocess.Popen([sys.executable, '-u', '-c', bootstrap], cwd=root / 'gateway', env=env)
        if '--managed' in sys.argv:
            def parent_closed():
                # Parent owns this pipe. EOF also occurs if the desktop crashes.
                sys.stdin.buffer.read()
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        child.kill()
            threading.Thread(target=parent_closed, daemon=True).start()
        try:
            return child.wait()
        except KeyboardInterrupt:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            return 0


if __name__ == '__main__':
    sys.exit(main())
