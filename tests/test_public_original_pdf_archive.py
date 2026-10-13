"""Content-addressed PUBLIC original filing store, issuer and tamper guard tests."""
import base64
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from reportlab.pdfgen import canvas
from ops.public_original_pdf_archive import archive

REQ = {"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1",
       "request_id":"PUBLIC_TEST_600499", "operation":"EXECUTE",
       "symbol":"600499.SH","data_type":"official_filings",
       "start_date":"2026-03-20","end_date":"2026-04-05",
       "report_period_end":"2025-12-31","source":"AUTO"}
URL = "https://static.cninfo.com.cn/finalpage/2026-03-28/1225046387.PDF"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def input_files(tmp, *, bad_pdf_hash=False, wrong_source=False, gap=False):
    f=Path(tmp)
    request=f/"request.json"
    response=f/"raw.json"
    receipt=f/"receipt.json"
    request.write_text(json.dumps(REQ))
    if gap:
        receipt.write_text(json.dumps({"status":"GAP"}))
        return request,response,receipt
    buf=io.BytesIO()
    sheet=canvas.Canvas(buf)
    sheet.drawString(36,700,"600499 2025 Annual Report")
    sheet.save()
    pdf=buf.getvalue()
    row={"source_url":"https://notofficial.example.org/annual.pdf" if wrong_source else URL,
         "source":"CNINFO_OFFICIAL_PDF","requested_report_period_end":"2025-12-31",
         "verification_state":"ORIGINAL_BYTES_CAPTURED_CONTENT_NOT_AUDITED",
         "pdf_base64":base64.b64encode(pdf).decode(),
         "document_sha256":"0"*64 if bad_pdf_hash else sha(pdf),
         "byte_count":len(pdf),"title":"600499 2025"}
    raw=json.dumps({"request":REQ,"source":"CNINFO_OFFICIAL_PDF","rows":[row]},ensure_ascii=False).encode()
    response.write_bytes(raw)
    receipt.write_text(json.dumps({"schema":"PUBLIC_DATA_GATEWAY_RECEIPT/v1",
       "status":"DELIVERED","symbol":"600499.SH",
       "request_id":REQ["request_id"],"response_sha256":sha(raw)}))
    return request,response,receipt


class OriginalArchiveTests(unittest.TestCase):
    def call(self, root, **kwargs):
        a,b,c=input_files(root,**kwargs)
        return archive(a,b,c,root=Path(root)/"public_originals")
    def test_bytes_persist_as_git_content_addressed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            x=self.call(tmp)
            self.assertTrue(x["archived"])
            target=Path(x["relative_path"])
            self.assertTrue(target.is_file())
            self.assertEqual(sha(target.read_bytes()),x["sha256"])
            self.assertTrue(target.with_suffix(".json").exists())
            y=archive(Path(tmp)/"request.json",Path(tmp)/"raw.json",
                      Path(tmp)/"receipt.json",root=Path(tmp)/"public_originals")
            self.assertFalse(y["archived"])
            self.assertEqual(y["sha256"],x["sha256"])
    def test_new_request_id_same_pdf_keeps_original_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=self.call(tmp)
            base=Path(tmp)
            req=json.loads((base/"request.json").read_text())
            req["request_id"]="PUBLIC_TEST_600499_RETRY"
            (base/"request.json").write_text(json.dumps(req))
            response=json.loads((base/"raw.json").read_text())
            response["request"]=req
            raw=json.dumps(response,ensure_ascii=False).encode()
            (base/"raw.json").write_bytes(raw)
            receipt=json.loads((base/"receipt.json").read_text())
            receipt["request_id"]=req["request_id"]
            receipt["response_sha256"]=sha(raw)
            (base/"receipt.json").write_text(json.dumps(receipt))
            again=archive(base/"request.json",base/"raw.json",
                base/"receipt.json",root=base/"public_originals")
            self.assertFalse(again["archived"])
            self.assertEqual(again["request_id"],"PUBLIC_TEST_600499")
            self.assertEqual(first["sha256"],again["sha256"])
    def test_base64_transport_roundtrip_and_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=self.call(tmp)
            pdf=Path(first["relative_path"]).read_bytes()
            path=Path(first["base64_transport_path"])
            self.assertEqual(base64.b64decode(path.read_bytes(),validate=False),pdf)
            path.write_text("tampered")
            with self.assertRaisesRegex(ValueError,"BASE64_IMMUTABLE_CONFLICT"):
                archive(Path(tmp)/"request.json",Path(tmp)/"raw.json",
                        Path(tmp)/"receipt.json",root=Path(tmp)/"public_originals")
    def test_wrong_pdf_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,"BYTE_HASH_MISMATCH"):
                self.call(tmp,bad_pdf_hash=True)
    def test_nonofficial_url_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,"UNTRUSTED_DOCUMENT"):
                self.call(tmp,wrong_source=True)
    def test_provider_gap_does_not_create_fake_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=self.call(tmp,gap=True)
            self.assertEqual(result["status"],"NO_ORIGINAL_DELIVERED")
            self.assertFalse(list(Path(tmp).rglob("*.pdf")))
    def test_existing_content_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=self.call(tmp)
            Path(result["relative_path"]).write_bytes(b"tamper")
            with self.assertRaisesRegex(ValueError,"IMMUTABLE_CONFLICT"):
                archive(Path(tmp)/"request.json",Path(tmp)/"raw.json",
                        Path(tmp)/"receipt.json",root=Path(tmp)/"public_originals")


if __name__=="__main__":
    unittest.main()
