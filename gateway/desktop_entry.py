"""Frozen desktop backend entry. Session arrives through an owned stdin pipe.

No arbitrary executable/path configuration. It cannot run without its parent.
"""
import json
import os
import sys
import threading


def main():
    if sys.platform not in ('win32', 'darwin'):
        raise SystemExit('独立桌面后端仅支持 Windows 与 macOS。')
    try:
        options = json.loads(sys.stdin.buffer.readline(4096))
        token = options['session']
        if set(options) != {'session'} or not isinstance(token, str) or len(token) != 64 or not all(c in '0123456789abcdef' for c in token):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise SystemExit('无法建立桌面会话。')
    # Persistent native profile, independent from developer environment overrides.
    for name in ('TRAINER_DATA_DIR', 'TRAINER_CREDENTIALS_DIR', 'TRAINER_DESKTOP_ISOLATED'):
        os.environ.pop(name, None)
    for name in ('OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'TRAINER_OKAI_API_KEY'):
        os.environ.pop(name, None)
    if sys.platform == 'win32':
        os.environ['TRAINER_GATEWAY_PORT'] = '18787'
    else:
        os.environ.setdefault('TRAINER_GATEWAY_PORT', '8787')
    os.environ['TRAINER_GATEWAY_SESSION_TOKEN'] = token
    stopped = threading.Event()
    def watch_parent():
        sys.stdin.buffer.read()
        stopped.set()
    threading.Thread(target=watch_parent, daemon=True).start()
    from server import main as serve
    serve(stopped)


if __name__ == '__main__':
    main()
