"""New US quote support is intentionally bounded, USD-checked and unverified."""
import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from ops.public_data_gateway import validate
from ops.public_gateway_quotes import fetch_quotes

REQ={"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1","operation":"EXECUTE",
     "request_id":"public_us_quote_001","symbol":"AAPL.US",
     "data_type":"historical_quotes","source":"AUTO",
     "start_date":"2026-10-01","end_date":"2026-10-09"}

class USQuoteBoundaryTests(unittest.TestCase):
    def test_us_quote_contract_and_source_restrictions(self):
        validate(REQ)
        validate({**REQ,"source":"yahoo_chart"})
        with self.assertRaisesRegex(ValueError,"US_ONLY_YAHOO"):
            validate({**REQ,"source":"akshare"})
        with self.assertRaisesRegex(ValueError,"MARKET_NOT_SUPPORTED"):
            validate({**REQ,"symbol":"AAPL.US","data_type":"financial_statements"})
        with self.assertRaisesRegex(ValueError,"INVALID_SYMBOL"):
            validate({**REQ,"symbol":"../../secrets.US"})
    def test_yahoo_us_source_currency_symbol_and_partial_turnover(self):
        def fake_get(url,**kwargs):
            self.assertIn("/AAPL",url)
            from zoneinfo import ZoneInfo
            epoch=int(dt.datetime(2026,10,8,16,tzinfo=ZoneInfo("America/New_York")).timestamp())
            response={"chart":{"result":[{"meta":{"symbol":"AAPL","currency":"USD"},
                "timestamp":[epoch],"indicators":{"quote":[{
                    "open":[250.0],"high":[252.0],"low":[248.0],
                    "close":[251.0],"volume":[100000]}]}}]}}
            return SimpleNamespace(status_code=200,content=b"ok",json=lambda:response)
        with patch("requests.get",side_effect=fake_get):
            rows,meta=fetch_quotes(REQ)
        self.assertEqual(meta["quote_currency"],"USD")
        self.assertEqual(meta["source_used"],"yahoo_chart")
        self.assertEqual(rows[0]["close"],"251.0")
        self.assertIn("amount",meta["missing_fields"])
    def test_reject_wrong_us_currency(self):
        def fake_get(url,**kwargs):
            return SimpleNamespace(status_code=200,content=b"ok",json=lambda:{
                "chart":{"result":[{"meta":{"symbol":"AAPL","currency":"HKD"},
                         "timestamp":[],"indicators":{"quote":[{}]}}]}})
        with patch("requests.get",side_effect=fake_get):
            rows,meta=fetch_quotes(REQ)
        self.assertEqual(rows,[])
        self.assertEqual(meta["fetched"],0)

if __name__=="__main__":
    unittest.main()
