"""Build public-only company research packets from current acquisition and evidence."""
import argparse,glob,json,hashlib
from datetime import datetime,timezone
from pathlib import Path

def read(path):
    p=Path(path);return json.loads(p.read_text()) if p.is_file() else {}

def main():
    p=argparse.ArgumentParser();p.add_argument("--universe",required=True);p.add_argument("--quotes",required=True)
    p.add_argument("--a-financials",required=True);p.add_argument("--hk-financials",required=True)
    p.add_argument("--a-originals",required=True);p.add_argument("--hk-originals",required=True)
    p.add_argument("--text-candidates",required=True);p.add_argument("--lead-registry",required=True)
    p.add_argument("--run-id",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    u=read(a.universe);symbols=[x["symbol"] for x in u.get("stocks",[]) if x.get("active")]
    q=read(a.quotes);qrows={x.get("ticker"):x for x in q.get("rows",[])}
    ao=read(a.a_originals).get("symbols",{});ho=read(a.hk_originals).get("symbols",{})
    tx=read(a.text_candidates).get("symbols",{});lr=read(a.lead_registry).get("leads",{})
    pending={}
    for row in lr.values():
        if row.get("state")=="PRIMARY_SOURCE_VERIFICATION_PENDING": pending[row.get("symbol")]=pending.get(row.get("symbol"),0)+1
    packets={}
    for s in symbols:
        originals=(ao if not s.endswith(".HK") else ho).get(s,{})
        files=originals.get("files",[])
        finance_files=(glob.glob(str(Path(a.a_financials)/"snapshots"/(s.replace(".","_")+"*.json"))) if not s.endswith(".HK")
                       else glob.glob(str(Path(a.hk_financials)/(s.replace(".","_")+"*.json"))))
        fin=[]
        for path in finance_files:
            raw=Path(path).read_bytes();fin.append({"path":str(path),"sha256":hashlib.sha256(raw).hexdigest(),"document":json.loads(raw)})
        packets[s]={"symbol":s,
          "quote":qrows.get(s),
          "official_originals":{"indexed":originals.get("indexed",0),"fetched":originals.get("fetched",0),
                                "complete":originals.get("complete",False),"sha256s":[x.get("sha256") for x in files if x.get("sha256")]},
          "financial_snapshots":fin,
          "original_text_candidate_source_count":len(tx.get(s,[])),
          "pending_public_lead_count":pending.get(s,0),
          "research_state":("PUBLIC_PRIMARY_EVIDENCE_READY" if originals.get("complete") else "PUBLIC_PRIMARY_EVIDENCE_PARTIAL"),
          "company_research_only":True,"portfolio_decision":False,"trade_signal":False}
    out={"schema":"PUBLIC_COMPANY_RESEARCH_COMPUTE/v1","source_run_id":a.run_id,
         "computed_at_utc":datetime.now(timezone.utc).isoformat(),"packets":packets,
         "contains_account_state":False,"contains_portfolio_decision":False,"contains_trade_logic":False}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"packets":len(packets),"ready":sum(x["research_state"]=="PUBLIC_PRIMARY_EVIDENCE_READY" for x in packets.values())}))
if __name__=="__main__":main()
