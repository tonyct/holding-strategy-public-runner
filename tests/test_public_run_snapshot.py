import json,tempfile,unittest
from pathlib import Path
from engine.public_run_snapshot import build
class PublicRunSnapshotTests(unittest.TestCase):
 def test_exact_public_lineage_only(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);objs={
    "u":{"stocks":[{"symbol":"A.SH","active":True}]},
    "h":{"status":"PASS"},
    "e":{"schema":"PUBLIC_EVIDENCE_INDEX/v1","artifact_count":3},
    "m":{"schema":"PUBLIC_DETERMINISTIC_METRICS/v1","active_symbol_count":1}}
   for n,x in objs.items():(p/f"{n}.json").write_text(json.dumps(x))
   out=build(p/"u.json",p/"h.json",p/"e.json",p/"m.json","123","1","a"*40)
   self.assertEqual(out["source_run_id"],"123");self.assertTrue(out["immutable_run_binding"]);self.assertTrue(out["no_private_repo_dependency"])
   self.assertFalse(out["contains_portfolio_decision"])
if __name__=="__main__":unittest.main()
