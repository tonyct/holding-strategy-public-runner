"""Assemble public-only company research packets from deterministic metrics and evidence.

A complete announcement window is not equivalent to decisive primary evidence.
The packet reports coverage honestly and never authorizes valuation or trading.
"""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path

TERMINAL_LEAD_STATES={
 "CROSS_BOARD_NOISE","RETIRED_LOW_INFORMATION","VERIFIED_NO_MATERIAL_FACT",
 "DUPLICATE_ALREADY_FROZEN","FALSE_TARGET","SUPERSEDED","RETIRED_OUT_OF_SCOPE"
}

def read(path):
    p=Path(path);return json.loads(p.read_text()) if p.is_file() else {}

def original_state(originals):
    indexed=int(originals.get("indexed",0) or 0);fetched=int(originals.get("fetched",0) or 0)
    complete=originals.get("complete") is True
    if complete and indexed==0:
        return "WINDOW_COMPLETE_NO_NEW_OFFICIAL_ORIGINALS"
    if complete and indexed>0 and fetched==indexed:
        return "CURRENT_WINDOW_ORIGINALS_COMPLETE"
    if fetched>0:
        return "CURRENT_WINDOW_ORIGINALS_PARTIAL"
    return "CURRENT_WINDOW_ORIGINALS_UNAVAILABLE"

def research_state(originals,metric,text_rows):
    ostate=original_state(originals)
    financial=(metric or {}).get("financials") or {}
    metric_state=financial.get("source_verification_state")
    if ostate=="CURRENT_WINDOW_ORIGINALS_COMPLETE":
        return "PUBLIC_EVIDENCE_PACKET_AVAILABLE"
    if ostate=="WINDOW_COMPLETE_NO_NEW_OFFICIAL_ORIGINALS":
        return ("PUBLIC_WINDOW_COMPLETE_NO_NEW_ORIGINALS_STRUCTURED_FINANCIALS_UNVERIFIED"
                if metric_state else "PUBLIC_WINDOW_COMPLETE_NO_NEW_ORIGINALS")
    if text_rows or metric_state:
        return "PUBLIC_EVIDENCE_PACKET_PARTIAL"
    return "PUBLIC_EVIDENCE_UNAVAILABLE"

def main():
    p=argparse.ArgumentParser()
    for x in ("universe","metrics","a-originals","hk-originals","text-candidates","lead-registry","run-id","output"):
        p.add_argument("--"+x,required=True)
    a=p.parse_args()
    u=read(a.universe);symbols=[x["symbol"] for x in u.get("stocks",[]) if x.get("active")]
    metrics=read(a.metrics).get("stocks",{})
    ao=read(a.a_originals).get("symbols",{});ho=read(a.hk_originals).get("symbols",{})
    tx=read(a.text_candidates).get("symbols",{});lr=read(a.lead_registry).get("leads",{})
    lead_counts={}
    for row in lr.values():
        symbol=row.get("symbol")
        if not symbol: continue
        item=lead_counts.setdefault(symbol,{"open":0,"terminal":0,"by_state":{}})
        state=row.get("state") or "UNKNOWN";item["by_state"][state]=item["by_state"].get(state,0)+1
        if state in TERMINAL_LEAD_STATES:item["terminal"]+=1
        else:item["open"]+=1
    packets={}
    for s in symbols:
        originals=(ho if s.endswith(".HK") else ao).get(s,{})
        files=originals.get("files",[]);metric=metrics.get(s,{})
        text_rows=tx.get(s,[]);lc=lead_counts.get(s,{"open":0,"terminal":0,"by_state":{}})
        ostate=original_state(originals)
        packets[s]={
          "symbol":s,
          "deterministic_metrics":metric,
          "official_originals":{
            "indexed":originals.get("indexed",0),"fetched":originals.get("fetched",0),
            "complete_window":originals.get("complete",False),"coverage_state":ostate,
            "sha256s":[x.get("sha256") for x in files if x.get("sha256")]},
          "original_text_candidate_source_count":len(text_rows),
          "public_leads":{"open_count":lc["open"],"terminal_count":lc["terminal"],"by_state":lc["by_state"]},
          "pending_public_lead_count":lc["open"],
          "research_state":research_state(originals,metric,text_rows),
          "decisive_primary_financial_evidence_verified":False,
          "company_research_only":True,
          "valuation_authorized":False,
          "trade_action_authorized":False}
    out={"schema":"PUBLIC_COMPANY_RESEARCH_COMPUTE/v2","source_run_id":a.run_id,
         "computed_at_utc":datetime.now(timezone.utc).isoformat(),"packets":packets,
         "public_only_contract":True,"buy_sell_prices_included":False,
         "automatic_trade_execution":False}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"packets":len(packets),
        "evidence_packet_available":sum(x["research_state"]=="PUBLIC_EVIDENCE_PACKET_AVAILABLE" for x in packets.values()),
        "window_complete_no_new":sum("NO_NEW_ORIGINALS" in x["research_state"] for x in packets.values())}))
if __name__=="__main__":main()
