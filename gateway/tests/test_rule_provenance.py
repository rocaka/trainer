import unittest
from rule_provenance import provenance, compare_rules


class RuleProvenanceTests(unittest.TestCase):
    def test_compare_known_changed_and_legacy(self):
        saved = provenance({'rules': 'v1'}, 'project-import')
        self.assertEqual(compare_rules(saved, {'rules': 'v1'})['status'], 'current')
        self.assertEqual(compare_rules(saved, {'rules': 'v2'})['status'], 'changed')
        self.assertEqual(compare_rules(None, {})['status'], 'unknown')
        self.assertEqual(compare_rules({'fingerprint': 'fake'}, {})['status'], 'unknown')

    def test_stable_and_changes_with_rules_or_mode(self):
        a = provenance({'a': 'one', 'b': 'two'}, 'project-import')
        self.assertEqual(a, provenance({'b': 'two', 'a': 'one'}, 'project-import'))
        self.assertNotEqual(a['fingerprint'], provenance({'a': 'changed', 'b': 'two'}, 'project-import')['fingerprint'])
        self.assertNotEqual(a['fingerprint'], provenance({'a': 'one', 'b': 'two'}, 'course')['fingerprint'])
        self.assertNotIn('one', str(a))

    def test_no_fake_timestamp_or_content_certification(self):
        a = provenance({}, 'course')
        self.assertEqual(a['verification'], 'rules-recorded-not-content-verified')
        self.assertEqual(len(a['fingerprint']), 64)
