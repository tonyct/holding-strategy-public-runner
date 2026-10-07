"""Public news-index discovery for research leads only."""
import argparse,json,re,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,urlparse
import requests
from universe import load_universe

NAMES={"600941.SH":"中国移动","148.HK":"建滔集团","001286.SZ":"陕西能源","603993.SH":"洛阳钼业","2233.HK":"西部水泥","3933.HK":"联邦制药","9926.HK":"康方生物","600499.SH":"科达制造","600795.SH":"国电电力","603871.SH":"嘉友国际","601857.SH":"中国石油"}
RSS="https://www.bing.com/search"
BLOCK_HOSTS={"xueqiu.com","guba.eastmoney.com","weibo.com","www.weibo.com","m.weibo.cn"}

def parse(data,symbol,limit):
    root=ET.fromstring(data)
    if root.tag!="rss": raise ValueError("NON_RSS_SEARCH_RESPONSE")
    rows=[]
    for item in root.findall("./channel/item"):
        url=(item.findtext("link") or "").strip()
        host=(urlparse(url).hostname or "").lower()
        if not url.startswith("https://") or host in BLOCK_HOSTS: continue
        title=re.sub("<[^>]+>","",item.findtext("title") or "").strip()
        desc=re.sub("<[^>]+>","",item.findtext("description") or "").strip()
        if not title and not desc: continue
        rows.append({"symbol":symbol,"source":"PUBLIC_WEB_INDEX","url":url,"title":title[:240],"snippet":desc[:1500],
                     "published_at":item.findtext("pubDate"),"verification_state":"UNVERIFIED_DISCOVERY",
                     "may_directly_change_main_or_trade":False})
        if len(rows)>=limit: break
    return rows

def collect(universe_file,output,per_query=8,delay=0.8):
    u=load_universe(universe_file); out=Path(output); out.mkdir(parents=True,exist_ok=True)
    rows=[];checks=[]
    s=requests.Session(); s.headers.update({"User-Agent":"E36PublicNewsDiscovery/1.0","Accept":"application/rss+xml, application/xml;q=0.9"})
    for symbol in u["active"]:
        q=f'"{NAMES[symbol]}" 股票 OR 公司 OR 行业'
        url=RSS+"?"+urlencode({"q":q,"format":"rss"})
        rec={"symbol":symbol,"query":q,"checked_utc":datetime.now(timezone.utc).isoformat()}
        try:
            r=s.get(url,timeout=(8,18),allow_redirects=False); rec["http_status"]=r.status_code
            found=parse(r.content,symbol,per_query) if r.status_code==200 else []
            rec["status"]="INDEXED_LEADS_FOUND" if found else ("SEARCH_HTTP_ERROR" if r.status_code!=200 else "SEARCH_RETURNED_NO_RESULTS")
            rec["candidates"]=len(found); rows.extend(found)
        except Exception as e:
            rec.update(status="SEARCH_REQUEST_OR_PARSE_FAILED",error_type=type(e).__name__)
        checks.append(rec); time.sleep(delay)
    result={"schema":"E36_PUBLIC_NEWS_DISCOVERY/v1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "universe_sha256":u["universe_sha256"],"research_only":True,"live_news_coverage_complete":False,
            "may_directly_change_main_or_trade":False,"lead_count":len(rows),"rows":rows,"checks":checks}
    (out/"NEWS_DISCOVERY.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--universe-file",default="config/research_universe.json"); p.add_argument("--output",default="output/news"); p.add_argument("--per-query",type=int,default=8); p.add_argument("--delay",type=float,default=0.8)
    a=p.parse_args(); r=collect(a.universe_file,a.output,max(1,min(a.per_query,12)),max(a.delay,0.5))
    print(json.dumps({"leads":r["lead_count"]},ensure_ascii=False))
