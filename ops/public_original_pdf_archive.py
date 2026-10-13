"""Archive public original issuer PDF bytes, keyed by SHA256, from gateway output.

PUBLIC-only: never sees PRIVATE case, author models, source_run_id or accounts.
Existing content is immutable; tampered/malformed gateway output is rejected.
"""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("public_originals")
SHA = re.compile(r"[a-f0-9]{64}\Z")
SYMBOL = re.compile(r"[0-9]{6}\.(?:SH|SZ)\Z")
PERIOD = re.compile(r"20[0-9]{2}-(?:03-31|06-30|09-30|12-31)\Z")


def _sha(b): return hashlib.sha256(b).hexdigest()


def archive(request_path, response_path, receipt_path, *, root=ROOT):
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if receipt.get("status")=="GAP":
        return {"status":"NO_ORIGINAL_DELIVERED","archived":False}
    raw=Path(response_path).read_bytes()
    response=json.loads(raw)
    symbol=request.get("symbol")
    period=request.get("report_period_end")
    rows=response.get("rows")
    if (request.get("schema")!="PUBLIC_DATA_GATEWAY_REQUEST/v1"
            or request.get("data_type")!="official_filings"
            or request.get("operation")!="EXECUTE"
            or not SYMBOL.fullmatch(str(symbol))
            or not PERIOD.fullmatch(str(period))
            or response.get("request")!=request
            or receipt.get("schema")!="PUBLIC_DATA_GATEWAY_RECEIPT/v1"
            or receipt.get("status")!="DELIVERED"
            or receipt.get("request_id")!=request.get("request_id")
            or receipt.get("symbol")!=symbol
            or receipt.get("response_sha256")!=_sha(raw)
            or not isinstance(rows,list) or len(rows)!=1):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_REQUEST_RECEIPT_MISMATCH")
    row=rows[0]
    parsed=urlparse(row.get("source_url",""))
    host=(parsed.hostname or "").lower()
    if (parsed.scheme!="https"
            or not (host=="cninfo.com.cn" or host.endswith(".cninfo.com.cn"))
            or row.get("source")!="CNINFO_OFFICIAL_PDF"
            or row.get("requested_report_period_end")!=period
            or row.get("verification_state")!="ORIGINAL_BYTES_CAPTURED_CONTENT_NOT_AUDITED"):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_UNTRUSTED_DOCUMENT")
    try:
        pdf=base64.b64decode(row["pdf_base64"],validate=True)
    except (ValueError,KeyError) as err:
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_INVALID_BASE64") from err
    digest=_sha(pdf)
    if (len(pdf)>8*1024*1024 or len(pdf)<256
            or not pdf.startswith(b"%PDF-")
            or b"%%EOF" not in pdf[-8192:]
            or row.get("byte_count")!=len(pdf)
            or row.get("document_sha256")!=digest):
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_BYTE_HASH_MISMATCH")
    try:
        from pypdf import PdfReader
        import io
        reader=PdfReader(io.BytesIO(pdf),strict=True)
        cover="".join((reader.pages[i].extract_text() or "") for i in range(min(2,len(reader.pages))))
        cover=re.sub(r"\s+","",cover)
        if symbol.split(".")[0] not in cover or period[:4] not in cover:
            raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_ISSUER_PERIOD_MISMATCH")
        pages=len(reader.pages)
    except ValueError:raise
    except Exception as err:
        raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_PDF_PARSE_FAILED") from err
    path=Path(root)/symbol/period/(digest+".pdf")
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if _sha(path.read_bytes())!=digest:
            raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_IMMUTABLE_CONFLICT")
        wrote=False
    else:
        path.write_bytes(pdf)
        wrote=True
    manifest={
        "schema":"E36_PUBLIC_IMMUTABLE_ORIGINAL_PDF/v1",
        "symbol":symbol,"report_period_end":period,
        "source_url":row["source_url"],"title":row.get("title"),
        "request_id":request["request_id"],"sha256":digest,
        "size_bytes":len(pdf),"pdf_pages":pages,
        "relative_path":path.as_posix(),
        "source_scope":"PUBLIC_ISSUER_FILE_NOT_ECONOMIC_REVIEW",
        "independent_economic_reviewed":False,"formal_l3_pass":False}
    manifest_path=path.with_suffix(".json")
    serialized=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    if manifest_path.exists():
        retained=json.loads(manifest_path.read_text(encoding="utf-8"))
        # Repeated requests for the exact immutable issuer bytes are idempotent.
        # Keep the first dispatch provenance; never rewrite it on retry.
        for field in manifest:
            if field != "request_id" and retained.get(field) != manifest[field]:
                raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_MANIFEST_CONFLICT")
        manifest=retained
    else:
        manifest_path.write_bytes(serialized)
    # GitHub text-only connectors cannot read binary PDF blobs. Retain a
    # checksum-bound UTF-8 transport sidecar for PRIVATE original-byte CAS.
    # It is PUBLIC issuer data, not a valuation or review artifact.
    transport_path=path.with_suffix(".b64")
    transport=(base64.b64encode(pdf).decode("ascii")+"\n").encode("ascii")
    if transport_path.exists():
        if transport_path.read_bytes()!=transport:
            raise ValueError("PUBLIC_ORIGINAL_ARCHIVE_BASE64_IMMUTABLE_CONFLICT")
    else:
        transport_path.write_bytes(transport)
    return {"status":"PUBLIC_ORIGINAL_BYTES_STORED_LOCALLY_FOR_GIT_COMMIT",
            "archived":wrote,"base64_transport_path":transport_path.as_posix(),**manifest}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--request",required=True)
    parser.add_argument("--response",required=True)
    parser.add_argument("--receipt",required=True)
    parser.add_argument("--root",default=str(ROOT))
    args=parser.parse_args()
    result=archive(args.request,args.response,args.receipt,root=args.root)
    print(json.dumps(result,ensure_ascii=False))
    if result["status"]=="NO_ORIGINAL_DELIVERED":
        return 0  # legitimate provider GAP, artifact still records it
    return 0


if __name__=="__main__":
    raise SystemExit(main())
