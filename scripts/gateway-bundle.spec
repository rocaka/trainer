"""Build on the target OS. Only tracked public teaching assets are included."""
from pathlib import Path
import subprocess

root = Path(SPECPATH).parent
tracked = subprocess.check_output(['git', 'ls-files', '-z', 'skills/core', 'skills/verified', 'docs'], cwd=root).decode().split('\0')
assets = []
for relative in filter(None, tracked):
    path = root / relative
    if path.is_symlink():
        raise ValueError('Bundled teaching resources must not be symlinks')
    if path.suffix in ('.md', '.yaml', '.yml', '.json'):
        assets.append((str(path), str(Path(relative).parent)))

# Local lazy imports must remain available in the frozen application.
modules = [p.stem for p in (root / 'gateway').glob('*.py') if p.stem != 'desktop_entry']
a = Analysis([str(root / 'gateway/desktop_entry.py')], pathex=[str(root / 'gateway')],
             binaries=[], datas=assets, hiddenimports=modules,
             hookspath=[], runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='trainer-gateway',
          debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='trainer-gateway')
