import unittest
from ops.public_fact_quality_v2 import quality
from engine.financial_fact_engine_v2 import fact
SHA="a"*64
class QualityTests(unittest.TestCase):
    def test_missing_field_receipt_no_promotion(self):
        q=quality({"stocks":[{"symbol":"A.HK","active":True}]},{"facts":[]},[])
        a=q["stocks"]["A.HK"]
        self.assertEqual(a["research_state"],"NO_SOURCE_BOUND_FACTS")
        self.assertFalse(a["valuation_authorized"])
        self.assertIn("operating_cash_flow",a["missing_research_fields"])
    def test_source_bound_and_conflicts(self):
        base={"symbol":"A.HK","field":"operating_cash_flow","value":"5","currency":"HKD",
              "period_start":"2026-01-01","period_end":"2026-06-30",
              "period_type":"H1_YTD","scope":"CONSOLIDATED","source":{"document_sha256":SHA,"page":1}}
        x=fact(base);y=fact({**base,"value":"6"})
        q=quality({"stocks":[{"symbol":"A.HK","active":True}]},{"facts":[x,y]},[{"symbol":"A.HK","page_count":5}])
        r=q["stocks"]["A.HK"]
        self.assertEqual(r["source_document_count"],1)
        self.assertEqual(len(r["numeric_conflicts"]),1)
        self.assertFalse(r["decisive_primary_financial_evidence_verified"])
if __name__=="__main__":unittest.main()
