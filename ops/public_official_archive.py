"""Immutable PUBLIC-only official PDF archive after a verified gateway response.

Only public issuer PDFs. Never accept private case/run IDs, portfolios or models.
Git retention is independent of 30-day Actions artifact expiry. Not L2/L3 PASS.
"""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = "archive/official_filings"
REQ_SCHEMA = "PUBLIC_DATA_GATEWAY_REQUEST/v1"
REC_SCHEMA = "PUBLIC_DATA_GATEWAY_RECEIPT/v1"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def archive(request_file, result_dir, archive_root=ROOT):
    request=json.loads(Path(request_file).read_text(encoding="utf-8"))
    result=Path(result_dir)
    receipt=json.loads((result/"PUBLIC_GATEWAY_RECEIPT.json").read_text(encoding="utf-8"))
    if (request.get("schema")!=REQ_SCHEMA or request.get("operation")!="EXECUTE"
            or request.get("data_type")!="official_filings"
            or receipt.get("schema")!=REC_SCHEMA
            or receipt.get("request_id")!=request.get("request_id")
            or receipt.get("symbol")!=request.get("symbol")
            or receipt.get("data_type")!=request.get("data_type")):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_REQUEST_RECEIPT_MISMATCH")
    if receipt.get("status")=="GAP":
        return {"status":"GAP_NOT_ARCHIVED","request_id":request["request_id"]}
    if receipt.get("status")!="DELIVERED" or receipt.get("row_count")!=1:
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_NOT_EXACTLY_ONE_ORIGINAL")
    raw_bytes=(result/"RAW_RESPONSE.json").read_bytes()
    if sha(raw_bytes)!=receipt.get("response_sha256"):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_RAW_DIGEST_MISMATCH")
    response=json.loads(raw_bytes)
    if (response.get("request")!=request or not isinstance(response.get("rows"),list)
            or len(response["rows"])!=1):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_RESPONSE_MISMATCH")
    row=response["rows"][0]
    p=urlparse(row.get("source_url",""))
    if (p.scheme!="https" or p.hostname!="static.cninfo.com.cn"
            or not re.fullmatch(r"/finalpage/20\d{2}-\d{2}-\d{2}/\d{10}\.PDF",p.path)
            or row.get("source")!="CNINFO_OFFICIAL_PDF"
            or row.get("requested_report_period_end")!=request.get("report_period_end")
            or row.get("verification_state")!="ORIGINAL_BYTES_CAPTURED_CONTENT_NOT_AUDITED"):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_UNTRUSTED_ORIGINAL")
    encoded=row.get("pdf_base64")
    if not isinstance(encoded,str) or len(encoded)>12_000_000:
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_B64_LIMIT")
    pdf=base64.b64decode(encoded,validate=True)
    digest=sha(pdf)
    if (len(pdf)>8*1024*1024 or len(pdf)<256
            or len(pdf)!=row.get("byte_count")
            or digest!=row.get("document_sha256")
            or not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-8192:]):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_PDF_INVALID")
    symbol=request.get("symbol","")
    period=request.get("report_period_end","")
    if (not re.fullmatch(r"\d{6}\.(?:SH|SZ)",symbol)
            or not re.fullmatch(r"20\d\d-(?:03-31|06-30|09-30|12-31)",period)):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_INVALID_TARGET")
    folder=Path(archive_root)/symbol/period
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(digest+".pdf")
    manifest_path=folder/(digest+".json")
    manifest={
        "schema":"PUBLIC_OFFICIAL_PDF_GIT_ARCHIVE/v1",
        "symbol":symbol,"report_period_end":period,
        "source_url":row["source_url"],"source":"CNINFO_OFFICIAL_PDF",
        "title":row.get("title"),"announcement_id":row.get("announcement_id"),
        "byte_count":len(pdf),"document_sha256":digest,
        "request_id":request["request_id"],
        "verification_state":"ORIGINAL_SOURCE_TRANSPORT_BYTES_VERIFIED_NOT_ACCOUNTING_OR_L3",
        "independent_reviewer_approved":False,"formal_l3_pass":False}
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
    for file,content in ((path,pdf),(manifest_path,manifest_bytes)):
        if file.exists():
            if file.read_bytes()!=content:
                raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_IMMUTABILITY_CONFLICT")
        else:
            file.write_bytes(content)
    return {"status":"ORIGINAL_PDF_READY_TO_COMMIT","path":str(path),
            "manifest_path":str(manifest_path),"document_sha256":digest}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--request",required=True)
    p.add_argument("--result-dir",required=True)
    p.add_argument("--archive-root",default=ROOT)
    a=p.parse_args()
    print(json.dumps(archive(a.request,a.result_dir,a.archive_root),ensure_ascii=False))

if __name__=="__main__":
    main()
