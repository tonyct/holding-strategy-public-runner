"""Bounded PUBLIC research adapters built on existing PUBLIC collectors.

No account/portfolio/private research data is accepted. All returned data is
source-qualified, not economically verified or approved for investment.
"""
import base64
import hashlib
import re

CAPABILITIES = {
    "financial_statements": {
        "adapter": "akshare", "markets": ["SH", "SZ"],
        "source_options": ["AUTO"],
        "fields": ["income", "balance", "cashflow"],
        "note": "Exact quarter/FY period; three statement coverage can be partial; unit and scope must be reviewed"},
    "announcement_index": {
        "adapter": "cninfo", "markets": ["SH", "SZ"],
        "source_options": ["AUTO", "DIRECT_CNINFO"],
        "fields": ["title", "url", "announced_at", "announcement_id", "adjunct_url"],
        "note": "Official disclosure index, not a downloaded or authenticated issuer document"},
    "official_filings": {
        "adapter": "cninfo_official_pdf", "markets": ["SH", "SZ"],
        "source_options": ["AUTO"],
        "fields": ["document_sha256", "pdf_base64", "source_url", "title", "announced_at"],
        "note": "At most one bounded original PDF with header/trailer and byte SHA; not a verified accounting interpretation"},
}

def financial_statements(request):
    from engine.financial_adapter import FinancialAdapter
    period=request["end_date"]
    if not re.fullmatch(r"20[0-9]{2}-(03-31|06-30|09-30|12-31)",period):
        raise ValueError("FINANCIAL_PERIOD_MUST_BE_QUARTER_END")
    adapter=FinancialAdapter(retries=0)
    report=adapter.fetch_company(request["symbol"],period)
    results=[]
    for statement,record in report["statements"].items():
        if record.get("data") is not None:
            results.append({"statement":statement,"fetch_state":record.get("status"),
                            "source_used":record["data"].get("source"),
                            "data":record["data"],"attempts":record.get("attempts",[])})
    return results, {"required":3,"fetched":len(results),
                     "missing":[k for k,v in report["statements"].items() if v.get("data") is None],
                     "source_health":report.get("source_health",{}),
                     "upstream_status":report.get("status")}

def _index(request):
    from engine.direct_cninfo import query
    symbol=request["symbol"]
    rows,total=query(symbol[:6],request["start_date"].replace("-",""),
                     request["end_date"].replace("-",""),max_pages=3)
    if total > 90:
        raise ValueError("ANNOUNCEMENT_WINDOW_EXCEEDS_PAGE_CAP")
    return rows,total

def announcement_index(request):
    rows,total=_index(request)
    if not rows:
        return [],{"required":1,"fetched":0,"source_used":"DIRECT_CNINFO",
                  "upstream_total":total,"gap_reason":"EMPTY_DISCLOSURE_WINDOW_UNCONFIRMED"}
    return [{**x,"source_used":"DIRECT_CNINFO"} for x in rows[:90]],{
        "required":1,"fetched":1,"source_used":"DIRECT_CNINFO","upstream_total":total}

def official_filings(request):
    from datetime import date
    import requests
    start=date.fromisoformat(request["start_date"])
    end=date.fromisoformat(request["end_date"])
    if (end-start).days>75:
        raise ValueError("ORIGINALS_REQUIRE_75_DAY_WINDOW")
    rows,total=_index(request)
    # Deterministic prioritization of regulatory financial reports (not random first result).
    candidates=[x for x in rows if ("年度报告" in x["title"] or
                 "半年度报告" in x["title"] or "季度报告" in x["title"])]
    if not candidates:
        return [],{"required":1,"fetched":0,"upstream_total":total,
                  "gap_reason":"NO_OFFICIAL_REPORT_IN_WINDOW"}
    attempts=[]
    for item in candidates[:3]:
        aid=str(item.get("announcement_id",""))
        stamp=str(item.get("announced_at",""))
        if not re.fullmatch(r"[0-9]{10}",aid) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",stamp):
            continue
        url="https://static.cninfo.com.cn/finalpage/"+stamp+"/"+aid+".PDF"
        try:
            with requests.Session() as s:
                resp=s.get(url,stream=True,allow_redirects=False,timeout=(5,18),
                           headers={"User-Agent":"PublicCompanyResearch/1.0",
                                    "Referer":"https://www.cninfo.com.cn/"})
                resp.raise_for_status()
                buf=bytearray()
                for chunk in resp.iter_content(65536):
                    buf.extend(chunk)
                    if len(buf)>3*1024*1024:raise ValueError("ORIGINAL_PDF_TOO_LARGE_FOR_ON_DEMAND")
            raw=bytes(buf)
            if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-8192:]:
                raise ValueError("INVALID_OFFICIAL_PDF_BYTES")
            return [{
                "title":item["title"],"announced_at":stamp,"source_url":url,
                "source":"CNINFO_OFFICIAL_PDF","document_sha256":hashlib.sha256(raw).hexdigest(),
                "byte_count":len(raw),"pdf_base64":base64.b64encode(raw).decode("ascii"),
                "verification_state":"ORIGINAL_BYTES_CAPTURED_CONTENT_NOT_AUDITED",
                "announcement_id":aid}],{
                "required":1,"fetched":1,"upstream_total":total,"source_used":"CNINFO_OFFICIAL_PDF",
                "attempts":attempts}
        except Exception as exc:
            attempts.append({"announcement_id":aid,"error":type(exc).__name__+":"+str(exc)[:100]})
    return [],{"required":1,"fetched":0,"upstream_total":total,
              "gap_reason":"OFFICIAL_PDF_DOWNLOAD_FAILED","attempts":attempts}

def execute_extended(request):
    kind=request["data_type"]
    if kind=="financial_statements":return financial_statements(request)
    if kind=="announcement_index":return announcement_index(request)
    if kind=="official_filings":return official_filings(request)
    raise ValueError("UNSUPPORTED_DATA_TYPE")
