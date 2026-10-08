import json,unittest
from pathlib import Path
class PublicComputeContractTests(unittest.TestCase):
 def test_contract_is_public_only_and_dynamic(self):
  c=json.loads(Path("config/public_data_contract.json").read_text())
  self.assertEqual(c["role"],"PUBLIC_MARKET_DATA_EVIDENCE_AND_DETERMINISTIC_COMPUTE_ONLY")
  self.assertTrue(c["no_private_repo_dependency"]);self.assertTrue(c["deterministic_public_compute_only"])
  self.assertTrue(c["no_valuation_logic"]);self.assertTrue(c["no_recommendation_logic"]);self.assertTrue(c["no_trade_logic"])
  self.assertEqual(c["public_delivery"]["direction"],"PRIVATE_SHADOW_PULL_FROM_PUBLIC")
  self.assertNotIn("optional_private_state_sink",c)
 def test_workflow_wires_compute_before_manifest(self):
  s=Path(".github/workflows/public_research.yml").read_text()
  names=["Update durable public lead lifecycle","Resolve deterministic public lead lifecycle",
         "Build deterministic public metrics","Build public company research packets",
         "Build dynamic public evidence index","Freeze exact public run snapshot","Build public-safe manifest"]
  pos=[s.index(x) for x in names];self.assertEqual(pos,sorted(pos))
  # Public is the computation boundary. It must never write Private state.
  self.assertNotIn("Optionally archive public state and official evidence into Private storage",s)
  self.assertNotIn("PRIVATE_STATE_WRITE_TOKEN",s)
  self.assertNotIn("holding-strategy-data",s)
  self.assertIn("Validate public data-only contract",s)
  self.assertIn("Public-safety gate",s)
  self.assertIn("Persist latest public JSON bundle",s)
  self.assertIn("PUBLIC_LEAD_RESOLUTION_REPORT.json",s);self.assertIn("PUBLIC_DETERMINISTIC_METRICS.json",s);self.assertIn("PUBLIC_EVIDENCE_INDEX.json",s);self.assertIn("PUBLIC_RUN_SNAPSHOT.json",s)
  self.assertFalse(any('\\n          assert contract.get' in line for line in s.splitlines()), 'BROKEN_LITERAL_NEWLINE_ASSERT')
  self.assertNotIn('\\\\n          assert contract.get',s)
 def test_evidence_readiness_does_not_equate_empty_complete_window_with_primary_evidence(self):
  s=Path(".github/workflows/public_research.yml").read_text()
  self.assertIn("75 days ago",s)
  c=Path("ops/public_company_compute.py").read_text()
  self.assertNotIn("PUBLIC_PRIMARY_EVIDENCE_READY",c)
  self.assertIn("WINDOW_COMPLETE_NO_NEW_OFFICIAL_ORIGINALS",c)
  l=Path("ops/public_lead_registry.py").read_text()
  self.assertIn("every article must have its own lifecycle id",l)

if __name__=="__main__":unittest.main()
