"""PUBLIC extended gateway hermetic contracts. No network requests."""
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ops import public_gateway_extended as ext
from ops.public_data_gateway import process, validate

REQUEST={"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1","request_id":"fixture_fin_001286","operation":"EXECUTE",
         "symbol":"001286.SZ","data_type":"financial_statements","start_date":"2025-01-01",
         "end_date":"2025-12-31","source":"AUTO"}

class ExtendedTests(unittest.TestCase):
    def test_financial_quarter_end_required(self):
        with self.assertRaises(ValueError):
            validate({**REQUEST,"end_date":"2025-11-15"})
    def test_announcement_index_preserves_official_source(self):
        with patch.object(ext,"_index",return_value=([{
            "title":"2026年半年度报告","url":"https://www.cninfo.com.cn/new/disclosure/detail",
            "announced_at":"2026-08-20","announcement_id":"1234567890"}],1)):
            rows, meta=ext.announcement_index({**REQUEST,"data_type":"announcement_index"})
        self.assertEqual(meta["source_used"],"DIRECT_CNINFO")
        self.assertEqual(rows[0]["source_used"],"DIRECT_CNINFO")
    def test_empty_announcement_cannot_claim_complete(self):
        with patch.object(ext,"_index",return_value=([],0)):
            rows, meta=ext.announcement_index({**REQUEST,"data_type":"announcement_index"})
        self.assertEqual(rows,[])
        self.assertEqual(meta["gap_reason"],"EMPTY_DISCLOSURE_WINDOW_UNCONFIRMED")
    def test_official_pdf_limit(self):
        with self.assertRaises(ValueError):
            validate({**REQUEST,"data_type":"official_filings","start_date":"2025-01-01"})
    def test_target_year_rejects_wrong_official_report(self):
        rows=[{"title":"2026年第一季度报告","announced_at":"2026-04-20",
               "announcement_id":"1234567890"}]
        with patch.object(ext,"_index",return_value=(rows,1)):
            found,meta=ext.official_filings({**REQUEST,"data_type":"official_filings",
                "start_date":"2026-04-01","end_date":"2026-04-30",
                "report_period_end":"2025-12-31"})
        self.assertEqual(found,[])
        self.assertEqual(meta["gap_reason"],"TARGET_REPORT_NOT_FOUND_IN_WINDOW")
    def test_financial_partial_receipt(self):
        with tempfile.TemporaryDirectory() as d, patch("ops.public_data_gateway.execute",
             return_value=([{"statement":"balance","data":{"source":"AKSHARE_SINA"}}],
                           {"required":3,"fetched":1,"missing":["income","cashflow"]})):
            result=process(REQUEST,d)
        self.assertEqual(result["status"],"PARTIAL")
        self.assertEqual(result["row_count"],1)
        self.assertFalse(result["economic_verified"])
    def test_pdf_original_sha(self):
        pdf=b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF"
        class Response:
            def raise_for_status(self):return None
            def iter_content(self,n):return iter([pdf])
        class Session:
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def get(self,*a,**kw):return Response()
        index=[{"title":"2026年半年度报告","announced_at":"2026-08-20",
                "announcement_id":"1234567890"}]
        with patch.object(ext,"_index",return_value=(index,1)), patch("requests.Session",Session):
            rows,meta=ext.official_filings({**REQUEST,"data_type":"official_filings",
                                           "start_date":"2026-08-01","end_date":"2026-08-31"})
        self.assertEqual(meta["fetched"],1)
        self.assertEqual(hashlib.sha256(base64.b64decode(rows[0]["pdf_base64"])).hexdigest(),
                         rows[0]["document_sha256"])
    def test_private_fields_rejected(self):
        with self.assertRaises(ValueError):
            validate({**REQUEST,"holdings":["001286.SZ"]})

if __name__=="__main__":
    unittest.main()
