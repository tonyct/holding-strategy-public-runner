import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import public_lead_registry as registry
from ops.public_company_compute import unresolved


class LeadLifecycleTests(unittest.TestCase):
    def test_explicit_noise_and_low_information_are_retired(self):
        self.assertEqual(registry.classify('community', {'discovery_relation': 'CROSS_BOARD'}), 'CROSS_BOARD_NOISE')
        self.assertEqual(registry.classify('community', {'quality_category': 'PURE_SENTIMENT_OR_LOW_INFORMATION'}), 'RETIRED_LOW_INFORMATION')

    def test_original_locator_is_still_open_research(self):
        state = registry.classify('ir', {'source': 'OFFICIAL_ANNOUNCEMENT_INDEX'})
        self.assertEqual(state, 'PRIMARY_SOURCE_LOCATOR_AVAILABLE')
        self.assertTrue(unresolved(state))
        self.assertTrue(unresolved(None))
        self.assertTrue(unresolved('NEW_UNKNOWN_REVIEW_STAGE'))

    def test_reobservation_preserves_existing_review_progress(self):
        state = 'PRIMARY_SOURCE_BYTES_CAPTURED_SEMANTIC_REVIEW_PENDING'
        self.assertEqual(registry.classify('ir', {'source': 'OFFICIAL_ANNOUNCEMENT_INDEX'}, state), state)
        self.assertEqual(registry.classify('community', {}, 'VERIFIED_NO_MATERIAL_FACT'), 'VERIFIED_NO_MATERIAL_FACT')

    def test_registry_counts_only_explicit_terminal_states(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / 'registry.json'
            state.write_text(json.dumps({'schema': registry.SCHEMA, 'leads': {
                'locator': {'symbol': '148.HK', 'state': 'PRIMARY_SOURCE_LOCATOR_AVAILABLE'},
                'unknown': {'symbol': '148.HK', 'state': 'UNKNOWN_STAGE'},
                'closed': {'symbol': '148.HK', 'state': 'CROSS_BOARD_NOISE'},
            }}))
            with patch('sys.argv', ['registry', '--registry', str(state), '--run-id', 'TEST_LIFECYCLE', '--output', str(root / 'out.json')]):
                registry.main()
            result = json.loads(state.read_text())
            self.assertEqual(result['counts']['pending'], 2)
            self.assertEqual(result['counts']['terminal'], 1)
            self.assertTrue(result['leads']['locator']['source_disappearance_is_not_resolution'])
            self.assertTrue(result['leads']['unknown']['source_disappearance_is_not_resolution'])
            self.assertNotIn('source_disappearance_is_not_resolution', result['leads']['closed'])

    def test_malformed_registry_rows_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'registry.json'
            path.write_text(json.dumps({'schema': registry.SCHEMA, 'leads': []}))
            with self.assertRaisesRegex(ValueError, 'ROWS_INVALID'):
                registry.load(path)


if __name__ == '__main__':
    unittest.main()
