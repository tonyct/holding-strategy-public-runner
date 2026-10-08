import unittest
from ops.public_lead_resolver import resolve

class LeadResolverTests(unittest.TestCase):
 def base(self,rows):
  return {"schema":"PUBLIC_LEAD_LIFECYCLE_REGISTRY/v1","leads":rows}
 def test_conservative_terminal_and_binding_states(self):
  leads={
   "low":{"lead_id":"low","source":"community","symbol":"A","state":"PRIMARY_SOURCE_VERIFICATION_PENDING",
     "latest_observation":{"quality_category":"PURE_SENTIMENT_OR_LOW_INFORMATION",
       "qualified_for_shadow_verification":False,"shadow_verification_priority":"NONE"}},
   "cross":{"lead_id":"cross","source":"community","symbol":"A","state":"PRIMARY_SOURCE_VERIFICATION_PENDING",
     "latest_observation":{"discovery_relation":"CROSS_BOARD",
       "qualified_for_target_specific_shadow_verification":False,"qualified_for_shadow_verification":True}},
   "official":{"lead_id":"official","source":"ir","symbol":"A","state":"PRIMARY_SOURCE_VERIFICATION_PENDING",
     "latest_observation":{"source":"OFFICIAL_ANNOUNCEMENT_INDEX","title":"关于召开2026年半年度业绩说明会的公告",
       "announced_at":"2026-09-29","url":"https://x/?announcementId=123"}},
   "secondary":{"lead_id":"secondary","source":"ir","symbol":"A","state":"PRIMARY_SOURCE_VERIFICATION_PENDING",
     "latest_observation":{"source":"SECONDARY_IR_DISCOVERY","title":"公司:关于召开2026年半年度业绩说明会的公告",
       "announced_at":"2026-09-29","url":"https://secondary/1"}},
   "hknoise":{"lead_id":"hknoise","source":"akshare","symbol":"148.HK","state":"PRIMARY_SOURCE_VERIFICATION_PENDING",
     "latest_observation":{"news":{"status":"SKIPPED_HK_NUMERIC_CODE_NOISE","rows":[]}}},
  }
  a={"symbols":{"A":{"files":[{"status":"FETCHED_OFFICIAL_ORIGINAL","announcement_id":"123",
       "date":"2026-09-29","title":"关于召开2026年半年度业绩说明会的公告",
       "sha256":"a"*64,"filename":"a.pdf"}]}}}
  reg,report=resolve(self.base(leads),a,{"symbols":{}})
  self.assertEqual(reg["leads"]["low"]["state"],"RETIRED_LOW_INFORMATION")
  self.assertEqual(reg["leads"]["cross"]["state"],"CROSS_BOARD_NOISE")
  self.assertEqual(reg["leads"]["official"]["state"],"PRIMARY_SOURCE_BYTES_CAPTURED_SEMANTIC_REVIEW_PENDING")
  self.assertFalse(reg["leads"]["official"]["primary_source_binding"]["semantic_fact_verified"])
  self.assertEqual(reg["leads"]["secondary"]["state"],"DUPLICATE_ALREADY_REGISTERED")
  self.assertEqual(reg["leads"]["hknoise"]["state"],"RETIRED_SOURCE_AMBIGUOUS")
  self.assertEqual(report["counts"]["pending"],1)
  self.assertFalse(report["automatic_fact_promotion"])
if __name__=="__main__":unittest.main()
