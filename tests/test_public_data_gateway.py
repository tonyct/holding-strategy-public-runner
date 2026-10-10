"""Contract tests for the PUBLIC-only on-demand gateway (offline)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.public_data_gateway import SCHEMA, CATEGORIES, validate, process

BASE = {"schema": SCHEMA, "request_id": "pubtest_20261010",
        "operation": "EXECUTE", "symbol": "001286.SZ",
        "data_type": "historical_quotes", "start_date": "2026-09-01",
        "end_date": "2026-09-30", "source": "AUTO"}

class GatewayContractTest(unittest.TestCase):
    def test_valid_request(self):
        validate(dict(BASE))
    def test_detect_private_fields(self):
        for field in ("holdings", "cost_basis", "thesis", "target_price", "portfolio"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate({**BASE, field: "secret"})
    def test_reject_unknown_type(self):
        with self.assertRaises(ValueError):
            validate({**BASE, "data_type": "unvalidated_anything"})
    def test_reject_unknown_source(self):
        with self.assertRaises(ValueError):
            validate({**BASE, "source": "https://example.org"})
    def test_reject_long_window(self):
        with self.assertRaises(ValueError):
            validate({**BASE, "start_date": "2020-01-01"})
    def test_hk_quotes_supported_but_hk_financials_not_yet(self):
        validate({**BASE, "symbol": "00700.HK", "source": "AUTO"})
        validate({**BASE, "symbol": "00700.HK", "source": "akshare"})
        with self.assertRaises(ValueError):
            validate({**BASE, "symbol": "00700.HK", "source": "baostock"})
        with self.assertRaises(ValueError):
            validate({**BASE, "symbol": "00700.HK", "data_type": "financial_statements"})
    def test_discovery_seeds_are_public_coverage_not_holdings(self):
        seed=CATEGORIES["historical_quotes"]["public_research_coverage_seed"]
        self.assertFalse(seed["complete_market_universe"])
        self.assertIn("NOT_ACCOUNT_HOLDINGS",seed["source"])
        self.assertIn("001286.SZ",seed["symbols"])
        self.assertIn("9926.HK",seed["symbols"])
        self.assertFalse(any("private" in x.lower() for x in seed["symbols"]))

    def test_discover(self):
        req={"schema": SCHEMA, "request_id": "discover001", "operation": "DISCOVER"}
        with tempfile.TemporaryDirectory() as d:
            r=process(req, d)
            self.assertEqual(r["status"], "DELIVERED")
            self.assertEqual(r["capabilities"], CATEGORIES)
            self.assertTrue((Path(d)/"PUBLIC_GATEWAY_RECEIPT.json").exists())
    def test_mocked_fetch_and_sha(self):
        with tempfile.TemporaryDirectory() as d, patch("ops.public_data_gateway.execute",
                 return_value=([{"date":"2026-09-01","close":"10.50"}], "FETCHED_UNVERIFIED")):
            r=process(dict(BASE),d)
            self.assertEqual(r["status"],"DELIVERED")
            self.assertEqual(r["row_count"],1)
            import hashlib
            self.assertEqual(hashlib.sha256((Path(d)/r["response_file"]).read_bytes()).hexdigest(),
                             r["response_sha256"])
            self.assertFalse(r["economic_verified"])
    def test_mocked_failure_reports_gap(self):
        with tempfile.TemporaryDirectory() as d, patch("ops.public_data_gateway.execute",
                                                          side_effect=RuntimeError("HTTP_429")):
            r=process(dict(BASE),d)
            self.assertEqual(r["status"],"GAP")
            self.assertEqual(r["fetch_state"],"FAILED")
            self.assertIn("HTTP_429",r["error_code"])

if __name__=="__main__":
    unittest.main()
