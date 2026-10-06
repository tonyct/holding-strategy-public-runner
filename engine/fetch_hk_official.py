"""HKEX issuer disclosure index via public HKEXnews issuer search results.

This utility records only user-supplied original HKEX URLs, validates source host,
and downloads published PDFs without pretending an index is an audited report.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
import requests
from universe import load_universe

ALLOWED = {"www1.hkexnews.hk", "www.hkexnews.hk"}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",default="config/hk_official_filings.json")
    ap.add_argument("--universe-file",default="config/research_universe.json")
    ap.add_argument("--output",default="output/hk_official_filings")
    args=ap.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    universe=load_universe(args.universe_file)
    try: manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError,ValueError): manifest={}
    reports=manifest.get("reports",[])
    if manifest.get("schema")!="E36_HK_FILING_LOCATORS/v1" or manifest.get("period")!="2026-06-30" or not isinstance(reports,list):
        raise ValueError("INVALID_HK_MANIFEST_OR_PERIOD")
    indexed={x["symbol"]:x for x in reports if isinstance(x,dict) and "symbol" in x}
    if len(indexed)!=len(reports) or any(s not in universe["hk_shares"] for s in indexed):
        raise ValueError("DUPLICATE_OR_UNEXPECTED_HK_SYMBOL")
    rows=[]
    for symbol in universe["hk_shares"]:
        record={"symbol":symbol,"status":"ORIGINAL_HK_FILING_LOCATOR_MISSING","downloaded":False}
        item=indexed.get(symbol)
        if item:
            urls=[item.get("url","")]+item.get("alternate_urls",[])
            errors=[]
            for url in dict.fromkeys(urls):
                parsed=urlparse(url)
                if parsed.scheme!="https" or parsed.hostname not in ALLOWED or not parsed.path.lower().endswith(".pdf"):
                    errors.append({"url":url,"error":"INVALID_HKEX_URL"})
                    continue
                try:
                    data=None
                    for attempt in range(3):
                        try:
                            with requests.get(url,timeout=(10,60),allow_redirects=False,stream=True) as res:
                                if res.status_code in (408,429,500,502,503,504) and attempt<2:
                                    import time
                                    time.sleep(2**attempt)
                                    continue
                                res.raise_for_status()
                                chunks=bytearray()
                                for chunk in res.iter_content(chunk_size=65536):
                                    chunks.extend(chunk)
                                    if len(chunks)>30*1024*1024:
                                        raise ValueError("HK_PDF_SIZE_LIMIT_EXCEEDED")
                                data=bytes(chunks)
                            break
                        except (requests.ConnectionError,requests.Timeout):
                            if attempt==2: raise
                            import time
                            time.sleep(2**attempt)
                    if data is None:
                        raise ValueError("HK_PDF_EMPTY_RESPONSE")
                    if len(data)>30*1024*1024 or not data.startswith(b"%PDF-") or b"%%EOF" not in data[-4096:]:
                        raise ValueError("INVALID_OR_TOO_LARGE_PDF")
                    import pymupdf
                    with pymupdf.open(stream=data,filetype="pdf") as document:
                        if document.needs_pass or document.page_count<15:
                            raise ValueError("UNREADABLE_HK_PDF")
                        front=" ".join(document[i].get_text() for i in range(min(12,document.page_count))).lower()
                        all_text=" ".join(document[i].get_text() for i in range(document.page_count)).lower()
                    if item.get("doc_type")!="FULL_INTERIM_REPORT":
                        raise ValueError("HK_REPORT_IS_NOT_FULL_INTERIM_REPORT")
                    if "2026" not in front or not any(t in front for t in ("interim report","中期報告","中期报告")):
                        raise ValueError("HK_REPORT_PERIOD_OR_TYPE_UNVERIFIED")
                    import re
                    issuer=re.sub(r"[^a-z0-9]+","",item.get("issuer","").lower())
                    normalized_front=re.sub(r"[^a-z0-9]+","",front)
                    if not issuer or issuer not in normalized_front:
                        raise ValueError("HK_ISSUER_IDENTITY_UNVERIFIED")
                    import re
                    normalized_text=re.sub(r"\s+","",all_text)
                    sections=(("financialposition","資產負債表","资产负债表"),
                              ("profitorloss","損益表","利润表","全面收益表"),
                              ("cashflows","現金流量表","现金流量表"))
                    if not all(any(term in normalized_text for term in group) for group in sections):
                        raise ValueError("HK_THREE_STATEMENT_SECTIONS_NOT_FOUND")
                    sha=hashlib.sha256(data).hexdigest()
                    filename=symbol.replace(".","_")+"_"+sha[:16]+".pdf"
                    (out/filename).write_bytes(data)
                    if hashlib.sha256((out/filename).read_bytes()).hexdigest()!=sha:
                        raise ValueError("HK_PDF_PERSISTED_HASH_MISMATCH")
                    record.update(status="HKEX_PDF_IDENTITY_PERIOD_VERIFIED_NOT_NOTES_AUDITED",
                                  source_url=url,sha256=sha,filename=filename,downloaded=True,
                                  failed_candidates=errors)
                    break
                except (requests.RequestException,ValueError) as exc:
                    errors.append({"url":url,"error":type(exc).__name__+":"+str(exc)[:130]})
            if not record["downloaded"]:
                record.update(status="HKEX_PDF_FETCH_FAILED",failed_candidates=errors)
        rows.append(record)
    receipt={"schema":"E36_HK_PRIMARY_FILING/v1","universe_sha256":universe["universe_sha256"],
             "generated_utc":datetime.now(timezone.utc).isoformat(),"rows":rows,
             "verified_financial_statements":0,"notes_researched":False}
    (out/"HK_FILING_RECEIPT.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"downloaded":sum(x["downloaded"] for x in rows),"total":len(rows)}))
    return 0 if rows and all(x["downloaded"] for x in rows) else 1
if __name__=="__main__":
    raise SystemExit(main())
