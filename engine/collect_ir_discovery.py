"""Extract investor-relations / research-meeting leads from announcement discovery outputs."""
import argparse,json,re
from datetime import datetime,timezone
from pathlib import Path

PAT=re.compile(r"投资者关系|调研活动|业绩说明会|路演|机构调研|投资者集体接待",re.I)

def collect(input_dir,output):
    root=Path(input_dir); rows=[]
    for p in root.glob("*.json"):
        if p.name=="ANNOUNCEMENT_RECEIPT.json": continue
        try: obj=json.loads(p.read_text())
        except Exception: continue
        symbol=obj.get("symbol")
        for item in obj.get("items",[]):
            title=str(item.get("title") or "")
            if PAT.search(title):
                rows.append({"symbol":symbol,"source":"OFFICIAL_ANNOUNCEMENT_INDEX","title":title,"url":item.get("url"),
                             "announced_at":item.get("announced_at"),"verification_state":"UNVERIFIED_DISCOVERY"})
        sec=(obj.get("secondary_discovery") or {}).get("unresolved_secondary_only_leads",[])
        for item in sec:
            title=str(item.get("title") or "")+" "+str(item.get("type_name") or "")
            if PAT.search(title):
                rows.append({"symbol":symbol,"source":"SECONDARY_IR_DISCOVERY","title":item.get("title"),"url":item.get("url"),
                             "announced_at":item.get("announced_at"),"type_name":item.get("type_name"),
                             "verification_state":"UNVERIFIED_DISCOVERY"})
    out={"schema":"E36_PUBLIC_IR_DISCOVERY/v1","generated_utc":datetime.now(timezone.utc).isoformat(),
         "research_only":True,"may_directly_change_main_or_trade":False,"lead_count":len(rows),"rows":rows}
    dest=Path(output); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--input-dir",default="output/a"); p.add_argument("--output",default="output/ir/IR_DISCOVERY.json")
    a=p.parse_args(); r=collect(a.input_dir,a.output); print(json.dumps({"leads":r["lead_count"]},ensure_ascii=False))
