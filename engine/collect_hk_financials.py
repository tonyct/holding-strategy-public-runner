"""Fetch HK three statements from AKShare/Eastmoney without inventing field mappings.
Raw report-period rows are preserved; original HKEX filings remain independently required.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from universe import load_universe

STATEMENTS = {"income":"利润表","balance":"资产负债表","cashflow":"现金流量表"}

def records_for_period(frame, period):
    if not hasattr(frame,"to_dict"):
        raise ValueError("INVALID_DATAFRAME")
    # AKShare may store the report date in DataFrame index rather than a column.
    if hasattr(frame,"reset_index"):
        frame=frame.reset_index()
    rows=frame.to_dict(orient="records")
    keys=("报告期","报告日期","报告时间","REPORT_DATE","截止日期","日期","报告日","index","日期索引")
    import re
    wanted=period.replace("-","")
    matches=[]
    for row in rows:
        if not isinstance(row,dict):continue
        dates=[]
        for k in keys:
            if k in row and row[k] is not None:
                raw=str(row[k])
                match=re.search(r"(20\d{2})[-/年]?(\d{1,2})[-/月]?(\d{1,2})",raw)
                if match: dates.append(match[1]+match[2].zfill(2)+match[3].zfill(2))
        if wanted in dates:
            matches.append({str(k):str(v) if v is not None else None for k,v in row.items()})
    return matches

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--universe-file",default="config/research_universe.json")
    ap.add_argument("--period",default="2026-06-30")
    ap.add_argument("--output",default="output/hk_financials")
    ap.add_argument("--retries",type=int,default=2)
    args=ap.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    universe=load_universe(args.universe_file)
    try:
        import akshare as ak
        init_error=None
    except (ImportError,RuntimeError) as exc:
        ak=None;init_error=type(exc).__name__
    reports=[]
    for symbol in universe["hk_shares"]:
        body={"symbol":symbol,"report_period_end":args.period,"currency":"UNVERIFIED",
              "unit":"UNVERIFIED","statements":{},"source":"AKSHARE_EASTMONEY_HK_UNVERIFIED_PRIMARY"}
        for key,label in STATEMENTS.items():
            entry={"status":"SOURCE_UNAVAILABLE","rows":[],"attempts":[]}
            for attempt in range(max(1,min(args.retries,4))):
                try:
                    if ak is None:raise RuntimeError(init_error or "AKSHARE_NOT_INSTALLED")
                    frame=ak.stock_financial_hk_report_em(stock=symbol[:-3].zfill(5),
                                                          symbol=label,indicator="报告期")
                    rows=records_for_period(frame,args.period)
                    if not rows:
                        raise ValueError("REPORT_PERIOD_ROWS_NOT_FOUND")
                    if len(rows)==1 and len(rows[0])<4:
                        raise ValueError("INSUFFICIENT_STATEMENT_FIELDS")
                    entry={"status":"RAW_REPORT_PERIOD_ROW_FETCHED_UNVERIFIED","rows":rows,
                           "attempts":entry["attempts"]};break
                except Exception as exc:
                    entry["attempts"].append({"try":attempt+1,
                        "error":type(exc).__name__+":"+str(exc)[:180]})
                    entry["error"]=entry["attempts"][-1]["error"]
                    if attempt+1<max(1,min(args.retries,4)):
                        time.sleep(min(5,1.2*(2**attempt)))
            body["statements"][key]=entry
            time.sleep(0.8)
        body["status"]="RAW_THREE_STATEMENTS_FETCHED_UNVERIFIED" if all(
            x["status"]=="RAW_REPORT_PERIOD_ROW_FETCHED_UNVERIFIED" for x in body["statements"].values()
            ) else "HK_STATEMENTS_PARTIAL_OR_BLOCKED"
        payload=json.dumps(body,ensure_ascii=False,sort_keys=True).encode()
        digest=hashlib.sha256(payload).hexdigest()
        (out/(symbol.replace(".","_")+"_"+digest[:16]+".json")).write_bytes(payload)
        reports.append({"symbol":symbol,"status":body["status"],"sha256":digest})
    result={"schema":"E36_HK_FINANCIAL_ACQUISITION/v1","universe_sha256":universe["universe_sha256"],
            "generated_utc":datetime.now(timezone.utc).isoformat(),"period":args.period,
            "original_filing_verified":False,"unit_verified":False,"rows":reports}
    (out/"HK_FINANCIAL_RECEIPT.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"complete_raw":sum(r["status"]=="RAW_THREE_STATEMENTS_FETCHED_UNVERIFIED" for r in reports),
                      "total":len(reports)}))
    return 0 if reports and all(r["status"]=="RAW_THREE_STATEMENTS_FETCHED_UNVERIFIED" for r in reports) else 1
if __name__=="__main__":
    raise SystemExit(main())
