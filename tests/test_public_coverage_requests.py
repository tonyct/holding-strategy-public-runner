import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from ops.public_coverage_requests import expand


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.u = {"schema": "E36_PUBLIC_RESEARCH_UNIVERSE/v1",
                  "source": "PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS",
                  "strategy_id": "PUBLIC_COMPANY_RESEARCH",
                  "stocks": [{"symbol": "001286.SZ", "active": True},
                             {"symbol": "148.HK", "active": False}]}
        self.req = {"schema": "PUBLIC_INDEPENDENT_COVERAGE_REQUESTS/v1",
                    "source": "PUBLIC_RESEARCH_ONLY_NOT_ACCOUNT_HOLDINGS",
                    "symbols": ["148.HK", "600941.SH"]}

    def test_reactivation_is_idempotent_and_does_not_change_input(self):
        original = copy.deepcopy(self.u)
        out, receipt = expand(self.u, self.req)
        self.assertEqual(self.u, original)
        self.assertEqual(receipt["added_count"], 1)
        self.assertEqual(receipt["reactivated_count"], 1)
        again, receipt = expand(out, self.req)
        self.assertEqual(again, out)
        self.assertEqual(receipt["added_count"], 0)
        self.assertEqual(receipt["reactivated_count"], 0)

    def test_private_fields_and_capacity_overflow_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "PRIVACY_INVALID"):
            expand(self.u, dict(self.req, cost_basis=100))
        too_many = dict(self.req, symbols=[f"{i:06d}.SH" for i in range(151)])
        with self.assertRaisesRegex(ValueError, "LIMIT"):
            expand(self.u, too_many)

    def test_real_packet_cli_matches_dynamic_12_20_50_100_scope(self):
        for count in (12, 20, 50, 100):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                symbols = [f"{i:06d}.SH" for i in range(count)]
                universe = dict(self.u, stocks=[{"symbol": t, "active": True} for t in symbols])
                files = {"universe": universe, "metrics": {}, "a-originals": {},
                         "hk-originals": {}, "text-candidates": {}, "lead-registry": {}}
                cmd = [sys.executable, "-m", "ops.public_company_compute"]
                for name, body in files.items():
                    path = root / (name + ".json")
                    path.write_text(json.dumps(body))
                    cmd += ["--" + name, str(path)]
                output = root / "packets.json"
                subprocess.run(cmd + ["--run-id", "TEST_DYNAMIC_SCOPE", "--output", str(output)],
                               check=True, capture_output=True, text=True)
                doc = json.loads(output.read_bytes())
                self.assertEqual(set(doc["packets"]), set(symbols))
                self.assertFalse(doc["automatic_fact_promotion"])
                self.assertFalse(doc["automatic_trade_execution"])


if __name__ == "__main__":
    unittest.main()
