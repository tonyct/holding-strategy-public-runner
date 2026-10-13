"""Immutable PUBLIC-only original issuer announcement bytes by exact CNINFO ID."""
import argparse
import base64
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from pypdf import PdfReader

def sha(b): return hashlib.sha256(b).hexdigest()

def archive(request_path, response_path, receipt_path, *, root="public_originals"):
    q=json.loads(Path(request_path).read_text(encoding="utf-8"))
    r=json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if r.get("status")=="GAP":
        return {"status":"NO_ORIGINAL_DELIVERED","archived":False}
    raw=Path(response_path).read_bytes()
    body=json.loads(raw)
    if (q.get("schema")!="PUBLIC_DATA_GATEWAY_REQUEST/v1"
        or q.get("data_type")!="official_announcement_pdf"
        or q.get("operation")!="EXECUTE"
        or not re.fullmatch(r"\d{6}\.(?:SH|SZ)",str(q.get("symbol")))
        or not re.fullmatch(r"\d{10}",str(q.get("announcement_id")))
        or r.get("schema")!="PUBLIC_DATA_GATEWAY_RECEIPT/v1"
        or r.get("status")!="DELIVERED"
        or r.get("request_id")!=q.get("request_id")
        or r.get("symbol")!=q.get("symbol")
        or r.get("row_count")!=1
        or sha(raw)!=r.get("response_sha256")
        or body.get("request")!=q
        or not isinstance(body.get("rows"),list) or len(body["rows"])!=1):
        raise ValueError("PUBLIC_ANNOUNCEMENT_ARCHIVE_SCOPE_MISMATCH")
    row=body["rows"][0]
    stamp=str(row.get("announced_at",""))
    aid=q["announcement_id"]
    url=f"https://static.cninfo.com.cn/finalpage/{stamp}/{aid}.PDF"
    if (not re.fullmatch(r"20\d\d-\d\d-\d\d",stamp)
        or row.get("announcement_id")!=aid
        or row.get("source_url")!=url
        or row.get("source")!="CNINFO_OFFICIAL_PDF"
        or row.get("verification_state")!="ORIGINAL_BYTES_CAPTURED_CONTENT_NOT_AUDITED"):
        raise ValueError("PUBLIC_ANNOUNCEMENT_SOURCE_NOT_OFFICIAL")
    b64=row.get("pdf_base64")
    if not isinstance(b64,str) or len(b64)>12000000:
        raise ValueError("PUBLIC_ANNOUNCEMENT_B64_LIMIT")
    pdf=base64.b64decode(b64,validate=True)
    digest=sha(pdf)
    if (len(pdf)>8*1024*1024 or len(pdf)<256
        or digest!=row.get("document_sha256")
        or len(pdf)!=row.get("byte_count")
        or not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-8192:]):
        raise ValueError("PUBLIC_ANNOUNCEMENT_BYTES_INVALID")
    reader=PdfReader(io.BytesIO(pdf),strict=True)
    cover="".join((p.extract_text() or "") for p in reader.pages[:min(2,len(reader.pages))])
    if q["symbol"].split(".")[0] not in cover:
        raise ValueError("PUBLIC_ANNOUNCEMENT_ISSUER_NOT_CONFIRMED")
    folder=Path(root)/q["symbol"]/"announcements"/stamp
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(digest+".pdf")
    trans=folder/(digest+".b64")
    manifest=folder/(digest+".json")
    meta={"schema":"PUBLIC_ANNOUNCEMENT_SOURCE_ARCHIVE/v1",
          "symbol":q["symbol"],"announcement_id":aid,
          "announced_at":stamp,"source_url":url,"title":row.get("title"),
          "sha256":digest,"git_path":path.as_posix(),"size_bytes":len(pdf),
          "pdf_pages":len(reader.pages),"first_request_id":q["request_id"],
          "economic_approval":False,"formal_l3_pass":False}
    transport=(base64.b64encode(pdf).decode("ascii")+"\n").encode("ascii")
    manifest_bytes=(json.dumps(meta,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    wrote=not path.exists()
    for f,bytes_expected in ((path,pdf),(trans,transport)):
        if f.exists():
            if f.read_bytes()!=bytes_expected: raise ValueError("PUBLIC_ANNOUNCEMENT_ARCHIVE_IMMUTABILITY_CONFLICT")
        else: f.write_bytes(bytes_expected)
    if manifest.exists():
        old=json.loads(manifest.read_text(encoding="utf-8"))
        for field,value in meta.items():
            if field!="first_request_id" and old.get(field)!=value:
                raise ValueError("PUBLIC_ANNOUNCEMENT_MANIFEST_CONFLICT")
        meta=old
    else:
        manifest.write_bytes(manifest_bytes)
    return {"status":"PUBLIC_ANNOUNCEMENT_ORIGINAL_ARCHIVED","archived":wrote,
            "transfer_path":trans.as_posix(),**meta}

def main():
    p=argparse.ArgumentParser()
    for name in ("request","response","receipt","root"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    print(json.dumps(archive(a.request,a.response,a.receipt,root=a.root),ensure_ascii=False))

if __name__=="__main__":main()
