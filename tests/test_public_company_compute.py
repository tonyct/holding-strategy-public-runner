import unittest
from ops.public_company_compute import original_state,research_state
class CompanyComputeStateTests(unittest.TestCase):
 def test_empty_complete_window_is_not_primary_evidence(self):
  o={"indexed":0,"fetched":0,"complete":True}
  self.assertEqual(original_state(o),"WINDOW_COMPLETE_NO_NEW_OFFICIAL_ORIGINALS")
  self.assertEqual(research_state(o,{"financials":{"source_verification_state":"CORE_THREE_STATEMENTS_UNVERIFIED"}},[]),
    "PUBLIC_WINDOW_COMPLETE_NO_NEW_ORIGINALS_STRUCTURED_FINANCIALS_UNVERIFIED")
 def test_complete_nonempty_window_is_evidence_packet_not_fact_verification(self):
  o={"indexed":2,"fetched":2,"complete":True}
  self.assertEqual(original_state(o),"CURRENT_WINDOW_ORIGINALS_COMPLETE")
  self.assertEqual(research_state(o,{},[{"x":1}]),"PUBLIC_EVIDENCE_PACKET_AVAILABLE")
if __name__=="__main__":unittest.main()
