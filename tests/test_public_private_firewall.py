import unittest
from pathlib import Path
from ops.public_private_firewall import check_json, check_request, check_public_universe, PrivateDataBlocked

class PublicFirewallTests(unittest.TestCase):
    def test_public_financials(self):
        check_json({"symbol":"ABC","financials":{"cash":10,"net_debt":2},"privacy_class":"PUBLIC_MARKET_DATA_ONLY"})
    def test_private_lineage_and_outputs(self):
        for k in ("account_nav","portfolio_weight","cost_basis","position_size","private_valuation","unrealized_pnl"):
            with self.subTest(k=k), self.assertRaises(PrivateDataBlocked):
                check_json({k:1})
        for payload in ({"derived_from_private":True},{"derived_from":"PRIVATE_ACCOUNT"}):
            with self.assertRaises(PrivateDataBlocked):
                check_json(payload)
    def test_request_gate(self):
        check_request("PUBLIC_REFRESH","public-refresh001")
        with self.assertRaises(PrivateDataBlocked):
            check_request("PRIVATE_ACCOUNT_REVIEW","public-refresh001")
    def test_upload_on_success_only(self):
        s=Path(".github/workflows/public_research.yml").read_text()
        self.assertNotIn("if: always()",s)
        self.assertIn("python -m ops.public_private_firewall",s)
        p=s.index("name: public-research-")
        self.assertIn("if: success()",s[p-120:p])

if __name__=="__main__":
    unittest.main()
