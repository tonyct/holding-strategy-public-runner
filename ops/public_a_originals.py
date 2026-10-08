"""Fetch current-window CNINFO original PDFs for the public research universe."""
import argparse,hashlib,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs

def load_universe(path):
    raw=Path(path).read_bytes();u=json.loads(raw)
    if u.get("schema")!="E36_PUBLIC_RESEARCH_UNIVERSE/v1" or u.get("strategy_id")!="PUBLIC_COMPANY_RESEARCH":
        raise ValueError("PUBLIC_UNIVERSE_INVALID")
    symbols=[x["symbol"] for x in u.get("stocks",[]) if x.get("active") and x["symbol"].endswith((".SH",".SZ"))]
    if not symbols or len(symbols)!=len(set(symbols)): raise ValueError("PUBLIC_A_SCOPE_INVALID")
    return symbols,hashlib.sha256(raw).hexdigest()

def targets(index_dir,symbols):
    root=Path(index_dir);r=json.loads((root/"ANNOUNCEMENT_RECEIPT.json").read_text())
    if r.get("schema")!="E36_A_ANNOUNCEMENT_INDEX/v1": raise ValueError("A_INDEX_SCHEMA_INVALID")
    by={x.get("symbol"):x for x in r.get("rows",[])}
    if set(by)!=set(symbols): raise ValueError("A_INDEX_SCOPE_MISMATCH")
    out={}
    for symbol in symbols:
        row=by[symbol];sha=row.get("sha256")
        if not isinstance(sha,str) or not re.fullmatch(r"[0-9a-f]{64}",sha): out[symbol]=[];continue
        p=root/(symbol.replace(".","_")+"_"+sha[:12]+".json")
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha: raise ValueError("A_INDEX_HASH_MISMATCH:"+symbol)
        doc=json.loads(raw);seen=set();items=[]
        for x in doc.get("items",[]):
            q=parse_qs(urlparse(x.get("url","")).query)
            aid=q.get("announcementId",[None])[0];code=q.get("stockCode",[None])[0]
            date=str(x.get("announced_at") or "")[:10]
            if not aid or not re.fullmatch(r"[0-9]{10}",aid) or code!=symbol[:6] or not re.fullmatch(r"20\d\d-\d\d-\d\d",date):
                continue
            if aid in seen: continue
            seen.add(aid)
            items.append({"announcement_id":aid,"date":date,"title":x.get("title"),
                "url":"https://static.cninfo.com.cn/finalpage/"+date+"/"+aid+".PDF"})
        out[symbol]=items
    return out

def fetch(session,item,symbol,out,attempts=2):
    errors=[]
    for attempt in range(attempts):
        try:
            resp=session.get(item["url"],timeout=(8,30),stream=True,allow_redirects=False,
                headers={"User-Agent":"PublicCompanyResearch/1.0","Referer":"https://www.cninfo.com.cn/"})
            if resp.status_code in (408,429,500,502,503,504) and attempt+1<attempts:
                time.sleep(min(2**attempt,3));continue
            resp.raise_for_status();data=bytearray()
            for chunk in resp.iter_content(65536):
                data.extend(chunk)
                if len(data)>30*1024*1024: raise ValueError("PDF_TOO_LARGE")
            if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-8192:]: raise ValueError("INVALID_PDF")
            sha=hashlib.sha256(data).hexdigest()
            name=symbol.replace(".","_")+"_"+item["announcement_id"]+"_"+sha[:12]+".pdf"
            (out/name).write_bytes(data)
            return {**item,"status":"FETCHED_OFFICIAL_ORIGINAL","sha256":sha,"filename":name,
                    "bytes":len(data),"identity_method":"CNINFO_OFFICIAL_INDEX_STOCKCODE_ANNOUNCEMENTID_DATE"}
        except Exception as e:
            errors.append(type(e).__name__+":"+str(e)[:120]);time.sleep(.3)
    return {**item,"status":"FETCH_FAILED","errors":errors}

def main():
    p=argparse.ArgumentParser();p.add_argument("--index-dir",required=True);p.add_argument("--output",required=True)
    p.add_argument("--universe",default="config/research_universe.json");p.add_argument("--max-per-symbol",type=int,default=20);a=p.parse_args()
    symbols,ush=load_universe(a.universe);todo=targets(a.index_dir,symbols)
    import requests
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    report={"schema":"PUBLIC_A_CURRENT_WINDOW_ORIGINALS/v1","universe_sha256":ush,
            "checked_at_utc":datetime.now(timezone.utc).isoformat(),"symbols":{}}
    with requests.Session() as s:
        for symbol in symbols:
            items=todo.get(symbol,[])[:max(1,min(a.max_per_symbol,100))]
            rows=[fetch(s,x,symbol,out) for x in items]
            report["symbols"][symbol]={"indexed":len(todo.get(symbol,[])),"attempted":len(rows),
                "fetched":sum(x.get("status")=="FETCHED_OFFICIAL_ORIGINAL" for x in rows),
                "files":rows,"complete":len(todo.get(symbol,[]))<=a.max_per_symbol and all(x.get("status")=="FETCHED_OFFICIAL_ORIGINAL" for x in rows)}
            (out/"A_ORIGINALS_RECEIPT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"symbols":len(symbols),"files":sum(x["fetched"] for x in report["symbols"].values())}))
if __name__=="__main__":main()
