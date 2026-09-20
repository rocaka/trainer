"""Validate packaging inputs without invoking PyInstaller or shipping user data."""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parent.parent
class Analysis:
    def __init__(self, scripts, **options):
        self.scripts, self.pure, self.binaries = scripts, [], []
        self.datas = options['datas']
        assert 'platform_paths' in options['hiddenimports']
        for source, destination in self.datas:
            path = Path(source)
            assert path.is_file()
            assert not any(part in path.parts for part in ('generated', 'learning-plans', '.trainer-credentials'))
        assert any(Path(source).name == 'SKILL_SPEC.md' for source, _ in self.datas)
        print(f'PASS: {len(self.datas)} tracked teaching resources; no generated courses or user databases')

runpy.run_path(str(root / 'scripts/gateway-bundle.spec'), init_globals={
    'SPECPATH': str(root / 'scripts'), 'Analysis': Analysis,
    'PYZ': lambda *a, **k: None, 'EXE': lambda *a, **k: None,
    'COLLECT': lambda *a, **k: None,
})
