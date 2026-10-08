import json,unittest
from pathlib import Path
class PublicComputeContractTests(unittest.TestCase):
 def test_contract_is_public_only_and_dynamic(self):
  c=json.loads(Path("config/public_data_contract.json").read_text())
  self.assertEqual(c["role"],"PUBLIC_MARKET_DATA_EVIDENCE_AND_DETERMINISTIC_COMPUTE_ONLY")
  self.assertTrue(c["no_private_repo_dependency"]);self.assertTrue(c["deterministic_public_compute_only"])
  self.assertTrue(c["no_valuation_logic"]);self.assertTrue(c["no_recommendation_logic"]);self.assertTrue(c["no_trade_logic"])
 def test_workflow_wires_compute_before_manifest(self):
  s=Path(".github/workflows/public_research.yml").read_text()
  names=["Build deterministic public metrics","Build dynamic public evidence index","Freeze exact public run snapshot","Build public-safe manifest"]
  pos=[s.index(x) for x in names];self.assertEqual(pos,sorted(pos))
  sink="Optionally archive public state and official evidence into Private storage"
  self.assertIn(sink,s)
  sink_pos=s.index(sink)
  self.assertNotIn("holding-strategy-data",s[:sink_pos])
  self.assertIn("holding-strategy-data",s[sink_pos:])
  self.assertIn("PRIVATE_STATE_WRITE_TOKEN",s[sink_pos:])
  self.assertIn("PUBLIC_DETERMINISTIC_METRICS.json",s);self.assertIn("PUBLIC_EVIDENCE_INDEX.json",s);self.assertIn("PUBLIC_RUN_SNAPSHOT.json",s)
  self.assertFalse(any('\\n          assert contract.get' in line for line in s.splitlines()), 'BROKEN_LITERAL_NEWLINE_ASSERT')
  self.assertNotIn('\\\\n          assert contract.get',s)
if __name__=="__main__":unittest.main()
