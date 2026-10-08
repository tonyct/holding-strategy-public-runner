"""Durable lifecycle registry for public discovery leads."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
SCHEMA="PUBLIC_LEAD_LIFECYCLE_REGISTRY/v1"

def load(path):
    p=Path(path)
    if not p.is_file(): return {"schema":SCHEMA,"leads":{}}
    x=json.loads(p.read_text())
    if x.get("schema")!=SCHEMA: raise ValueError("LEAD_REGISTRY_SCHEMA_INVALID")
    return x

def stable(source,row):
    key=json.dumps({"source":source,"symbol":row.get("symbol") or row.get("ticker"),"url":row.get("url") or row.get("link"),
                    "title":row.get("title") or row.get("post_title"),"published":row.get("published_at") or row.get("date")},
                   sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(key.encode()).hexdigest()

def rows(path):
    p=Path(path)
    if not p.is_file(): return []
    x=json.loads(p.read_text());return x.get("rows") or x.get("leads") or x.get("event_candidates") or []

def main():
    p=argparse.ArgumentParser();p.add_argument("--registry",required=True);p.add_argument("--run-id",required=True);p.add_argument("--output",required=True)
    p.add_argument("--community");p.add_argument("--news");p.add_argument("--ir");p.add_argument("--akshare");a=p.parse_args()
    reg=load(a.registry);seen=set()
    for source,path in (("community",a.community),("news",a.news),("ir",a.ir),("akshare",a.akshare)):
        if not path: continue
        for row in rows(path):
            if not isinstance(row,dict): continue
            symbol=row.get("symbol") or row.get("ticker")
            if not symbol: continue
            lid=stable(source,row);seen.add(lid)
            rec=reg["leads"].get(lid,{})
            state=rec.get("state") or ("CROSS_BOARD_NOISE" if row.get("target_specific") is False and row.get("discovery_relation")=="CROSS_BOARD" else "PRIMARY_SOURCE_VERIFICATION_PENDING")
            reg["leads"][lid]={**rec,"lead_id":lid,"source":source,"symbol":symbol,"state":state,
                               "first_seen_run_id":rec.get("first_seen_run_id") or a.run_id,"last_seen_run_id":a.run_id,
                               "latest_observation":row,"not_seen_in_current_input":False}
    for lid,row in reg["leads"].items():
        if lid not in seen and row.get("state")=="PRIMARY_SOURCE_VERIFICATION_PENDING":
            row["not_seen_in_current_input"]=True;row["source_disappearance_is_not_resolution"]=True
    pending=sum(x.get("state")=="PRIMARY_SOURCE_VERIFICATION_PENDING" for x in reg["leads"].values())
    reg["updated_at_utc"]=datetime.now(timezone.utc).isoformat();reg["counts"]={"total":len(reg["leads"]),"pending":pending,"terminal":len(reg["leads"])-pending}
    Path(a.registry).parent.mkdir(parents=True,exist_ok=True);Path(a.registry).write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n")
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(reg["counts"]))
if __name__=="__main__":main()
