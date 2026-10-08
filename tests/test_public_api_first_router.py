import unittest
from ops.public_api_first_router import route,validate
NOW="2026-10-08T04:00:00Z"
def record(field,value="100",source="PUBLIC_API",**kw):
 r={"symbol":"148.HK","field":field,"value":value,"source_type":source,
    "source_id":"test-source","observed_at":NOW,"currency":"HKD",
    "period_start":"2026-01-01","period_end":"2026-06-30",
    "period_type":"H1_YTD","scope":"CONSOLIDATED","unit_multiplier":"1000",
    "price_session":"2026-10-08","metric_definition":"reported ratio",
    "denominator_period":"TTM"}
 r.update(kw)
 return r
class TestRouter(unittest.TestCase):
 def test_no_unverified_automatic_approval(self):
  q=route(["148.HK"],[record("revenue")],NOW)
  self.assertFalse(q["selected_candidates"]["148.HK"]["revenue"]["usable_for_frozen_valuation"])
  self.assertEqual(q["selected_candidates"]["148.HK"]["revenue"]["value_normalized"],"100000")
  self.assertTrue(q["ai_fallback_tasks"])
 def test_old_market_data_must_expire(self):
  q=route(["148.HK"],[record("pe",observed_at="2026-10-01T04:00:00Z")],NOW)
  self.assertNotIn("pe",q["selected_candidates"].get("148.HK",{}))
 def test_different_currency_is_not_merged(self):
  q=route(["148.HK"],[record("revenue"),record("revenue",currency="CNY")],NOW)
  self.assertIn("MIXED_CONTEXT_REQUIRES_RECONCILIATION",[x["reason"] for x in q["gaps"]])
 def test_conflicting_values_do_not_get_silent_winner(self):
  q=route(["148.HK"],[record("revenue"),record("revenue",value="200")],NOW)
  self.assertNotIn("revenue",q["selected_candidates"].get("148.HK",{}))
 def test_ai_requires_page_and_literal_proof(self):
  self.assertEqual(validate(record("revenue",source="AI_DOCUMENT_EXTRACTION")),"AI_EVIDENCE_REQUIRED")
 def test_unknown_currency_not_accepted(self):
  self.assertEqual(validate(record("revenue",currency="UNVERIFIED")),"UNVERIFIED_CURRENCY")
 def test_numeric_equivalent_sources_do_not_conflict(self):
  q=route(["148.HK"],[record("revenue","1.0"),record("revenue","1.00")],NOW)
  self.assertIn("revenue",q["selected_candidates"]["148.HK"])
 def test_dynamic_universe(self):
  q=route(["148.HK","600941.SH"],[],NOW)
  self.assertEqual(len(q["symbols"]),2)
  self.assertEqual(len(q["ai_fallback_tasks"]),22)
if __name__=="__main__":unittest.main()
