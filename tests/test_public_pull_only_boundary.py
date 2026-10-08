"""Prevent re-introducing any Public -> Private write or secret boundary."""
import json
import unittest
from pathlib import Path


class PublicPullOnlyBoundary(unittest.TestCase):
    def test_all_legacy_public_to_private_publishers_absent(self):
        for name in ("ops/private_state_sink.py",
                     "ops/private_sink_atomic_v2.py",
                     "ops/private_sink_v2_status.py"):
            self.assertFalse(Path(name).exists(), name)

    def test_contract_is_explicit_private_shadow_pull(self):
        cfg = json.loads(Path("config/public_data_contract.json").read_text())
        self.assertNotIn("optional_private_state_sink", cfg)
        policy = cfg["public_delivery"]
        self.assertEqual(policy["direction"], "PRIVATE_SHADOW_PULL_FROM_PUBLIC")
        self.assertTrue(policy["public_must_not_write_private_repository"])
        self.assertTrue(policy["public_must_not_store_private_write_credential"])
        self.assertEqual(policy["public_publish_repository"],
                         "tonyct/holding-strategy-public-runner")
        handoff = json.loads(Path("config/public_shadow_handoff_contract.json").read_text())
        self.assertEqual(handoff["consumer"], "PRIVATE_SHADOW_PULL")
        self.assertTrue(handoff["public_security"]["public_push_to_private_prohibited"])

    def test_all_public_workflows_reject_private_write_tokens(self):
        workflows = Path(".github/workflows")
        for path in workflows.glob("*.yml"):
            content = path.read_text()
            with self.subTest(path=str(path)):
                self.assertNotIn("PRIVATE_STATE_WRITE_TOKEN", content)
                self.assertNotIn("ops.private_state_sink", content)
                self.assertNotIn("ops.private_sink_atomic_v2", content)
                self.assertNotIn("holding-strategy-data", content)
                self.assertNotIn("secrets.PRIVATE_", content)
        source = (workflows / "public_research.yml").read_text()
        self.assertIn('test "${GITHUB_REPOSITORY}" = "tonyct/holding-strategy-public-runner"', source)
        self.assertIn("PUBLIC_REMOTE_MISMATCH", source)
        self.assertIn("git push origin HEAD:main", source)

    def test_no_executable_public_sink_in_repo(self):
        for root in ("ops", "engine"):
            for path in Path(root).rglob("*.py"):
                content = path.read_text()
                with self.subTest(path=str(path)):
                    self.assertNotIn("PRIVATE_STATE_WRITE_TOKEN", content)
                    self.assertNotIn("holding-strategy-data", content)


if __name__ == "__main__":
    unittest.main()
