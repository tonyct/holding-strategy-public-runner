"""Synthetic public-only binary transport tests, not an issuer or economic review."""
import base64
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from reportlab.pdfgen import canvas
from ops.public_data_gateway import process, validate
from ops.public_announcement_original_archive import archive
from ops.public_sseinfo_original import fetch, NoRedirect, source_location, MAX_BYTES

REQUEST=dict(schema="PUBLIC_DATA_GATEWAY_REQUEST/v1", request_id="SSEINFO_SYNTHETIC_TEST",
             operation="EXECUTE", symbol="600499.SH", data_type="official_announcement_pdf",
             source="SSEINFO", start_date="2026-09-30", end_date="2026-09-30",
             announcement_id="2026093010410331063380066")


def pdf_bytes(symbol="600499"):
    target=io.BytesIO(); pdf=canvas.Canvas(target)
    pdf.drawString(40,700,symbol+" synthetic public attachment fixture")
    pdf.save(); return target.getvalue()


class Response(io.BytesIO):
    status=200


class AttachmentTests(unittest.TestCase):
    def test_exact_public_filename_and_date_no_free_form_url(self):
        validate(REQUEST)
        url, stamp=source_location(REQUEST)
        self.assertEqual(url,"https://sns.sseinfo.com/resources/images/upload/202609/2026093010410331063380066.pdf")
        self.assertEqual(stamp,"2026-09-30")
        for changes in ({"symbol":"600499.SZ"}, {"announcement_id":"20260930/../../secret"},
                        {"start_date":"2026-10-01"}, {"announcement_id":"20261300123456789012"},
                        {"source_url":"https://private.invalid/secret"}, {"portfolio":[]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate(dict(REQUEST,**changes))

    def test_real_gateway_to_immutable_archive_with_exact_bytes(self):
        raw=pdf_bytes()
        with tempfile.TemporaryDirectory() as folder, patch(
                "ops.public_sseinfo_original.build_opener") as opener:
            opener.return_value.open.return_value=Response(raw)
            result=process(REQUEST,folder)
            self.assertEqual(result["status"],"DELIVERED")
            self.assertFalse(result["economic_verified"])
            root=Path(folder); request=root/"request.json"
            request.write_text(json.dumps(REQUEST))
            saved=archive(request,root/"RAW_RESPONSE.json",root/"PUBLIC_GATEWAY_RECEIPT.json",root=root/"originals")
            self.assertEqual(Path(saved["git_path"]).read_bytes(),raw)
            self.assertEqual(saved["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertFalse(saved["formal_l3_pass"])
            # A provider cannot swap the original's host while retaining its SHA.
            response=json.loads((root/"RAW_RESPONSE.json").read_text())
            response["rows"][0]["source_url"]="https://other.invalid/file.pdf"
            altered=json.dumps(response).encode();(root/"RAW_RESPONSE.json").write_bytes(altered)
            result["response_sha256"]=hashlib.sha256(altered).hexdigest()
            (root/"PUBLIC_GATEWAY_RECEIPT.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,"SOURCE_NOT_OFFICIAL"):
                archive(request,root/"RAW_RESPONSE.json",root/"PUBLIC_GATEWAY_RECEIPT.json",root=root/"originals")

    def test_wrong_issuer_html_and_oversized_bytes_never_delivered(self):
        for raw in (pdf_bytes("000001"),b"<html>error</html>",b"X"*(MAX_BYTES+1)):
            with self.subTest(size=len(raw)), patch("ops.public_sseinfo_original.build_opener") as opener:
                opener.return_value.open.return_value=Response(raw)
                rows, meta=fetch(REQUEST)
                self.assertEqual(rows,[])
                self.assertEqual(meta["fetched"],0)
                self.assertEqual(meta["gap_reason"],"SSEINFO_ORIGINAL_ATTACHMENT_FETCH_FAILED")

    def test_redirect_cannot_fetch_an_unapproved_host(self):
        with self.assertRaisesRegex(ValueError,"REDIRECT_REFUSED"):
            NoRedirect().redirect_request(None,None,302,"redirect",{},"https://other.invalid/")


if __name__=="__main__":unittest.main()
