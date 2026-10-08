"""Conservatively advance public discovery leads using deterministic evidence rules.

This worker never upgrades a community/news claim into a verified issuer fact.
It only retires obvious noise/low-information leads, proves duplicates, or binds
a lead to already-downloaded official bytes for later semantic review.
"""
import argparse,json,re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs

PENDING_STATES={
    "PRIMARY_SOURCE_VERIFICATION_PENDING",
    "PRIMARY_SOURCE_BYTES_CAPTURED_SEMANTIC_REVIEW_PENDING",
    "SOURCE_UNAVAILABLE_RETRYABLE",
}

def load(path):
    p=Path(path)
    return json.loads(p.read_text()) if p.is_file() else {}

def unresolved(state):
    return state in PENDING_STATES or str(state or "").endswith("_PENDING")

def norm(text):
    text=str(text or "").casefold()
    # Secondary IR titles often prepend issuer short name before a colon.
    if ":" in text or "：" in text:
        parts=re.split(r"[:：]",text,maxsplit=1)
        if len(parts)==2 and len(parts[0])<=20:
            text=parts[1]
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+","",text)

def containment(a,b):
    a,b=norm(a),norm(b)
    return bool(a and b and (a in b or b in a) and min(len(a),len(b))>=8)

def a_evidence(receipt):
    by_id={};by_symbol={}
    for symbol,row in (receipt.get("symbols") or {}).items():
        for f in row.get("files",[]):
            if f.get("status")!="FETCHED_OFFICIAL_ORIGINAL" or not f.get("sha256"):
                continue
            item={**f,"symbol":symbol}
            aid=str(f.get("announcement_id") or "")
            if aid: by_id[(symbol,aid)]=item
            by_symbol.setdefault(symbol,[]).append(item)
    return by_id,by_symbol

def announcement_id(url):
    try:
        q=parse_qs(urlparse(str(url or "")).query)
        return str((q.get("announcementId") or [""])[0])
    except Exception:
        return ""

def bind(row,evidence,method):
    row["state"]="PRIMARY_SOURCE_BYTES_CAPTURED_SEMANTIC_REVIEW_PENDING"
    row["primary_source_binding"]={
        "method":method,
        "sha256":evidence.get("sha256"),
        "filename":evidence.get("filename"),
        "announcement_id":evidence.get("announcement_id"),
        "date":evidence.get("date") or evidence.get("published_at"),
        "title":evidence.get("title"),
        "semantic_fact_verified":False,
    }
    row["terminal"]=False

def resolve(registry,a_originals,hk_originals):
    if registry.get("schema")!="PUBLIC_LEAD_LIFECYCLE_REGISTRY/v1":
        raise ValueError("LEAD_REGISTRY_SCHEMA_INVALID")
    a_by_id,a_by_symbol=a_evidence(a_originals)
    leads=registry.get("leads") or {}
    official_ir={}
    for lid,row in leads.items():
        obs=row.get("latest_observation") or {}
        if row.get("source")=="ir" and obs.get("source")=="OFFICIAL_ANNOUNCEMENT_INDEX":
            official_ir.setdefault((row.get("symbol"),obs.get("announced_at")),[]).append((lid,obs))

    transitions=[]
    for lid,row in leads.items():
        if row.get("state")!="PRIMARY_SOURCE_VERIFICATION_PENDING":
            continue
        before=row["state"];source=row.get("source");obs=row.get("latest_observation") or {}
        if source=="community":
            cross=(obs.get("discovery_relation")=="CROSS_BOARD"
                   and obs.get("qualified_for_target_specific_shadow_verification") is not True)
            low=(obs.get("quality_category")=="PURE_SENTIMENT_OR_LOW_INFORMATION"
                 or obs.get("qualified_for_shadow_verification") is False
                 or obs.get("shadow_verification_priority")=="NONE")
            if cross:
                row.update(state="CROSS_BOARD_NOISE",terminal=True,
                    resolution_reason="DISCOVERY_NOT_TARGET_SPECIFIC")
            elif low:
                row.update(state="RETIRED_LOW_INFORMATION",terminal=True,
                    resolution_reason="DISCOVERY_EXPLICITLY_NOT_QUALIFIED_FOR_RESEARCH_VERIFICATION")
        elif source=="akshare":
            news=obs.get("news") or {};rows=news.get("rows") or []
            if news.get("status")=="SKIPPED_HK_NUMERIC_CODE_NOISE" and not rows:
                row.update(state="RETIRED_SOURCE_AMBIGUOUS",terminal=True,
                    resolution_reason="HK_NUMERIC_CODE_SEARCH_EXPLICITLY_AMBIGUOUS")
            elif not rows and news.get("status") not in ("PUBLIC_ROWS_FETCHED",):
                row.update(state="SOURCE_UNAVAILABLE_RETRYABLE",terminal=False,
                    resolution_reason="PUBLIC_DISCOVERY_SOURCE_CURRENTLY_UNAVAILABLE")
        elif source=="ir":
            symbol=row.get("symbol");date=obs.get("announced_at");aid=announcement_id(obs.get("url"))
            if obs.get("source")=="SECONDARY_IR_DISCOVERY":
                dup=next(((oid,o) for oid,o in official_ir.get((symbol,date),[])
                          if containment(obs.get("title"),o.get("title"))),None)
                if dup:
                    row.update(state="DUPLICATE_ALREADY_REGISTERED",terminal=True,
                        duplicate_of=dup[0],resolution_reason="SAME_SYMBOL_DATE_TITLE_AS_OFFICIAL_DISCOVERY")
                else:
                    match=next((x for x in a_by_symbol.get(symbol,[])
                                if str(x.get("date") or "")==str(date or "")
                                and containment(obs.get("title"),x.get("title"))),None)
                    if match: bind(row,match,"SECONDARY_DISCOVERY_MATCHED_DOWNLOADED_OFFICIAL_TITLE_DATE")
            else:
                match=a_by_id.get((symbol,aid)) if aid else None
                if match: bind(row,match,"OFFICIAL_ANNOUNCEMENT_ID_MATCHED_DOWNLOADED_BYTES")

        if row.get("state")!=before:
            row["resolved_or_advanced_at_utc"]=datetime.now(timezone.utc).isoformat()
            transitions.append({"lead_id":lid,"symbol":row.get("symbol"),"source":source,
                                "from":before,"to":row.get("state")})

    states=Counter(x.get("state") for x in leads.values())
    pending=sum(unresolved(x.get("state")) for x in leads.values())
    registry["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    registry["counts"]={"total":len(leads),"pending":pending,"terminal":len(leads)-pending,
                        "by_state":dict(sorted(states.items(),key=lambda x:str(x[0])))}
    registry["resolution_semantics"]={
        "community_or_news_claims_auto_verified_as_issuer_fact":False,
        "official_byte_binding_is_semantic_fact_verification":False,
        "source_disappearance_is_resolution":False,
    }
    report={"schema":"PUBLIC_LEAD_RESOLUTION_REPORT/v1",
            "generated_at_utc":registry["updated_at_utc"],
            "transition_count":len(transitions),"transitions":transitions,
            "counts":registry["counts"],
            "automatic_fact_promotion":False,"valuation_authorized":False,
            "automatic_trade_execution":False}
    return registry,report

def main():
    p=argparse.ArgumentParser()
    for x in ("registry","a-originals","hk-originals","report"):p.add_argument("--"+x,required=True)
    a=p.parse_args()
    reg,report=resolve(load(a.registry),load(a.a_originals),load(a.hk_originals))
    Path(a.registry).write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n")
    Path(a.report).parent.mkdir(parents=True,exist_ok=True)
    Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"transition_count":report["transition_count"],**report["counts"]},ensure_ascii=False))
if __name__=="__main__":main()
