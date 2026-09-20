"""Platform paths without filesystem side effects (also usable by packaging tests)."""
import os
import sys
from pathlib import Path


def data_directory(platform=None, environ=None, home=None):
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if environ.get('TRAINER_DATA_DIR'):
        return Path(environ['TRAINER_DATA_DIR'])
    if platform == 'win32':
        return Path(environ.get('LOCALAPPDATA') or home / 'AppData/Local') / 'Trainer'
    if platform == 'darwin':
        return home / 'Library/Application Support/Trainer'
    return Path(environ.get('XDG_DATA_HOME') or home / '.local/share') / 'Trainer'


def credentials_directory():
    # Keep the existing macOS location; Windows must not rely on POSIX chmod
    # as an access-control boundary. Its ACL/credential-store adapter is pending.
    return Path(os.environ.get('TRAINER_CREDENTIALS_DIR') or Path.home() / '.trainer-credentials')


def assets_directory():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent
