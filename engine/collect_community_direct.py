"""Direct public community discovery.

Primary source: Eastmoney Guba public article-list endpoint (no account state).
Research-only discovery: never directly changes valuation, MAIN, or trading.
"""
import argparse,json,time,re
from datetime import datetime,timezone
from pathlib import Path
import requests
from universe import load_universe

API="https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist"

RESEARCH_TERMS=(
    "业绩","财报","收入","利润","成本","分红","回购","增持","减持","公告","月报",
    "订单","项目","产能","扩产","停产","涨价","降价","销量","产量","资本开支",
    "诉讼","监管","合作","收购","出售","审批","临床","获批","调研","说明会",
    "政策","关税","融资","事故","铜","钴","煤","油","天然气","水泥","PCB",
    "电子纱","电子布","创新药","AI","算力","云业务","油气","矿","物流"
)
PURE_SENTIMENT_TERMS=(
    "梭哈","抄底","主力","洗盘","吸筹","看涨","看跌","太牛","好难熬","何时到底",
    "割肉","加仓","清仓","目标价","涨停","跌停","退市"
)

def qualify(title,click_count=None,comment_count=None):
    text=str(title or "")
    matched=[x for x in RESEARCH_TERMS if x in text]
    sentiment=[x for x in PURE_SENTIMENT_TERMS if x in text]
    clicks=int(click_count or 0) if str(click_count or "").isdigit() else 0
    comments=int(comment_count or 0) if str(comment_count or "").isdigit() else 0
    score=min(60,12*len(set(matched))) + min(20, comments*2) + min(20, clicks//500)
    if matched:
        category="RESEARCH_SIGNAL"
        priority="HIGH" if score>=40 else "MEDIUM" if score>=20 else "LOW"
        return True,category,priority,score,matched,sentiment
    return False,"PURE_SENTIMENT_OR_LOW_INFORMATION","NONE",0,matched,sentiment

def code_for(symbol):
    code, market = symbol.split(".")
    if market == "HK":
        return "hk" + code.zfill(5)
    return code

def parse_json_response(resp):
    try:
        return resp.json()
    except Exception:
        text=resp.text.strip()
        m=re.search(r'^[^(]*\((.*)\)\s*;?$',text,re.S)
        if not m:
            raise ValueError("NON_JSON_GUBA_RESPONSE")
        return json.loads(m.group(1))

def collect(universe_file,output,limit=20,delay=0.8,session=None):
    u=load_universe(universe_file)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    s=session or requests.Session()
    s.headers.update({
        "User-Agent":"Mozilla/5.0 (compatible; E36PublicResearch/1.0; research-only)",
        "Accept":"application/json,text/plain,*/*",
        "Referer":"https://guba.eastmoney.com/",
    })
    rows=[];checks=[]
    for symbol in u["active"]:
        code=code_for(symbol)
        rec={"symbol":symbol,"source":"EASTMONEY_GUBA_DIRECT","checked_utc":datetime.now(timezone.utc).isoformat(),
             "status":"NOT_ATTEMPTED","candidate_count":0}
        try:
            params={"code":code,"type":"0","index":"1","pageSize":str(limit),
                    "deviceid":"100","version":"200","product":"Guba","plat":"Web"}
            r=s.get(API,params=params,timeout=(8,20),allow_redirects=True)
            rec["http_status"]=r.status_code
            rec["response_url"]=r.url
            if r.status_code in (401,403,429):
                rec["status"]="ACCESS_RESTRICTED"
            elif r.status_code!=200:
                rec["status"]="HTTP_ERROR"
            elif len(r.content)>2*1024*1024:
                rec["status"]="RESPONSE_TOO_LARGE"
            else:
                obj=parse_json_response(r)
                items=obj.get("re") or obj.get("data") or []
                if isinstance(items,dict):
                    items=items.get("list") or items.get("re") or []
                if not isinstance(items,list):
                    items=[]
                before=len(rows)
                for item in items:
                    if not isinstance(item,dict): continue
                    title=str(item.get("post_title") or item.get("title") or "").strip()
                    post_id=str(item.get("post_id") or item.get("id") or "").strip()
                    if not title: continue
                    qualified,category,priority,signal_score,matched_terms,sentiment_terms=qualify(
                        title,item.get("post_click_count"),item.get("post_comment_count"))
                    rows.append({
                        "symbol":symbol,
                        "source":"EASTMONEY_GUBA_DIRECT",
                        "post_id":post_id or None,
                        "title":title[:500],
                        "published_at":item.get("post_publish_time") or item.get("publish_time"),
                        "updated_at":item.get("post_last_time") or item.get("last_time"),
                        "author":item.get("user_nickname") or item.get("user_name"),
                        "click_count":item.get("post_click_count"),
                        "comment_count":item.get("post_comment_count"),
                        "like_count":item.get("post_like_count"),
                        "url":("https://guba.eastmoney.com/news,"+code+","+post_id+".html") if post_id else None,
                        "market_code": code,
                        "verification_state":"UNVERIFIED_DISCOVERY",
                        "raw_post_verified":False,
                        "issuer_fact_verified":False,
                        "may_directly_change_main_or_trade":False,
                        "quality_category":category,
                        "shadow_verification_priority":priority,
                        "signal_score":signal_score,
                        "matched_research_terms":matched_terms,
                        "matched_sentiment_terms":sentiment_terms,
                        "qualified_for_shadow_verification":qualified,
                    })
                rec["candidate_count"]=len(rows)-before
                rec["status"]="DIRECT_POSTS_FOUND" if rec["candidate_count"] else "DIRECT_EMPTY_OR_UNSUPPORTED"
                if isinstance(obj,dict):
                    rec["response_rc"]=obj.get("rc")
        except requests.RequestException as e:
            rec.update(status="REQUEST_FAILED",error_type=type(e).__name__)
        except Exception as e:
            rec.update(status="PARSE_FAILED",error_type=type(e).__name__,error=str(e)[:300])
        checks.append(rec)
        if delay: time.sleep(delay)

    result={
        "schema":"E36_COMMUNITY_DIRECT_DISCOVERY/v2",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "universe_sha256":u["universe_sha256"],
        "research_only":True,
        "may_directly_change_main_or_trade":False,
        "live_platform_coverage":False,
        "source":"EASTMONEY_GUBA_DIRECT",
        "symbols_checked":len(checks),
        "symbols_with_posts":sum(1 for r in checks if r["status"]=="DIRECT_POSTS_FOUND"),
        "lead_count":len(rows),
        "rows":rows,
        "checks":checks,
    }
    (out/"COMMUNITY_DIRECT_DISCOVERY.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    qualified=[r for r in rows if r.get("qualified_for_shadow_verification")]
    queue={
        "schema":"E36_COMMUNITY_QUALIFIED_QUEUE/v1",
        "generated_utc":result["generated_utc"],
        "research_only":True,
        "may_directly_change_main_or_trade":False,
        "requires_shadow_verification":True,
        "source":result["source"],
        "qualified_count":len(qualified),
        "symbols_with_qualified_leads":sorted({r["symbol"] for r in qualified}),
        "rows":sorted(qualified,key=lambda r:(r.get("signal_score") or 0),reverse=True)
    }
    (out/"COMMUNITY_QUALIFIED_QUEUE.json").write_text(json.dumps(queue,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--universe-file",default="config/research_universe.json")
    p.add_argument("--output",default="output/community")
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--delay",type=float,default=0.8)
    a=p.parse_args()
    r=collect(a.universe_file,a.output,max(5,min(a.limit,50)),max(0.5,a.delay))
    print(json.dumps({"symbols_checked":r["symbols_checked"],"symbols_with_posts":r["symbols_with_posts"],"leads":r["lead_count"]},ensure_ascii=False))
    raise SystemExit(0 if r["symbols_with_posts"]>0 and r["lead_count"]>0 else 2)
