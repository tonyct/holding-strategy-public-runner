import unittest,tempfile,json
from pathlib import Path
from ops.private_sink_atomic_v2 import preflight
class AtomicSinkTests(unittest.TestCase):
 def fixture(self):
  temp=tempfile.TemporaryDirectory()
  root=Path(temp.name)
  (root/"PUBLIC_RESEARCH_BUNDLE.json").write_text(json.dumps({"source_run_id":"123","contains_account_state":False,"contains_portfolio_decision":False,"source_run_attempt":"1"}))
  (root/"ACQUISITION_HEALTH.json").write_text('{"status":"DEGRADED"}')
  return temp,root
 def test_v2_preserves_epoch(self):
  t,r=self.fixture()
  _,p=preflight(r,"123",{"schema":"PRIVATE_PUBLIC_INPUT_POINTER/v2","source":{"run_id":"122"},"active_version":"4.8.0","epoch":36})
  self.assertEqual(p["epoch"],36)
  self.assertEqual(p["schema"],"PRIVATE_PUBLIC_INPUT_POINTER/v2")
  self.assertFalse(p["automatic_trade_execution"])
  t.cleanup()
 def test_stale_rejected(self):
  t,r=self.fixture()
  with self.assertRaisesRegex(ValueError,"STALE_RUN"):preflight(r,"123",{"schema":"PRIVATE_PUBLIC_INPUT_POINTER/v2","source":{"run_id":"123"}})
  t.cleanup()
 def test_v1_downgrade_rejected(self):
  t,r=self.fixture()
  with self.assertRaisesRegex(ValueError,"INCOMPATIBLE_POINTER"):preflight(r,"123",{"schema":"PRIVATE_PUBLIC_INPUT_POINTER/v1"})
  t.cleanup()
 def test_missing_required_rejected(self):
  t,r=self.fixture()
  (r/"ACQUISITION_HEALTH.json").unlink()
  with self.assertRaisesRegex(ValueError,"MISSING_REQUIRED"):preflight(r,"123",None)
  t.cleanup()
if __name__=="__main__":unittest.main()
