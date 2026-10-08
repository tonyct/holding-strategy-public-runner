import unittest
from ops.public_api_snapshot_adapter import convert_a_snapshot
class AdapterTests(unittest.TestCase):
 def test_known_cny_scope_converts_to_candidates(self):
  snap={"symbol":"600795.SH","report_period_end":"2026-06-30","collected_at":"2026-10-08T00:00:00Z",
        "statements":{"income":{"data":{"standard_fields":{"revenue":"4"},"raw_numeric_unit":"CNY_MILLIONS","accounting_scope":"CONSOLIDATED"}}}}
  rows,gaps=convert_a_snapshot(snap,"a"*64)
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]["unit_multiplier"],"1000000")
  self.assertEqual(rows[0]["period_start"],"2026-01-01")
 def test_unknown_units_rejected(self):
  snap={"symbol":"600795.SH","report_period_end":"2026-06-30",
        "statements":{"income":{"data":{"standard_fields":{"revenue":"4"},"raw_numeric_unit":"AS_RETURNED_BY_SOURCE_VERIFY_BEFORE_COMPARISON","accounting_scope":"CONSOLIDATED"}}}}
  rows,gaps=convert_a_snapshot(snap,"a"*64)
  self.assertFalse(rows)
  self.assertEqual(gaps[0]["reason"],"UNVERIFIED_UNIT_OR_SCOPE")
 def test_parent_not_assumed_consolidated(self):
  snap={"symbol":"600795.SH","report_period_end":"2026-06-30","collected_at":"2026-10-08T00:00:00Z",
        "statements":{"income":{"data":{"standard_fields":{"net_profit":"4"},"raw_numeric_unit":"CNY_YUAN","accounting_scope":"PARENT"}}}}
  rows,_=convert_a_snapshot(snap,"a"*64)
  self.assertEqual(rows[0]["scope"],"PARENT")
if __name__=="__main__":unittest.main()
