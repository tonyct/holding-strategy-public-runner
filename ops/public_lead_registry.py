"""Durable lifecycle registry for public discovery leads.

Discovery is not verification. Low-information sentiment and cross-board noise
can be terminally retired by explicit source metadata; target-specific research
signals remain open until primary-source/semantic review closes them.
"""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

SCHEMA="PUBLIC_LEAD_LIFECYCLE_REGISTRY/v1"
TERMINAL_STATES={
    "CROSS_BOARD_NOISE","RETIRED_LOW_INFORMATION","VERIFIED_NO_MATERIAL_FACT",
    "DUPLICATE_ALREADY_FROZEN","FALSE_TARGET","SUPERSEDED","RETIRED_OUT_OF_SCOPE"
}

def load(path):
    p=Path(path)
    if not p.is_file(): return {"schema":SCHEMA,"leads":{}}
    x=json.loads(p.read_text())
    if x.get("schema")!=SCHEMA: raise ValueError("LEAD_REGISTRY_SCHEMA_INVALID")
    if not isinstance(x.get("leads"),dict): raise ValueError("LEAD_REGISTRY_ROWS_INVALID")
    return x

def stable(source,row):
    key=json.dumps({"source":source,"symbol":row.get("symbol") or row.get("ticker"),
                    "url":row.get("url") or row.get("link"),
                    "title":row.get("title") or row.get("post_title"),
                    "published":row.get("published_at") or row.get("date")},
                   sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(key.encode()).hexdigest()

def rows(path,source):
    p=Path(path)
    if not p.is_file(): return []
    x=json.loads(p.read_text())
    if source!="akshare":
        value=x.get("rows") or x.get("leads") or x.get("event_candidates") or []
        return value if isinstance(value,list) else []
    out=[]
    # AKShare is symbol-bucketed. Each article is its own lead, not one lead per symbol.
    for bucket in x.get("rows") or []:
        if not isinstance(bucket,dict): continue
        symbol=bucket.get("symbol")
        news=bucket.get("news") or {}
        for article in news.get("rows") or []:
            if not isinstance(article,dict): continue
            out.append({
                "symbol":symbol,
                "title":article.get("新闻标题"),
                "url":article.get("新闻链接"),
                "published_at":article.get("发布时间"),
                "article_source":article.get("文章来源"),
                "summary":article.get("新闻内容"),
                "verification_state":"UNVERIFIED_DISCOVERY",
                "source":"AKSHARE_STOCK_NEWS_EM",
            })
    return out

def classify(source,row,prior_state=None):
    if prior_state in TERMINAL_STATES:
        return prior_state
    if source=="community":
        if (row.get("discovery_relation")=="CROSS_BOARD"
                and row.get("qualified_for_target_specific_shadow_verification") is not True):
            return "CROSS_BOARD_NOISE"
        if (row.get("qualified_for_shadow_verification") is False
                or row.get("quality_category")=="PURE_SENTIMENT_OR_LOW_INFORMATION"
                or row.get("shadow_verification_priority")=="NONE"):
            return "RETIRED_LOW_INFORMATION"
    if source=="ir" and row.get("source")=="OFFICIAL_ANNOUNCEMENT_INDEX":
        return "PRIMARY_SOURCE_LOCATOR_AVAILABLE"
    return "PRIMARY_SOURCE_VERIFICATION_PENDING"

def main():
    p=argparse.ArgumentParser();p.add_argument("--registry",required=True);p.add_argument("--run-id",required=True);p.add_argument("--output",required=True)
    p.add_argument("--community");p.add_argument("--news");p.add_argument("--ir");p.add_argument("--akshare");a=p.parse_args()
    reg=load(a.registry);seen=set()
    for source,path in (("community",a.community),("news",a.news),("ir",a.ir),("akshare",a.akshare)):
        if not path: continue
        for row in rows(path,source):
            if not isinstance(row,dict): continue
            symbol=row.get("symbol") or row.get("ticker")
            if not symbol: continue
            lid=stable(source,row);seen.add(lid);rec=reg["leads"].get(lid,{})
            state=classify(source,row,rec.get("state"))
            reg["leads"][lid]={**rec,"lead_id":lid,"source":source,"symbol":symbol,"state":state,
                "first_seen_run_id":rec.get("first_seen_run_id") or a.run_id,"last_seen_run_id":a.run_id,
                "latest_observation":row,"not_seen_in_current_input":False,
                "terminal":state in TERMINAL_STATES}
    for lid,row in reg["leads"].items():
        if lid in seen: continue
        if row.get("state") not in TERMINAL_STATES:
            row["not_seen_in_current_input"]=True
            row["source_disappearance_is_not_resolution"]=True
            row["missed_input_runs"]=int(row.get("missed_input_runs",0))+1
    by_state={}
    for row in reg["leads"].values():
        st=row.get("state") or "UNKNOWN";by_state[st]=by_state.get(st,0)+1
    terminal=sum(st in TERMINAL_STATES for st in (x.get("state") for x in reg["leads"].values()))
    pending=len(reg["leads"])-terminal
    reg["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    reg["counts"]={"total":len(reg["leads"]),"pending":pending,"terminal":terminal,"by_state":by_state}
    Path(a.registry).parent.mkdir(parents=True,exist_ok=True);Path(a.registry).write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n")
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(reg["counts"]))
if __name__=="__main__":main()
