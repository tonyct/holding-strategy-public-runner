"""Conservative A/H API snapshot adapter, only explicit CNY unit and accounting scope.

Never infers period basis, stock currency, or Hong Kong report units.
"""
import argparse,json,hashlib
from datetime import datetime,timezone
from pathlib import Path

MAP={"revenue":"revenue","attributable_net_profit":"attributable_net_profit",
     "net_profit":"net_profit","total_assets":"assets","total_liabilities":"liabilities",
     "operating_cashflow":"operating_cash_flow"}
UNITS={"CNY_YUAN":"1","CNY_THOUSANDS":"1000","CNY_TEN_THOUSANDS":"10000","CNY_MILLIONS":"1000000"}
def convert_a_snapshot(snapshot,sha):
    rows=[];rejected=[]
    symbol=snapshot.get("symbol")
    for section in ("income","balance","cashflow"):
        data=(snapshot.get("statements") or {}).get(section,{}).get("data") or {}
        values=data.get("standard_fields") or {}
        period=data.get("report_period_end") or snapshot.get("report_period_end")
        unit=data.get("raw_numeric_unit")
        scope=data.get("accounting_scope")
        if not isinstance(values,dict):continue
        if unit not in UNITS or scope not in ("CONSOLIDATED","PARENT"):
            rejected.append({"symbol":symbol,"section":section,"reason":"UNVERIFIED_UNIT_OR_SCOPE"})
            continue
        if not period or len(str(period))!=10:
            rejected.append({"symbol":symbol,"section":section,"reason":"MISSING_PERIOD"})
            continue
        if period[5:]== "12-31":
            kind="FY"
        elif period[5:]=="06-30":kind="H1_YTD"
        elif period[5:]=="03-31":kind="Q1_YTD"
        elif period[5:]=="09-30":kind="Q3_YTD"
        else:
            rejected.append({"symbol":symbol,"section":section,"reason":"UNKNOWN_PERIOD_BASIS"})
            continue
        for key,field in MAP.items():
            if key not in values:continue
            if section=="income" and field not in ("revenue","attributable_net_profit","net_profit"):continue
            if section=="cashflow" and field!="operating_cash_flow":continue
            if section=="balance" and field not in ("assets","liabilities"):continue
            rows.append({"symbol":symbol,"field":field,"value":values[key],
                        "currency":"CNY","unit_multiplier":UNITS[unit],
                        "period_start":None if section=="balance" else period[:4]+"-01-01",
                        "period_end":period,"period_type":"POINT_IN_TIME" if section=="balance" else kind,
                        "scope":scope,"source_type":"PUBLIC_API","source_id":sha+":"+section+":"+key,
                        "observed_at":data.get("collected_at") or snapshot.get("collected_at"),
                        "provider_field":key,"source_snapshot_sha256":sha})
    return rows,rejected
def collect(a_dir,hk_dir):
    rows=[];rejected=[];files=[]
    for path in sorted(Path(a_dir).glob("snapshots/*.json")):
        raw=path.read_bytes()
        try:
            a,b=convert_a_snapshot(json.loads(raw),hashlib.sha256(raw).hexdigest())
            rows+=a;rejected+=b;files.append(path.name)
        except (ValueError,KeyError,TypeError) as exc:
            rejected.append({"file":path.name,"reason":"INVALID_A_SNAPSHOT:"+type(exc).__name__})
    for path in sorted(Path(hk_dir).glob("*.json")):
        if path.name=="HK_FINANCIAL_RECEIPT.json":continue
        try:
            h=json.loads(path.read_text(encoding="utf-8"))
            if h.get("currency")=="UNVERIFIED" or h.get("unit")=="UNVERIFIED":
                rejected.append({"symbol":h.get("symbol"),"file":path.name,
                                 "reason":"HK_CURRENCY_OR_UNIT_UNVERIFIED"})
        except (ValueError,TypeError):
            rejected.append({"file":path.name,"reason":"INVALID_HK_SNAPSHOT"})
    return {"schema":"PUBLIC_API_STANDARDIZATION_RECEIPT/v1","records":rows,
            "rejected":rejected,"a_snapshot_files_seen":len(files),
            "automatic_fact_verification":False,"may_modify_private_head":False}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--a-financials",required=True)
    p.add_argument("--hk-financials",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    out=collect(a.a_financials,a.hk_financials)
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
if __name__=="__main__":main()
