import json
import tempfile
import unittest
from pathlib import Path
from ops.public_fact_routing_bridge import build
from ops.public_private_firewall import (
    check_json, check_request, check_public_universe, validate, PrivateDataBlocked,
)

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
    def test_public_routing_false_only_exact_schema_and_location(self):
        packet={"schema":"PUBLIC_API_FIRST_FACT_ROUTING/v1",
                "private_consumption_approved":False,
                "source_verification_state":"UNVERIFIED"}
        # Only the publication validator may authorize this exact location.
        with self.assertRaises(PrivateDataBlocked):
            check_json(packet)
        check_json(packet, allow_public_routing_control=True)
        for bad in (
            {**packet,"private_consumption_approved":True},
            {**packet,"private_consumption_approved":0},
            {**packet,"schema":"OTHER_SCHEMA"},
            {**packet,"account_nav":100},
            {**packet,"derived_from":"PRIVATE_ACCOUNT"},
            {"schema":"PUBLIC_API_FIRST_FACT_ROUTING/v1",
             "nested":{"private_consumption_approved":False}},
        ):
            with self.subTest(bad=repr(bad)), self.assertRaises(PrivateDataBlocked):
                check_json(bad, allow_public_routing_control=True)

    def test_actual_generated_routing_passes_publication_validator(self):
        universe={"schema":"E36_PUBLIC_RESEARCH_UNIVERSE/v1",
                  "source":"PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS",
                  "strategy_id":"PUBLIC_COMPANY_RESEARCH",
                  "stocks":[{"symbol":"600795.SH","active":True}]}
        packet=build(universe,{"facts":[]},[],"2026-10-08T04:00:00Z")
        self.assertIs(packet["private_consumption_approved"],False)
        self.assertEqual(packet["source_verification_state"],"UNVERIFIED")
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            output=base/"output"
            (output/"compute").mkdir(parents=True)
            routing=output/"compute"/"PUBLIC_API_FIRST_ROUTING_V1.json"
            routing.write_text(json.dumps(packet),encoding="utf-8")
            universe_path=base/"universe.json"
            universe_path.write_text(json.dumps(universe),encoding="utf-8")
            manifest=output/"PUBLIC_RESEARCH_BUNDLE.json"
            manifest.write_text(json.dumps({
                "schema":"E36_PUBLIC_RESEARCH_BUNDLE/v1",
                "privacy_class":"PUBLIC_MARKET_DATA_ONLY",
                "source_repository":"tonyct/holding-strategy-public-runner",
                "contains_account_state":False,
                "contains_portfolio_decision":False,
                "files":[{"path":"compute/PUBLIC_API_FIRST_ROUTING_V1.json"}]
            }),encoding="utf-8")
            self.assertEqual(validate(output,manifest,universe_path),1)
            # A real private flag still blocks the entire publication.
            packet["private_consumption_approved"]=True
            routing.write_text(json.dumps(packet),encoding="utf-8")
            with self.assertRaises(PrivateDataBlocked):
                validate(output,manifest,universe_path)
            # The same false flag in any other file is also rejected.
            packet["private_consumption_approved"]=False
            other=output/"compute"/"other.json"
            routing.unlink()
            other.write_text(json.dumps(packet),encoding="utf-8")
            manifest.write_text(json.dumps({
                "privacy_class":"PUBLIC_MARKET_DATA_ONLY",
                "source_repository":"tonyct/holding-strategy-public-runner",
                "contains_account_state":False,
                "contains_portfolio_decision":False,
                "files":[{"path":"compute/other.json"}]
            }),encoding="utf-8")
            with self.assertRaises(PrivateDataBlocked):
                validate(output,manifest,universe_path)

    def test_latest_persisted_routing_contract(self):
        fixture=Path("runtime/latest/compute/PUBLIC_API_FIRST_ROUTING_V1.json")
        if fixture.is_file():
            packet=json.loads(fixture.read_text(encoding="utf-8"))
            self.assertEqual(packet["schema"],"PUBLIC_API_FIRST_FACT_ROUTING/v1")
            self.assertIs(packet["private_consumption_approved"],False)
            check_json(packet,allow_public_routing_control=True)

    def test_upload_on_success_only(self):
        s=Path(".github/workflows/public_research.yml").read_text()
        self.assertNotIn("if: always()",s)
        self.assertIn("python -m ops.public_private_firewall",s)
        p=s.index("name: public-research-")
        self.assertIn("if: success()",s[p-120:p])

if __name__=="__main__":
    unittest.main()
