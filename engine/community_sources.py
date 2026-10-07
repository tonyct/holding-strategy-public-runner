"""Community-source ingestion gate: permission-aware, provenance-preserving and research-only.

Input is an explicitly supplied list of public URLs / snippets obtained through a
permitted source. This module does NOT scrape platform pages or imply live coverage.
"""
import argparse,hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from universe import load_universe

HOSTS={"eastmoney":{"guba.eastmoney.com","gubaf10.eastmoney.com","mguba.eastmoney.com"},
       "weibo":{"weibo.com","www.weibo.com","m.weibo.cn"},
       "futu":{"futunn.com","www.futunn.com"},
       "xueqiu":{"xueqiu.com","www.xueqiu.com"}}
def classify(url):
    p=urlparse(url)
    if p.scheme!="https" or p.username or p.password: return None
    return next((source for source,hosts in HOSTS.items() if p.hostname in hosts),None)

def ingest(universe_file,input_file,output_file):
    u=load_universe(universe_file)
    obj=json.loads(Path(input_file).read_text(encoding="utf-8"))
    if obj.get("schema")!="E36_COMMUNITY_CANDIDATES/v1":raise ValueError("BAD_INPUT_SCHEMA")
    rows=[];seen=set();invalid=[]
    for i,r in enumerate(obj.get("rows",[])):
        if not isinstance(r,dict): invalid.append({"index":i,"reason":"BAD_ROW"});continue
        symbol=r.get("symbol");url=r.get("url","");source=classify(url) if isinstance(url,str) else None
        if symbol not in u["active"] or not source or (r.get("source") and r["source"]!=source):
            invalid.append({"index":i,"reason":"SYMBOL_OR_SOURCE_INVALID"});continue
        scope=r.get("evidence_scope")
        if scope not in ("PUBLIC_INDEX_SNIPPET","PERMITTED_PUBLIC_PAGE","USER_SUPPLIED_EXCERPT"):
            invalid.append({"index":i,"reason":"EVIDENCE_SCOPE_MISSING"});continue
        title=str(r.get("title") or "")[:240].strip()
        snippet=str(r.get("snippet") or "")[:1500].strip()
        if not title and not snippet:
            invalid.append({"index":i,"reason":"EMPTY_CANDIDATE"});continue
        key=hashlib.sha256((symbol+"|"+source+"|"+url.split("#")[0].split("?")[0]).encode()).hexdigest()
        if key in seen:continue
        seen.add(key)
        rows.append({"id":key,"symbol":symbol,"source":source,"url":url,
                     "title":title,"snippet":snippet,"published_at":r.get("published_at"),
                     "indexed_at":r.get("indexed_at"),"evidence_scope":scope,
                     "raw_post_verified":scope=="USER_SUPPLIED_EXCERPT",
                     "issuer_fact_verified":False,"current_platform_scan_complete":False,
                     "status":"RESEARCH_LEAD_PENDING_PRIMARY_SOURCE_VERIFICATION"})
    result={"schema":"E36_COMMUNITY_RESEARCH_QUEUE/v1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "universe_sha256":u["universe_sha256"],"active_count":len(u["active"]),
        "accepted_count":len(rows),"rejected_count":len(invalid),
        "live_platform_coverage":False,"research_only":True,
        "may_directly_change_main_or_trade":False,"rows":rows,"rejected":invalid}
    out=Path(output_file);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--universe-file",default="config/research_universe.json")
    p.add_argument("--input",required=True)
    p.add_argument("--output",default="output/community/COMMUNITY_RESEARCH_QUEUE.json")
    a=p.parse_args()
    r=ingest(a.universe_file,a.input,a.output)
    print(json.dumps({"accepted":r["accepted_count"],"rejected":r["rejected_count"],"live":r["live_platform_coverage"]}))
