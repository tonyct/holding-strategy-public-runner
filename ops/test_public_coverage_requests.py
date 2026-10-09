"""Public-only dynamic coverage: no holdings, no private state, no ticker caps at 11."""
import copy
import unittest
from ops.public_coverage_requests import expand, MAX_SYMBOLS

U = {
    "schema": "E36_PUBLIC_RESEARCH_UNIVERSE/v1",
    "source": "PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS",
    "strategy_id": "PUBLIC_COMPANY_RESEARCH",
    "universe_version": "PUBLIC_BASE",
    "stocks": [{"symbol": "600941.SH", "active": True},
               {"symbol": "148.HK", "active": True}],
}
Q = {"schema": "PUBLIC_INDEPENDENT_COVERAGE_REQUESTS/v1",
     "source": "PUBLIC_RESEARCH_ONLY_NOT_ACCOUNT_HOLDINGS",
     "symbols": ["000001.SZ", "5.HK"]}


class Coverage(unittest.TestCase):
    def test_new_names_expand_without_private_information(self):
        prior = copy.deepcopy(U)
        out, r = expand(U, Q)
        self.assertEqual(len(out["stocks"]), 4)
        self.assertEqual(r["added_count"], 2)
        self.assertEqual(U, prior)
        self.assertTrue(r["research_scope_only_not_holdings"])
        self.assertTrue(r["no_private_repo_dependency"])
        self.assertFalse(r["automatic_fact_approval"])

    def test_idempotent_expansion_and_existing_scope(self):
        one, _ = expand(U, Q)
        two, receipt = expand(one, Q)
        self.assertEqual(one, two)
        self.assertEqual(receipt["added_count"], 0)

    def test_account_metadata_blocked_and_ticker_list_constrained(self):
        for extra in ({"holdings": [{"symbol": "000001.SZ"}]},
                      {"private_reason": "owned"},
                      {"cost_basis": 5}):
            with self.assertRaisesRegex(ValueError, "PRIVACY"):
                expand(U, dict(Q, **extra))
        for invalid in (["AAPL"], ["600941.SH", "600941.SH"],
                        ["../../../etc/passwd"]):
            with self.assertRaises(ValueError):
                expand(U, dict(Q, symbols=invalid))

    def test_no_overwrite_or_duplicate_existing_public_pool(self):
        bad = copy.deepcopy(U)
        bad["stocks"].append({"symbol": "148.HK", "active": True})
        with self.assertRaises(ValueError):
            expand(bad, Q)
        self.assertGreater(MAX_SYMBOLS, 20)


if __name__ == "__main__":
    unittest.main()
