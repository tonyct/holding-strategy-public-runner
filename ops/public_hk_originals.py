"""Fetch public HKEX index rows and current-window original PDFs."""
import argparse,hashlib,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
API="https://www1.hkexnews.hk/search/titleSearchServlet.do";ROOT="https://www1.hkexnews.hk"

def load_scope(universe_path,map_path):
    u=json.loads(Path(universe_path).read_text());m=json.loads(Path(map_path).read_text())
    if u.get("schema")!="E36_PUBLIC_RESEARCH_UNIVERSE/v1" or m.get("schema")!="PUBLIC_HKEX_ISSUER_ID_MAP/v1":
        raise ValueError("PUBLIC_HK_CONFIG_INVALID")
    symbols=[x["symbol"] for x in u.get("stocks",[]) if x.get("active") and x["symbol"].endswith(".HK")]
    out={}
    for s in symbols:
        row=(m.get("issuers") or {}).get(s)
        if not row:
            # A newly added HK issuer must not stop every other HK retrieval.
            # SHADOW may use targeted public search and extend this PUBLIC map
            # only after identifying the exchange's real stock_id and issuer.
            out[s]=(None,())
            continue
        if not row.get("stock_id") or not row.get("issuer_names"):
            raise ValueError("HKEX_MAP_ENTRY_INCOMPLETE:"+s)
        out[s]=(str(row["stock_id"]),tuple(row["issuer_names"]))
    return out

def index(session,symbol,stock_id,start,end):
    params={"sortDir":"0","sortByOptions":"DateTime","category":"0","market":"SEHK","stockId":stock_id,
      "documentType":"-1","fromDate":start,"toDate":end,"title":"","searchType":"0",
      "t1code":"-2","t2Gcode":"-2","t2code":"-2","rowRange":"250","lang":"E"}
    r=session.get(API,params=params,timeout=(10,35),headers={"Referer":ROOT+"/search/titlesearch.xhtml","Accept":"application/json","User-Agent":"PublicCompanyResearch/1.0"})
    r.raise_for_status();j=r.json();rows=j.get("result");rows=json.loads(rows) if isinstance(rows,str) else rows
    if not isinstance(rows,list) or j.get("hasNextRow") or len(rows)>=250: raise ValueError("HKEX_INDEX_PAGINATION_OR_SCHEMA")
    expected=str(int(symbol.split(".")[0]));out=[]
    for row in rows:
        codes=[str(int(x)) for x in re.findall(r"\b\d{1,5}\b",re.sub(r"<[^>]*>"," ",str(row.get("STOCK_CODE",""))))]
        if expected not in codes: continue
        url=urljoin(ROOT,row.get("FILE_LINK",""));p=urlparse(url)
        if p.scheme!="https" or p.hostname not in ("www1.hkexnews.hk","www.hkexnews.hk","hkexnews.hk") or not p.path.lower().endswith(".pdf"): continue
        out.append({"announcement_id":str(row.get("NEWS_ID","")),"title":re.sub(r"<[^>]*>"," ",str(row.get("TITLE",""))),
                    "published_at":str(row.get("DATE_TIME","")),"url":url})
    return out

def fetch(session,item,symbol,names,out):
    try:
        r=session.get(item["url"],stream=True,timeout=(10,50),allow_redirects=False,
          headers={"User-Agent":"PublicCompanyResearch/1.0","Referer":ROOT+"/"});r.raise_for_status()
        data=bytearray()
        for chunk in r.iter_content(65536):
            data.extend(chunk)
            if len(data)>35*1024*1024: raise ValueError("PDF_TOO_LARGE")
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-8192:]: raise ValueError("INVALID_PDF")
        import fitz
        with fitz.open(stream=bytes(data),filetype="pdf") as pdf:
            front="".join(pdf[i].get_text(sort=True) for i in range(min(6,pdf.page_count)));pages=pdf.page_count
        compact=re.sub(r"\s+","",front).upper()
        identity=any(re.sub(r"\s+","",n).upper() in compact for n in names)
        sha=hashlib.sha256(data).hexdigest();name=symbol.replace(".","_")+"_"+(item["announcement_id"] or sha[:10])+"_"+sha[:12]+".pdf"
        (out/name).write_bytes(data)
        return {**item,"status":"FETCHED_OFFICIAL_ORIGINAL","identity_verified":identity,"sha256":sha,"filename":name,"bytes":len(data),"pages":pages}
    except Exception as e:
        return {**item,"status":"FETCH_FAILED","error":type(e).__name__+":"+str(e)[:160]}

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--universe",default="config/research_universe.json")
    p.add_argument("--issuer-map",default="config/hkex_issuer_ids.json");p.add_argument("--start");p.add_argument("--end");p.add_argument("--max-per-symbol",type=int,default=25);a=p.parse_args()
    from datetime import timedelta
    now=datetime.now(timezone.utc);start=a.start or (now-timedelta(days=35)).strftime("%Y%m%d");end=a.end or now.strftime("%Y%m%d")
    scope=load_scope(a.universe,a.issuer_map);out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    import requests
    report={"schema":"PUBLIC_HK_CURRENT_WINDOW_ORIGINALS/v1","date_window":[start,end],"checked_at_utc":now.isoformat(),"symbols":{}}
    with requests.Session() as s:
        for symbol,(sid,names) in scope.items():
            if sid is None:
                report["symbols"][symbol]={"indexed":0,"attempted":0,"fetched":0,
                    "files":[],"complete":False,
                    "status":"HKEX_ISSUER_ID_DISCOVERY_REQUIRED",
                    "error":"PUBLIC_EXCHANGE_ISSUER_IDENTIFIER_UNVERIFIED"}
                (out/"HK_ORIGINALS_RECEIPT.json").write_text(
                    json.dumps(report,ensure_ascii=False,indent=2)+"\n")
                continue
            try:
                rows=index(s,symbol,sid,start,end);(out/(symbol.replace(".","_")+"_announcement_index.json")).write_text(json.dumps(rows,ensure_ascii=False,indent=2))
                chosen=rows[:max(1,min(a.max_per_symbol,100))];files=[fetch(s,x,symbol,names,out) for x in chosen]
                report["symbols"][symbol]={"indexed":len(rows),"attempted":len(files),"fetched":sum(x.get("status")=="FETCHED_OFFICIAL_ORIGINAL" for x in files),
                  "files":files,"complete":len(rows)<=a.max_per_symbol and all(x.get("status")=="FETCHED_OFFICIAL_ORIGINAL" for x in files)}
            except Exception as e: report["symbols"][symbol]={"indexed":0,"attempted":0,"fetched":0,"files":[],"complete":False,"error":type(e).__name__+":"+str(e)[:160]}
            (out/"HK_ORIGINALS_RECEIPT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
            time.sleep(.3)
    print(json.dumps({"symbols":len(scope),"files":sum(x.get("fetched",0) for x in report["symbols"].values())}))
if __name__=="__main__":main()
