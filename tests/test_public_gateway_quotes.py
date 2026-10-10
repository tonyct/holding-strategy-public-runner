"""Offline test for historic quote source failover and strict row scopes."""
import unittest
from unittest.mock import patch
from ops.public_gateway_quotes import fetch_quotes

REQUEST={"symbol":"001286.SZ","start_date":"2025-09-01","end_date":"2025-09-30","source":"AUTO"}
ROW={"date":"2025-09-01","code":"001286","open":"10","high":"11","low":"9",
     "close":"10.5","volume":"1000","amount":"10000","adjustflag":"3"}

class QuoteRouterTests(unittest.TestCase):
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
