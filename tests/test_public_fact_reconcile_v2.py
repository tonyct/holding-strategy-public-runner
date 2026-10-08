import unittest
from engine.financial_fact_engine_v2 import fact
from ops.public_fact_reconcile_v2 import reconcile
def f(v,sha):
 return fact({"symbol":"600795.SH","field":"operating_cash_flow","value":v,"currency":"CNY","scope":"CONSOLIDATED","period_start":"2026-01-01","period_end":"2026-06-30","period_type":"H1_YTD","source":{"document_sha256":sha*64,"page":12}})
class ReconcileTests(unittest.TestCase):
 def test_conflicting_documents(self):
  v=reconcile([f("100","a"),f("110","b")],["600795.SH"])["stocks"]["600795.SH"]
  self.assertEqual(v["comparisons"][0]["status"],"CONFLICT_REVIEW_REQUIRED")
  self.assertFalse(v["independent_fact_verification"])
 def test_same_document_cannot_be_independent(self):
  v=reconcile([f("100","a"),f("100","a")],["600795.SH"])["stocks"]["600795.SH"]
  self.assertEqual(v["comparisons"][0]["status"],"SAME_DOCUMENT_CONSISTENT_NOT_INDEPENDENT")
 def test_independent_hash_consistency_not_verified(self):
  v=reconcile([f("100","a"),f("100","b")],["600795.SH"])["stocks"]["600795.SH"]
  self.assertEqual(v["comparisons"][0]["status"],"MULTI_DOCUMENT_CONSISTENT_NOT_INDEPENDENTLY_VERIFIED")
 def test_missing_fields(self):
  v=reconcile([],["600795.SH"])["stocks"]["600795.SH"]
  self.assertIn("issued_shares",v["missing_fields"])
  self.assertFalse(v["capital_structure_reconciled"])
if __name__=="__main__":unittest.main()
