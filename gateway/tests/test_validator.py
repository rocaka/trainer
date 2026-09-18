import unittest

from validator import validate_draft


class DraftValidationTests(unittest.TestCase):
    def test_complete_provisional_draft_is_accepted(self):
        draft = {
            "id": "python.example.lesson",
            "title": "Example",
            "summary": "Example summary",
            "skillMarkdown": "---\nid: python.example.lesson\nstatus: provisional\n---\n# Example",
            "curriculumYaml": "prerequisites: []\ncontexts:\n  languages: [Python]",
            "conceptMarkdown": "# Concept",
            "exerciseMarkdown": "# 预测练习",
            "validationChecklist": "- validate",
        }
        self.assertEqual(validate_draft(draft), {"valid": True, "errors": []})

    def test_verified_status_is_rejected_for_model_output(self):
        draft = {
            "id": "python.example.lesson",
            "title": "Example", "summary": "Example summary",
            "skillMarkdown": "status: verified",
            "curriculumYaml": "prerequisites: []\ncontexts: {}",
            "conceptMarkdown": "x", "exerciseMarkdown": "预测", "validationChecklist": "x",
        }
        self.assertFalse(validate_draft(draft)["valid"])


if __name__ == "__main__":
    unittest.main()
