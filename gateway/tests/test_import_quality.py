import unittest
from validator import validate_import_quality


class ImportQualityTests(unittest.TestCase):
    def test_staging_blocks_incomplete_import_and_preserves_library_category(self):
        from unittest.mock import patch
        import server
        result = {'draft': {}, 'validation': {'valid': True, 'errors': []}}
        with patch.object(server, 'current_id', return_value=None), patch.object(server, 'checkpoint'), patch.object(server, 'generate_draft', return_value=result), patch.object(server, 'stage_pending', return_value={}) as stage:
            output = server.generate_and_stage({'generationMode': 'project-import'}, 'project-import')
        self.assertFalse(output['validation']['valid'])
        self.assertEqual(output['draft']['category'], 'course')
        self.assertEqual(output['importQuality']['level'], 'structure-only')
        stage.assert_called_once()

    def test_missing_sections_are_reported(self):
        result = validate_import_quality({'exerciseMarkdown': '介绍变量', 'validationChecklist': ''})
        self.assertFalse(result['valid'])
        self.assertEqual(len(result['errors']), 7)

    def test_headings_without_content_do_not_pass(self):
        result = validate_import_quality({'exerciseMarkdown': '\n'.join('## ' + x for x in ['读懂', '跑通', '修改', '测试', '独立重建', '提交材料']), 'validationChecklist': '## 验收标准'})
        self.assertFalse(result['valid'])

    def test_sections_are_structural_not_mastery_validation(self):
        result = validate_import_quality({'exerciseMarkdown': '\n'.join('## ' + x + '\n明确本阶段的目标、产物与操作步骤。' for x in ['读懂', '跑通', '修改', '测试', '独立重建', '提交材料']), 'validationChecklist': '## 验收标准\n列出正常、边界和失败条件。'})
        self.assertTrue(result['valid'])
        self.assertEqual(result['level'], 'structure-only')
