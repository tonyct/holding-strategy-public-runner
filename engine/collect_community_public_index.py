"""Low-frequency public web-index discovery for the E36 community research queue.

Searches the public Bing RSS representation, not community-platform endpoints.
Search snippets are discovery leads only; never claim complete/current platform coverage.
"""
import argparse,base64,json,re,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,urlparse,parse_qs,unquote
import requests
from universe import load_universe
from community_sources import classify,ingest

NAMES={"600941.SH":"中国移动","148.HK":"建滔集团","001286.SZ":"陕西能源",
"603993.SH":"洛阳钼业","2233.HK":"西部水泥","3933.HK":"联邦制药",
"9926.HK":"康方生物","600499.SH":"科达制造","600795.SH":"国电电力",
"603871.SH":"嘉友国际","601857.SH":"中国石油"}
DOMAINS={
    "xueqiu":"xueqiu.com",
    "eastmoney":"guba.eastmoney.com",
    "weibo":"weibo.com",
    "futu":"futunn.com",
}
QUERY_TEMPLATES={
    "xueqiu":'site:xueqiu.com "{name}" 股票 讨论',
    "eastmoney":'site:guba.eastmoney.com/news "{name}"',
    "weibo":'site:weibo.com "{name}" 股票',
    "futu":'site:futunn.com/post "{name}"',
}
RSS="https://www.bing.com/search"

def specific_lead_url(source,url):
    try:
        p=urlparse(url)
        path=p.path or "/"
        if source=="xueqiu":
            return not path.startswith("/S/") and path!="/"
        if source=="eastmoney":
            return "news" in path.lower()
        if source=="futu":
            return "/post" in path.lower()
        if source=="weibo":
            return path not in ("","/")
    except Exception:
        return False
    return False

def unwrap_search_url(url):
    """Resolve common Bing result redirect wrappers without fetching the target."""
    if not isinstance(url,str) or not url:
        return url
    try:
        p=urlparse(url)
        host=(p.hostname or "").lower()
        if host not in ("bing.com","www.bing.com","cn.bing.com"):
            return url
        qs=parse_qs(p.query)
        for key in ("u","url","r","target"):
            for raw in qs.get(key,[]):
                cand=unquote(raw)
                if cand.startswith(("http://","https://")):
                    return cand
                # Bing often encodes the destination as a1<urlsafe-base64>.
                if cand.startswith("a1"):
                    enc=cand[2:]
                    enc += "="*((4-len(enc)%4)%4)
                    try:
                        dec=base64.urlsafe_b64decode(enc.encode()).decode("utf-8","replace")
                    except Exception:
                        continue
                    if dec.startswith(("http://","https://")):
                        return dec
    except Exception:
        return url
    return url

def parse_rss(data,source,symbol,limit=5,diagnostics=None):
    root=ET.fromstring(data)
    if root.tag!="rss":raise ValueError("NON_RSS_SEARCH_RESPONSE")
    rows=[]
    items=root.findall("./channel/item")
    if diagnostics is not None:diagnostics["raw_items"]=len(items)
    wrong_host=0;generic=0;empty=0;wrong_host_samples=[]
    for item in items:
        raw_url=(item.findtext("link") or "").strip()
        url=unwrap_search_url(raw_url)
        if classify(url)!=source:
            wrong_host+=1
            if len(wrong_host_samples)<3:
                wrong_host_samples.append({"raw_url":raw_url[:1000],"unwrapped_url":url[:1000],"classified_as":classify(url)})
            continue
        if not specific_lead_url(source,url):
            generic+=1
            continue
        title=re.sub("<[^>]+>","",item.findtext("title") or "").strip()
        desc=re.sub("<[^>]+>","",item.findtext("description") or "").strip()
        if not title and not desc:
            empty+=1
            continue
        rows.append({"symbol":symbol,"source":source,"url":url,
            "title":title[:240],"snippet":desc[:1500],
            "published_at":item.findtext("pubDate"),
            "evidence_scope":"PUBLIC_INDEX_SNIPPET"})
        if len(rows)>=limit:break
    if diagnostics is not None:
        diagnostics.update(filtered_wrong_host=wrong_host,filtered_generic_landing=generic,filtered_empty=empty,accepted_before_dedup=len(rows),wrong_host_samples=wrong_host_samples)
    return rows

def collect(universe_file,output,per_query=5,delay=1.0,session=None):
    u=load_universe(universe_file)
    if set(u["active"])-set(NAMES):raise ValueError("STOCK_NAME_MAPPING_MISSING")
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    all_rows=[];checks=[]
    session=session or requests.Session()
    session.headers.update({"User-Agent":"E36ResearchPublicIndex/1.0 (+read-only research; low frequency)",
                            "Accept":"application/rss+xml, application/xml;q=0.9"})
    for symbol in u["active"]:
        for source,domain in DOMAINS.items():
            query=QUERY_TEMPLATES[source].format(name=NAMES[symbol])
            url=RSS+"?"+urlencode({"q":query,"format":"rss"})
            receipt={"symbol":symbol,"source":source,"query":query,
                "checked_utc":datetime.now(timezone.utc).isoformat(),"status":"NOT_ATTEMPTED"}
            try:
                with session.get(url,timeout=(8,18),allow_redirects=False) as resp:
                    receipt["http_status"]=resp.status_code
                    if resp.status_code in (401,403,429):
                        receipt["status"]="SEARCH_ACCESS_RESTRICTED"
                    elif resp.status_code!=200:
                        receipt["status"]="SEARCH_HTTP_ERROR"
                    elif len(resp.content)>1024*1024:
                        receipt["status"]="SEARCH_RESPONSE_TOO_LARGE"
                    else:
                        found=parse_rss(resp.content,source,symbol,per_query,receipt)
                        all_rows.extend(found)
                        receipt.update(status="INDEXED_LEADS_FOUND" if found else ("SEARCH_RETURNED_NO_RESULTS" if receipt["raw_items"]==0 else "SEARCH_RESULTS_FILTERED"),
                                       candidates=len(found))
            except (requests.RequestException,ValueError,ET.ParseError) as exc:
                receipt.update(status="SEARCH_REQUEST_OR_PARSE_FAILED",error_type=type(exc).__name__)
            checks.append(receipt)
            if delay:time.sleep(delay)
    candidates=out/"PUBLIC_SEARCH_CANDIDATES.json"
    candidates.write_text(json.dumps({"schema":"E36_COMMUNITY_CANDIDATES/v1","rows":all_rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    queue=ingest(universe_file,candidates,out/"COMMUNITY_RESEARCH_QUEUE.json")
    report={"schema":"E36_COMMUNITY_PUBLIC_INDEX_SCAN/v1",
       "generated_utc":datetime.now(timezone.utc).isoformat(),
       "universe_sha256":u["universe_sha256"],"checks_expected":len(u["active"])*len(DOMAINS),
       "checks_completed":len(checks),"lead_count":queue["accepted_count"],
       "index_success_count":sum(x["status"] in ("INDEXED_LEADS_FOUND","SEARCH_RETURNED_NO_RESULTS","SEARCH_RESULTS_FILTERED") for x in checks),
       "source_counts":{s:sum(r["source"]==s for r in queue["rows"]) for s in DOMAINS},
       "live_platform_coverage":False,"research_only":True,"rows":checks}
    (out/"PUBLIC_INDEX_SCAN_RECEIPT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--universe-file",default="config/research_universe.json")
    p.add_argument("--output",default="output/community")
    p.add_argument("--per-query",type=int,default=5)
    p.add_argument("--delay",type=float,default=1.0)
    a=p.parse_args()
    r=collect(a.universe_file,a.output,max(1,min(a.per_query,10)),max(a.delay,0.5))
    print(json.dumps({"checks":r["checks_completed"],"search_accessible":r["index_success_count"],
                      "leads":r["lead_count"],"source_counts":r["source_counts"]},ensure_ascii=False))
    raise SystemExit(0 if r["index_success_count"] else 2)
