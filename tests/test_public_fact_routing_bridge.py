import unittest
from ops.public_fact_routing_bridge import build
from engine.financial_fact_engine_v2 import fact
NOW="2026-10-08T04:00:00Z"
class BridgeTests(unittest.TestCase):
 def test_source_bound_candidate_but_no_valuation(self):
  row={"symbol":"600795.SH","field":"operating_cash_flow","value":"12",
      "currency":"CNY","period_start":"2026-01-01","period_end":"2026-06-30",
      "period_type":"H1_YTD","scope":"CONSOLIDATED",
      "source":{"document_sha256":"a"*64,"page":6}}
  q=build({"stocks":[{"symbol":"600795.SH","active":True}]},{"facts":[fact(row)]},[],NOW)
  self.assertEqual(q["inputs"]["original_document_candidate_count"],1)
  self.assertEqual(q["selected_candidates"]["600795.SH"]["operating_cash_flow"]["value_normalized"],"12")
  self.assertFalse(q["private_consumption_approved"])
  self.assertFalse(q["selected_candidates"]["600795.SH"]["operating_cash_flow"]["usable_for_frozen_valuation"])
 def test_ai_queue_only_for_core_gaps(self):
  q=build({"stocks":[{"symbol":"600795.SH","active":True}]},{"facts":[]},[],NOW)
  self.assertEqual(len(q["ai_fallback_tasks"]),11)
  self.assertFalse(q["model_output_auto_approved"])
if __name__=="__main__":unittest.main()
