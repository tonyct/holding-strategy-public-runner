"""Assemble public-only company research packets from deterministic metrics and evidence."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path

def read(path):
    p=Path(path);return json.loads(p.read_text()) if p.is_file() else {}

def unresolved(state):
    return state in {
        "PRIMARY_SOURCE_VERIFICATION_PENDING",
        "PRIMARY_SOURCE_BYTES_CAPTURED_SEMANTIC_REVIEW_PENDING",
        "SOURCE_UNAVAILABLE_RETRYABLE",
    } or str(state or "").endswith("_PENDING")

def main():
    p=argparse.ArgumentParser()
    for x in ("universe","metrics","a-originals","hk-originals","text-candidates","lead-registry","run-id","output"):
        p.add_argument("--"+x,required=True)
    a=p.parse_args()
    u=read(a.universe);symbols=[x["symbol"] for x in u.get("stocks",[]) if x.get("active")]
    metrics=read(a.metrics).get("stocks",{})
    ao=read(a.a_originals).get("symbols",{});ho=read(a.hk_originals).get("symbols",{})
    tx=read(a.text_candidates).get("symbols",{});lr=read(a.lead_registry).get("leads",{})
    pending={};terminal={}
    for row in lr.values():
        bucket=pending if unresolved(row.get("state")) else terminal
        bucket[row.get("symbol")]=bucket.get(row.get("symbol"),0)+1
    packets={}
    for s in symbols:
        originals=(ho if s.endswith(".HK") else ao).get(s,{})
        files=originals.get("files",[])
        metric=metrics.get(s,{})
        packets[s]={
          "symbol":s,
          "deterministic_metrics":metric,
          "official_originals":{
            "indexed":originals.get("indexed",0),"fetched":originals.get("fetched",0),
            "complete":originals.get("complete",False),
            "sha256s":[x.get("sha256") for x in files if x.get("sha256")]},
          "original_text_candidate_source_count":len(tx.get(s,[])),
          "pending_public_lead_count":pending.get(s,0),
          "terminal_public_lead_count":terminal.get(s,0),
          "research_state":("PUBLIC_PRIMARY_EVIDENCE_READY" if originals.get("complete")
                            else "PUBLIC_PRIMARY_EVIDENCE_PARTIAL"),
          "company_research_only":True,
          "valuation_authorized":False,
          "trade_action_authorized":False}
    out={"schema":"PUBLIC_COMPANY_RESEARCH_COMPUTE/v1","source_run_id":a.run_id,
         "computed_at_utc":datetime.now(timezone.utc).isoformat(),"packets":packets,
         "public_only_contract":True,"buy_sell_prices_included":False,
         "lead_counts":{"pending":sum(pending.values()),"terminal":sum(terminal.values())},
         "automatic_fact_promotion":False,"automatic_trade_execution":False}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"packets":len(packets),
        "ready":sum(x["research_state"]=="PUBLIC_PRIMARY_EVIDENCE_READY" for x in packets.values())}))
if __name__=="__main__":main()
