"""SEC XBRL companyfacts discovery: official transport, unreviewed economics.

Public-only US ticker, bounded HTTPS requests and point-in-time filing cutoff.
These API rows are NOT an independently reviewed annual report or valuation.
"""
import hashlib
import json
import os
import re

TAG_MAP={
    "Revenues":"revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax":"revenue",
    "NetIncomeLoss":"net_profit",
    "Assets":"total_assets",
    "Liabilities":"total_liabilities",
    "NetCashProvidedByUsedInOperatingActivities":"operating_cashflow",
}
MAX_META_BYTES=2_000_000
MAX_FACT_BYTES=18_000_000

def fetch_sec_companyfacts(request, *, get=None):
    import requests
    get=get or requests.get
    symbol=request["symbol"]
    if not re.fullmatch(r"[A-Z]{1,5}(?:-[A-Z])?\\.US",symbol):
        raise ValueError("SEC_US_SYMBOL_REQUIRED")
    user_agent=os.environ.get("PUBLIC_SEC_USER_AGENT","")
    if (not isinstance(user_agent,str) or not 12<=len(user_agent)<=180
        or "@" not in user_agent or "\\n" in user_agent or "\\r" in user_agent):
        return [],{"required":1,"fetched":0,
                   "gap_reason":"SEC_COMPLIANT_CONTACT_USER_AGENT_NOT_CONFIGURED"}
    headers={"User-Agent":user_agent,"Accept":"application/json"}
    def get_json(url,max_size):
        response=get(url,headers=headers,timeout=(5,18),allow_redirects=False)
        if response.status_code!=200 or len(response.content)>max_size:
            raise ValueError("SEC_HTTP_OR_RESPONSE_SIZE_INVALID")
        return response.json(),hashlib.sha256(response.content).hexdigest()
    mapping,map_sha=get_json("https://www.sec.gov/files/company_tickers.json",
                             MAX_META_BYTES)
    ticker=symbol[:-3]
    matched=[x for x in mapping.values() if isinstance(x,dict)
             and x.get("ticker")==ticker
             and isinstance(x.get("cik_str"),int)]
    if len(matched)!=1:
        return [],{"required":1,"fetched":0,
                   "gap_reason":"SEC_TICKER_CIK_MAPPING_NOT_UNAMBIGUOUS"}
    cik=matched[0]["cik_str"]
    if not 1<=cik<=9_999_999_999:
        raise ValueError("SEC_CIK_OUT_OF_RANGE")
    url="https://data.sec.gov/api/xbrl/companyfacts/CIK"+str(cik).zfill(10)+".json"
    document,facts_sha=get_json(url,MAX_FACT_BYTES)
    if document.get("cik")!=cik:
        raise ValueError("SEC_ENTITY_CIK_MISMATCH")
    from datetime import date
    start=date.fromisoformat(request["start_date"])
    asof=date.fromisoformat(request["end_date"])
    rows=[]
    seen=set()
    tags=(document.get("facts") or {}).get("us-gaap") or {}
    for official_tag,metric in TAG_MAP.items():
        item=tags.get(official_tag) or {}
        for unit,entries in (item.get("units") or {}).items():
            if unit!="USD" or not isinstance(entries,list):
                continue
            choices=[]
            for value in entries:
                if not isinstance(value,dict):
                    continue
                filed=value.get("filed","")
                try:
                    fdate=date.fromisoformat(filed)
                    period_end=date.fromisoformat(value["end"])
                except (ValueError,TypeError,KeyError):
                    continue
                if not start<=fdate<=asof or value.get("form") not in ("10-K","10-Q"):
                    continue
                if isinstance(value.get("val"),bool) or not isinstance(value.get("val"),int):
                    continue
                accn=value.get("accn","")
                if not re.fullmatch(r"\\d{10}-\\d{2}-\\d{6}",accn):
                    continue
                choices.append((fdate,period_end,value))
            if not choices:
                continue
            filed,period_end,value=max(choices,key=lambda x:(x[0],x[1]))
            record_id=(metric,value["accn"],period_end.isoformat())
            if record_id in seen:
                continue
            seen.add(record_id)
            rows.append({
                "symbol":symbol,"cik":cik,
                "metric":metric,"sec_us_gaap_tag":official_tag,
                "value":str(value["val"]),"unit":"USD","currency":"USD",
                "form":value["form"],"accession":value["accn"],
                "filed_at":filed.isoformat(),"report_period_end":period_end.isoformat(),
                "fiscal_year":value.get("fy"),"fiscal_period":value.get("fp"),
                "statement_start":value.get("start"),
                "source_used":"SEC_OFFICIAL_COMPANYFACTS_API",
                "source_payload_sha256":facts_sha,
                "economic_verification":"UNREVIEWED_SEC_XBRL_REPORTING_FACT"})
            if len(rows)>=24:
                break
        if len(rows)>=24:
            break
    return rows,{
        "required":2,"fetched":1 if rows else 0,
        "source_used":"sec_edgar_companyfacts" if rows else None,
        "source_payload_sha256":facts_sha,"mapping_sha256":map_sha,
        "source_kind":"SEC_PUBLIC_XBRL_API",
        "filing_cutoff_at":asof.isoformat(),
        "no_future_filing_accepted":True,
        "economic_verified":False,
        "missing_fields":["original_filing_semantic_audit"],
        "gap_reason":"NO_POINT_IN_TIME_SEC_FILING_WITH_SELECTED_FACTS" if not rows else None,
    }
