"""SEC discovery is deterministic, filing-as-of and economically unapproved."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ops.public_data_gateway import process,validate
from ops.public_gateway_sec_facts import fetch_sec_companyfacts

REQUEST={"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1",
         "request_id":"public_sec_us_test_001","operation":"EXECUTE",
         "symbol":"AAPL.US","data_type":"sec_companyfacts",
         "start_date":"2025-10-09","end_date":"2026-10-09","source":"AUTO"}

def response(data):
    return SimpleNamespace(status_code=200,content=json.dumps(data).encode(),
                           json=lambda:data)

def get(url,**kw):
    if "company_tickers.json" in url:
        return response({"0":{"ticker":"AAPL","cik_str":320193}})
    return response({"cik":320193,"facts":{"us-gaap":{
        "Assets":{"units":{"USD":[
            {"filed":"2025-10-31","end":"2025-09-27",
             "accn":"0000320193-25-000079","form":"10-K","val":1000,"fy":2025,"fp":"FY"},
            {"filed":"2026-10-12","end":"2026-09-27",
             "accn":"0000320193-26-000099","form":"10-K","val":2000}
        ]}}}}})

class SECCompanyfactsTests(unittest.TestCase):
    def test_us_only_exact_provider(self):
        validate(REQUEST)
        validate({**REQUEST,"source":"sec_edgar"})
        with self.assertRaises(ValueError):
            validate({**REQUEST,"symbol":"001286.SZ"})
        with self.assertRaises(ValueError):
            validate({**REQUEST,"source":"akshare"})
    def test_no_future_filing_or_silent_issuer_approval(self):
        with patch.dict(os.environ,{"PUBLIC_SEC_USER_AGENT":"research-team contact@example.org"}):
            rows,details=fetch_sec_companyfacts(REQUEST,get=get)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["value"],"1000")
        self.assertEqual(rows[0]["filed_at"],"2025-10-31")
        self.assertFalse(details["economic_verified"])
        self.assertEqual(details["required"],2)
        self.assertEqual(details["fetched"],1)
    def test_missing_sec_contact_fails_to_gap(self):
        with patch.dict(os.environ,{"PUBLIC_SEC_USER_AGENT":""}):
            rows,meta=fetch_sec_companyfacts(REQUEST,get=get)
        self.assertEqual(rows,[])
        self.assertEqual(meta["fetched"],0)
    def test_public_receipt_is_partial_not_false_delivered(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "ops.public_data_gateway.execute",
            return_value=([{"metric":"total_assets","filed_at":"2025-10-31"}],
                          {"required":2,"fetched":1,
                           "source_used":"sec_edgar_companyfacts"})):
            outcome=process(REQUEST,root)
            self.assertEqual(outcome["status"],"PARTIAL")
            self.assertFalse(outcome["economic_verified"])
            self.assertTrue((Path(root)/"RAW_RESPONSE.json").exists())

if __name__=="__main__":
    unittest.main()
