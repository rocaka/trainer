import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import repository
import version_store as versions

class VersionRecoveryTests(unittest.TestCase):
    def test_trash_hidden_restore_and_active(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            skills = root / 'skills'
            with patch.object(repository, 'SKILLS_ROOT', skills), patch.object(versions, 'SKILLS_ROOT', skills), patch.object(versions, 'ROOT', root), patch.object(versions, 'REGISTRY', skills / 'versions.json'), patch.object(versions, 'TRASH', skills / '.trainer-trash'):
                for identity in ['test.base', 'test.child']:
                    directory = skills / 'generated' / identity.replace('.', '/')
                    directory.mkdir(parents=True)
                    (directory / 'SKILL.md').write_text('---\nid: ' + identity + '\nstatus: provisional\n---\n# Test')
                versions.register_approved_version('test.base', 'test.child')
                versions.trash('test.base', 'test.child')
                self.assertEqual([s['id'] for s in repository.list_skills()], ['test.base'])
                versions.restore('test.base', 'test.child')
                versions.activate('test.base', 'test.child')
                self.assertEqual(versions.history('test.base')['activeId'], 'test.child')
