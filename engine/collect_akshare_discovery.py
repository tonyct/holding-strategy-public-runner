"""AKShare-backed public discovery. Capability-detected, research-only, fail-soft."""
import argparse,json,traceback
from datetime import datetime,timezone
from pathlib import Path
from universe import load_universe

def scalar(v):
    if v is None: return None
    try:
        if hasattr(v,"isoformat"): return v.isoformat()
    except Exception: pass
    try:
        if str(v) in ("nan","NaT","None"): return None
    except Exception: pass
    return str(v)[:3000]

def frame_rows(df,limit):
    if df is None or getattr(df,"empty",True): return []
    out=[]
    for _,row in df.head(limit).iterrows():
        out.append({str(k):scalar(v) for k,v in row.to_dict().items()})
    return out

def collect(universe_file,output,limit=20):
    import akshare as ak
    u=load_universe(universe_file)
    result={"schema":"E36_AKSHARE_PUBLIC_DISCOVERY/v1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "universe_sha256":u["universe_sha256"],"research_only":True,
            "may_directly_change_main_or_trade":False,"news_api_available":hasattr(ak,"stock_news_em"),
            "guba_api_available":hasattr(ak,"stock_guba_em"),"rows":[]}
    for symbol in u["active"]:
        code=symbol.split(".")[0]
        rec={"symbol":symbol,"news":{"status":"API_UNAVAILABLE","rows":[]},"community":{"status":"API_UNAVAILABLE","rows":[]}}
        if result["news_api_available"]:
            try:
                rows=frame_rows(ak.stock_news_em(symbol=code),limit)
                rec["news"]={"status":"PUBLIC_ROWS_FETCHED" if rows else "NO_ROWS","rows":rows,
                             "verification_state":"UNVERIFIED_DISCOVERY","source":"AKSHARE_STOCK_NEWS_EM"}
            except Exception as e:
                rec["news"]={"status":"REQUEST_FAILED","error_type":type(e).__name__,"rows":[]}
        if result["guba_api_available"]:
            try:
                rows=frame_rows(ak.stock_guba_em(symbol=code),limit)
                rec["community"]={"status":"PUBLIC_ROWS_FETCHED" if rows else "NO_ROWS","rows":rows,
                                  "verification_state":"UNVERIFIED_DISCOVERY","source":"AKSHARE_STOCK_GUBA_EM"}
            except Exception as e:
                rec["community"]={"status":"REQUEST_FAILED","error_type":type(e).__name__,"rows":[]}
        result["rows"].append(rec)
    result["news_symbol_count"]=sum(r["news"]["status"]=="PUBLIC_ROWS_FETCHED" for r in result["rows"])
    result["community_symbol_count"]=sum(r["community"]["status"]=="PUBLIC_ROWS_FETCHED" for r in result["rows"])
    result["news_row_count"]=sum(len(r["news"].get("rows",[])) for r in result["rows"])
    result["community_row_count"]=sum(len(r["community"].get("rows",[])) for r in result["rows"])
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--universe-file",default="config/research_universe.json");p.add_argument("--output",default="output/discovery/AKSHARE_DISCOVERY.json");p.add_argument("--limit",type=int,default=20)
    a=p.parse_args();r=collect(a.universe_file,a.output,max(1,min(a.limit,50)))
    print(json.dumps({"news_api":r["news_api_available"],"guba_api":r["guba_api_available"],"news_symbols":r["news_symbol_count"],"news_rows":r["news_row_count"],"community_symbols":r["community_symbol_count"],"community_rows":r["community_row_count"]},ensure_ascii=False))
