import json,tempfile,unittest
from pathlib import Path
from engine.public_evidence_index import build
class PublicEvidenceIndexTests(unittest.TestCase):
 def test_cardinality_is_dynamic_and_bundle_is_excluded(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/"a").mkdir();(r/"a/x.json").write_text(json.dumps({"schema":"X/v1","status":"OK"}));(r/"z.json").write_text("{}")
   (r/"PUBLIC_RESEARCH_BUNDLE.json").write_text("{}")
   out=build(r);self.assertEqual(out["artifact_count"],2);self.assertTrue(out["dynamic_cardinality"]);self.assertFalse(out["fixed_document_count_assumed"])
   self.assertNotIn("PUBLIC_RESEARCH_BUNDLE.json",[x["path"] for x in out["artifacts"]])
if __name__=="__main__":unittest.main()
