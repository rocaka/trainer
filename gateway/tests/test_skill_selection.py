import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import repository
import version_store


class SkillSelectionTests(unittest.TestCase):
    def test_missing_parent_uses_existing_selected_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / 'child'
            child.mkdir()
            (child / 'SKILL.md').write_text('---\nid: go.child\n---\n# Go')
            with patch.object(repository, 'SKILLS_ROOT', root), patch.object(version_store, 'history', return_value={'activeId': 'go.parent'}):
                self.assertEqual(version_store.resolve_teaching_id('go.child'), 'go.child')
                with self.assertRaises(FileNotFoundError):
                    version_store.resolve_teaching_id('go.missing')

    def test_explicit_category_overrides_legacy_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            text = '从零写一个项目'
            self.assertEqual(repository._category(directory, {}, text, 'provisional'), 'project-practice')
            (directory / '.trainer-category.json').write_text('{"category":"course"}')
            self.assertEqual(repository._category(directory, {}, text, 'provisional'), 'course')
            self.assertEqual(repository._category(directory, {}, text, 'core'), 'core')

    def test_existing_active_version_remains_authoritative(self):
        with patch.object(version_store, 'history', return_value={'activeId': 'go.active'}), patch.object(version_store, '_skill_path'):
            self.assertEqual(version_store.resolve_teaching_id('go.child'), 'go.active')
