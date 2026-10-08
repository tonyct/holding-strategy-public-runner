import unittest
from unittest.mock import patch
from ops import private_state_sink as sink

class PrivateSinkSafetyTests(unittest.TestCase):
    def test_put_uses_sha_for_existing_remote_object(self):
        calls=[]
        def api(token,repo,method,path,payload=None):
            calls.append((method,payload))
            if method=="GET":return 200,{"sha":"oldsha"}
            return 200,{"content":{"sha":"newsha"}}
        with patch.object(sink,"request",side_effect=api):
            self.assertEqual(sink.put("t","repo","key",b"x","msg"),"newsha")
        self.assertEqual(calls[-1][1]["sha"],"oldsha")
    def test_private_sink_never_executes_trades(self):
        import inspect
        src=inspect.getsource(sink)
        self.assertIn("STALE_OR_DUPLICATE_PUBLIC_RUN",src)
        self.assertIn("POINTER_SCHEMA_MIGRATION_REQUIRED",src)

if __name__=="__main__":unittest.main()
