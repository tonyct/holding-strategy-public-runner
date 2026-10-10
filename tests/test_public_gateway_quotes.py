"""Offline test for historic quote source failover and strict row scopes."""
import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path
from ops.public_gateway_quotes import fetch_quotes

REQUEST={"symbol":"001286.SZ","start_date":"2025-09-01","end_date":"2025-09-30","source":"AUTO"}
ROW={"date":"2025-09-01","code":"001286","open":"10","high":"11","low":"9",
     "close":"10.5","volume":"1000","amount":"10000","adjustflag":"3"}

class QuoteRouterTests(unittest.TestCase):
    def test_fallback_provenance_in_receipt(self):
        from ops.public_data_gateway import process
        with tempfile.TemporaryDirectory() as d, patch("ops.public_data_gateway.execute",
             return_value=([dict(ROW)],{"source_used":"akshare","required":1,"fetched":1})):
            req={"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1","request_id":"test_source_akshare_001",
                 "operation":"EXECUTE","symbol":"001286.SZ","data_type":"historical_quotes",
                 "start_date":"2025-09-01","end_date":"2025-09-30","source":"AUTO"}
            receipt=process(req,d)
            raw=json.loads((Path(d)/"RAW_RESPONSE.json").read_text())
            self.assertEqual(receipt["provider"],"akshare")
            self.assertEqual(raw["source"],"akshare")
    def test_akshare_lot_volume_normalized_to_shares(self):
        import sys
        from ops.public_gateway_quotes import _akshare
        class FakeFrame:
            def to_dict(self,orient):
                return [{"日期":"2025-09-01","开盘":10,"最高":11,"最低":9,
                         "收盘":10.5,"成交量":12,"成交额":10000}]
        class FakeAKShare:
            def stock_zh_a_hist(self,**kwargs):return FakeFrame()
        with patch.dict(sys.modules,{"akshare":FakeAKShare()}):
            rows=_akshare(REQUEST)
        self.assertEqual(rows[0]["volume"],"1200")
    def test_failed_source_receipt_must_not_claim_provider(self):
        from ops.public_data_gateway import process
        with tempfile.TemporaryDirectory() as d, patch("ops.public_data_gateway.execute",
             return_value=([],{"required":1,"fetched":0,
                               "gap_reason":"ALL_ALLOWED_QUOTE_SOURCES_UNAVAILABLE",
                               "source_attempts":[{"source":"akshare","outcome":"FAILED"}]})):
            req={"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1","request_id":"test_no_fake_provider_001",
                 "operation":"EXECUTE","symbol":"001286.SZ","data_type":"historical_quotes",
                 "start_date":"2025-09-01","end_date":"2025-09-30","source":"akshare"}
            outcome=process(req,d)
            self.assertEqual(outcome["status"],"GAP")
            self.assertIsNone(outcome["provider"])
            self.assertEqual(outcome["source_details"]["source_attempts"][0]["source"],"akshare")
    def test_primary_success(self):
        with patch("ops.public_gateway_quotes._baostock",return_value=[dict(ROW)]):
            rows,details=fetch_quotes(REQUEST)
        self.assertEqual(details["source_used"],"baostock")
        self.assertEqual(len(rows),1)
    def test_fallback_when_primary_fails(self):
        with patch("ops.public_gateway_quotes._baostock",side_effect=RuntimeError("HTTP_429")),\
             patch("ops.public_gateway_quotes._akshare",return_value=[dict(ROW)]):
            rows,details=fetch_quotes(REQUEST)
        self.assertEqual(details["source_used"],"akshare")
        self.assertEqual(details["source_attempts"][0]["source"],"baostock")
    def test_hk_never_calls_baostock(self):
        hk={**REQUEST,"symbol":"9926.HK"}
        with patch("ops.public_gateway_quotes._baostock") as primary,\
             patch("ops.public_gateway_quotes._akshare",return_value=[
                 {**ROW,"code":"9926"}]):
            rows,details=fetch_quotes(hk)
        primary.assert_not_called()
        self.assertEqual(details["quote_currency"],"HKD")
        self.assertEqual(details["normalized_volume_unit"],"AS_RETURNED")
        self.assertEqual(len(rows),1)
    def test_hk_yahoo_missing_turnover_is_partial(self):
        hk={**REQUEST,"symbol":"9926.HK"}
        with patch("ops.public_gateway_quotes._akshare",side_effect=RuntimeError("blocked")),\
             patch("ops.public_gateway_quotes._yahoo_chart",return_value=[
                 {**ROW,"code":"9926","amount":None}]):
            rows,details=fetch_quotes(hk)
        self.assertEqual(details["source_used"],"yahoo_chart")
        self.assertEqual(details["quote_currency"],"HKD")
        self.assertEqual(details["required"],2)
        self.assertEqual(details["fetched"],1)
        self.assertIsNone(rows[0]["amount"])
        self.assertIn("amount",details["missing_fields"])
    def test_hk_baostock_explicitly_rejected(self):
        with self.assertRaisesRegex(ValueError,"NON_A_SHARE_BAOSTOCK_NOT_SUPPORTED"):
            fetch_quotes({**REQUEST,"symbol":"9926.HK","source":"baostock"})
    def test_reject_wrong_symbol(self):
        with patch("ops.public_gateway_quotes._baostock",return_value=[{**ROW,"code":"999999"}]),\
             patch("ops.public_gateway_quotes._akshare",return_value=[]):
            rows,details=fetch_quotes(REQUEST)
        self.assertEqual(rows,[])
        self.assertEqual(details["gap_reason"],"ALL_ALLOWED_QUOTE_SOURCES_UNAVAILABLE")
    def test_explicit_source_no_fallback(self):
        with patch("ops.public_gateway_quotes._baostock",side_effect=RuntimeError("blocked")),\
             patch("ops.public_gateway_quotes._akshare") as alternate:
            rows,details=fetch_quotes({**REQUEST,"source":"baostock"})
        self.assertEqual(rows,[])
        alternate.assert_not_called()
    def test_reject_duplicate_days(self):
        with patch("ops.public_gateway_quotes._baostock",return_value=[dict(ROW),dict(ROW)]),\
             patch("ops.public_gateway_quotes._akshare",return_value=[]):
            rows,details=fetch_quotes(REQUEST)
        self.assertEqual(rows,[])

if __name__=="__main__":
    unittest.main()
