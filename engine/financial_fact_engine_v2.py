"""Deterministic public-only fact processing. Candidate facts are never promoted to verified."""
import argparse
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS={"revenue","attributable_net_profit","net_profit","operating_cash_flow","capital_expenditure","assets","liabilities","cash","interest_bearing_debt","issued_shares","minority_interest"}
PERIODS={"FY","H1_YTD","Q1_YTD","Q3_YTD","QUARTER","TTM","POINT_IN_TIME"}
SCOPES={"CONSOLIDATED","PARENT","ENTITY","UNKNOWN"}

def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def number(x):
    if x is None or isinstance(x,bool): raise ValueError("INVALID_NUMBER")
    try:
        v=Decimal(str(x).replace(",",""))
        if not v.is_finite(): raise ValueError("NON_FINITE")
        return v
    except InvalidOperation as e: raise ValueError("INVALID_NUMBER") from e

def fact(row):
    r=dict(row)
    for k in ("symbol","field","value","currency","period_end","period_type","scope","source"):
        if k not in r: raise ValueError("MISSING_"+k.upper())
    if r["field"] not in FIELDS or r["period_type"] not in PERIODS or r["scope"] not in SCOPES:
        raise ValueError("INVALID_FIELD_OR_CONTEXT")
    s=r["source"]
    if not isinstance(s,dict) or len(str(s.get("document_sha256","")))!=64 or not isinstance(s.get("page"),int) or s["page"]<1:
        raise ValueError("INVALID_SOURCE")
    if r["period_type"]!="POINT_IN_TIME" and not r.get("period_start"): raise ValueError("MISSING_START")
    if r.get("period_start") and date.fromisoformat(r["period_start"])>date.fromisoformat(r["period_end"]):
        raise ValueError("INVALID_PERIOD")
    date.fromisoformat(r["period_end"])
    mul=number(r.get("unit_multiplier",1))
    if mul<=0: raise ValueError("INVALID_UNIT")
    r["value"]=str(number(r["value"])*mul)
    r["unit_multiplier"]="1"
    r["schema"]="PUBLIC_FINANCIAL_FACT/v2"
    r["kind"]="NORMALIZED_CANDIDATE"
    r["verification_state"]="UNVERIFIED"
    identity={k:r.get(k) for k in ("symbol","field","currency","period_start","period_end","period_type","scope")}
    r["semantic_key"]=digest(identity)
    r["fact_id"]=digest({"identity":identity,"value":r["value"],"source":s})
    return r

def derive(field, inputs, formula, compute, period_start=None, period_end=None, period_type=None):
    if not inputs: raise ValueError("MISSING_INPUTS")
    first=inputs[0]
    if any(any(f[k]!=first[k] for k in ("symbol","currency","scope")) for f in inputs):
        raise ValueError("MIXED_CONTEXT")
    v=compute([number(f["value"]) for f in inputs])
    if v is None: raise ValueError("UNDEFINED_RESULT")
    identity={"symbol":first["symbol"],"field":field,"currency":first["currency"],"scope":first["scope"],
              "period_start":period_start if period_start is not None else first.get("period_start"),
              "period_end":period_end or first["period_end"],"period_type":period_type or first["period_type"]}
    out={**identity,"schema":"PUBLIC_FINANCIAL_FACT/v2","kind":"DETERMINISTIC_DERIVED",
         "value":str(v),"formula_id":formula,"input_fact_ids":[f["fact_id"] for f in inputs],
         "verification_state":"UNVERIFIED","source_verification_inherited":True}
    out["semantic_key"]=digest(identity)
    out["fact_id"]=digest({"identity":identity,"value":out["value"],"formula":formula,"inputs":out["input_fact_ids"]})
    return out

def ttm(fy,current,previous):
    if [x["period_type"] for x in (fy,current,previous)]!=["FY","H1_YTD","H1_YTD"]:
        raise ValueError("TTM_PERIOD_TYPE")
    if any(x["field"]!=fy["field"] for x in (current,previous)): raise ValueError("TTM_FIELD")
    fe,ce,pe=map(lambda x:date.fromisoformat(x["period_end"]),(fy,current,previous))
    fs,cs,ps=map(lambda x:date.fromisoformat(x["period_start"]),(fy,current,previous))
    if not (fe.month==12 and fe.day==31 and fs==date(fe.year,1,1) and
            ce==date(fe.year+1,6,30) and pe==date(fe.year,6,30) and
            cs==date(fe.year+1,1,1) and ps==date(fe.year,1,1)):
        raise ValueError("TTM_ALIGNMENT")
    return derive(fy["field"],[fy,current,previous],"FY_PLUS_CURRENT_H1_MINUS_PRIOR_H1/v2",
                  lambda a:a[0]+a[1]-a[2],(pe+timedelta(days=1)).isoformat(),ce.isoformat(),"TTM")

def ratio(a,b,name):
    if any(a.get(k)!=b.get(k) for k in ("symbol","currency","scope","period_start","period_end","period_type")):
        raise ValueError("RATIO_ALIGNMENT")
    if number(b["value"])==0: raise ValueError("ZERO_DENOMINATOR")
    return derive(name,[a,b],"RATIO/v2",lambda v:v[0]/v[1])

def delta(old,new):
    def group(rows):
        d=defaultdict(set)
        for r in rows:d[r["semantic_key"]].add(r["fact_id"])
        return d
    a,b=group(old),group(new)
    changes=[]
    for k in sorted(set(a)|set(b)):
        before,after=sorted(a.get(k,set())),sorted(b.get(k,set()))
        state=("CONFLICTED" if len(after)>1 else "ADDED" if not before else "REMOVED" if not after else "UNCHANGED" if before==after else "CHANGED")
        if state!="UNCHANGED":changes.append({"semantic_key":k,"status":state,"previous_fact_ids":before,"current_fact_ids":after})
    return {"schema":"PUBLIC_FINANCIAL_DELTA/v2","changes":changes,"change_count":len(changes)}

def run(rows,prior=None):
    facts=[fact(r) for r in rows]
    by_context=defaultdict(lambda:defaultdict(list))
    for f in facts:
        context=tuple(f.get(k) for k in ("symbol","currency","scope","period_start","period_end","period_type"))
        by_context[context][f["field"]].append(f)
    derived=[]
    for fields in by_context.values():
        ocf=fields.get("operating_cash_flow",[])
        capex=fields.get("capital_expenditure",[])
        if len(ocf)==1 and len(capex)==1 and ocf[0]["source"]["document_sha256"]==capex[0]["source"]["document_sha256"]:
            derived.append(derive("simple_historical_free_cash_flow",[ocf[0],capex[0]],
                          "OPERATING_CASH_FLOW_MINUS_REPORTED_CAPITAL_EXPENDITURE/v2",
                          lambda x:x[0]-x[1]))
    facts.extend(derived)
    by_symbol=defaultdict(list)
    for r in facts:by_symbol[r["symbol"]].append(r)
    compact={"schema":"PUBLIC_COMPACT_FACT_PACKET/v2","stocks":{
        sym:[{k:f.get(k) for k in ("fact_id","field","value","currency","period_start","period_end","period_type","scope","verification_state")}
             for f in sorted(v,key=lambda x:(x["field"],x["period_end"],x["fact_id"]))]
        for sym,v in sorted(by_symbol.items())},"no_valuation":True,"no_trade_logic":True,"historical_simplified_fcf_is_not_owner_cash_flow":True}
    return {"store":{"schema":"PUBLIC_FACT_STORE/v2","facts":facts}, "compact":compact,"delta":delta(prior or [],facts)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True);p.add_argument("--previous");p.add_argument("--out-dir",required=True)
    args=p.parse_args()
    source=json.loads(Path(args.input).read_text(encoding="utf-8"))
    prior=json.loads(Path(args.previous).read_text(encoding="utf-8")).get("facts",[]) if args.previous else []
    outputs=run(source["facts"],prior)
    root=Path(args.out_dir);root.mkdir(parents=True,exist_ok=True)
    for key,filename in (("store","PUBLIC_FACT_STORE_V2.json"),("compact","PUBLIC_COMPACT_FACT_PACKET_V2.json"),("delta","PUBLIC_DELTA_PACKET_V2.json")):
        (root/filename).write_text(json.dumps(outputs[key],sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

if __name__=="__main__":main()
