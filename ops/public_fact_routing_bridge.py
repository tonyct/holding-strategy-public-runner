"""Bridge Public v2 source-bound candidates into API-first routed review packets.

No source is independently verified; this bridge never rewrites private state.
"""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from ops.public_api_first_router import route

def from_fact_store(store,observed_at):
    result=[]
    for f in store.get("facts",[]):
        if f.get("kind")!="NORMALIZED_CANDIDATE":continue
        source=f.get("source") or {}
        if not source.get("document_sha256") or not source.get("page"):continue
        result.append({"symbol":f.get("symbol"),"field":f.get("field"),"value":f.get("value"),
                       "currency":f.get("currency"),"period_start":f.get("period_start"),
                       "period_end":f.get("period_end"),"period_type":f.get("period_type"),
                       "scope":f.get("scope"),"unit_multiplier":"1",
                       "source_type":"OFFICIAL_REPORT","source_id":f.get("fact_id"),
                       "document_sha256":source["document_sha256"],"page":source["page"],
                       "observed_at":observed_at})
    return result

def build(universe,store,api_records,observed_at):
    symbols=[x["symbol"] for x in universe.get("stocks",[]) if x.get("active") is True]
    candidate=from_fact_store(store,observed_at)
    packet=route(symbols,list(api_records)+candidate,observed_at)
    packet["inputs"]={"api_candidate_count":len(api_records),
                      "original_document_candidate_count":len(candidate)}
    packet["source_verification_state"]="UNVERIFIED"
    packet["private_consumption_approved"]=False
    return packet

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--universe",required=True)
    ap.add_argument("--fact-store",required=True)
    ap.add_argument("--api-records")
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    read=lambda p:json.loads(Path(p).read_text(encoding="utf-8"))
    source=read(args.api_records) if args.api_records and Path(args.api_records).is_file() else []
    records=source.get("records",[]) if isinstance(source,dict) else source
    if not isinstance(records,list):raise ValueError("INVALID_API_RECORDS")
    out=build(read(args.universe),read(args.fact_store),records,datetime.now(timezone.utc).isoformat())
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
