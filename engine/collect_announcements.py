"""Collect public A-share exchange disclosure index. Zero-new result must be verified."""
import argparse
import hashlib
import json
import time
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
try:
    from .direct_cninfo import query as direct_cninfo_query
except ImportError:
    from direct_cninfo import query as direct_cninfo_query
try:
    from .announcement_secondary import query as eastmoney_announcement_query
except ImportError:
    from announcement_secondary import query as eastmoney_announcement_query
try:
    from .universe import load_universe
except ImportError:
    from universe import load_universe

def query(ak,symbol,start,end):
    code=symbol.split('.')[0]
    df=ak.stock_zh_a_disclosure_report_cninfo(symbol=code,market='沪深京',keyword='',category='',start_date=start,end_date=end)
    rows=df.to_dict(orient='records') if hasattr(df,'to_dict') else df
    result=[]
    for row in rows:
        if not isinstance(row,dict):continue
        title=row.get('公告标题') or row.get('announcementTitle')
        link=row.get('公告链接') or row.get('url')
        stamp=row.get('公告时间') or row.get('announcementTime')
        code_seen=str(row.get('代码') or row.get('secCode') or code).zfill(6)
        if code_seen!=code:continue
        if title and link:
            result.append({'title':str(title),'url':str(link),'announced_at':str(stamp) if stamp is not None else None})
    return list({item['url']:item for item in result}.values()),len(rows)

def _ann_key(item):
    title=re.sub(r"[\s\u3000]+","",str(item.get("title") or "")).casefold()
    date=str(item.get("announced_at") or "")[:10]
    return date,title

def _merge_official(primary, direct):
    out=[];seen=set()
    for item in list(primary or [])+list(direct or []):
        key=_ann_key(item)
        if not key[1] or key in seen: continue
        seen.add(key);out.append(item)
    return out

def _secondary_gap(official, secondary):
    known={_ann_key(x) for x in official or []}
    return [x for x in secondary or [] if _ann_key(x) not in known]

def verified_same_day_cache(symbol, start, end, out, root="receipts/shadow/ingestion"):
    """Use only an exact, hashed, successfully scanned SAME-DAY historical window.
    Cache is explicitly stale relative to this run and never a fresh source claim.
    """
    candidates = []
    for manifest in Path(root).glob("*/run-*/a/ANNOUNCEMENT_RECEIPT.json"):
        try:
            r = json.loads(manifest.read_text(encoding="utf-8"))
            if (r.get("schema") != "E36_A_ANNOUNCEMENT_INDEX/v1"
                    or r.get("end") != end or r.get("start", "") > start
                    or str(r.get("run_utc", ""))[:10].replace("-", "") != end):
                continue
            row = next(x for x in r.get("rows", []) if x.get("symbol") == symbol
                       and x.get("status") in ("LINKS_FETCHED_UNVERIFIED_ORIGIN",
                                               "NO_NEW_PUBLICATION_IN_WINDOW_HISTORY_VERIFIED"))
            sha = row.get("sha256", "")
            if len(sha) != 64:
                continue
            original = manifest.parent / (symbol.replace(".", "_") + "_" + sha[:12] + ".json")
            raw = original.read_bytes()
            if hashlib.sha256(raw).hexdigest() != sha:
                continue
            doc = json.loads(raw)
            if (doc.get("symbol") != symbol or doc.get("end_date") != end
                    or doc.get("start_date", "") > start
                    or doc.get("status") != row["status"]):
                continue
            candidates.append((r["run_utc"], row, raw, manifest))
        except (OSError, ValueError, KeyError, StopIteration, TypeError):
            continue
    if not candidates:
        return None
    stamp, row, raw, manifest = max(candidates, key=lambda entry: entry[0])
    path = out / (symbol.replace(".", "_") + "_" + row["sha256"][:12] + ".json")
    path.write_bytes(raw)
    return {"symbol": symbol, "status": "CACHED_VERIFIED_SAME_DAY_INDEX_PROVIDER_FAILED",
            "items": row.get("items", 0), "raw_count": row.get("raw_count", 0),
            "historical_recheck_raw_count": row.get("historical_recheck_raw_count"),
            "sha256": row["sha256"], "cached_source_scan_at": stamp,
            "cached_from": str(manifest), "fresh_current_run_scan": False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--universe-file',default='config/research_universe.json')
    p.add_argument('--output',default='output/announcements')
    p.add_argument('--start',default='20260701')
    p.add_argument('--end',default=date.today().strftime('%Y%m%d'))
    p.add_argument('--attempts',type=int,default=3)
    a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    universe=load_universe(a.universe_file)
    receipts=[]
    try:
        import akshare as ak
        install_error=None
    except ImportError as exc:
        ak=None;install_error=str(exc)
    for symbol in universe['a_shares']:
        try:
            errors=[];source_used=None
            if ak is not None:
                for attempt in range(max(1,min(a.attempts,4))):
                    try:
                        items,raw_count=query(ak,symbol,a.start,a.end)
                        source_used="AKSHARE_CNINFO"
                        break
                    except Exception as exc:
                        errors.append("AKSHARE:"+type(exc).__name__+':'+str(exc)[:140])
                        if attempt+1<max(1,min(a.attempts,4)):
                            time.sleep(min(1.5 * (2 ** attempt), 4))
                else:
                    items=None;raw_count=None
            else:
                errors.append('AKSHARE:UNAVAILABLE:'+str(install_error))
                items=None;raw_count=None
            # Wrapper failure must not become a source-family failure. Fall back
            # to CNINFO's public index directly in the same run.
            if items is None:
                try:
                    items,raw_count=direct_cninfo_query(symbol.split('.')[0],a.start,a.end)
                    source_used="DIRECT_CNINFO"
                except Exception as exc:
                    errors.append("DIRECT_CNINFO:"+type(exc).__name__+':'+str(exc)[:180])
                    raise RuntimeError('ALL_ANNOUNCEMENT_SOURCES_FAILED:'+';'.join(errors))
            # Independently query a different discovery family.  If it
            # sees announcements missing from the wrapper result, force one
            # direct CNINFO pass in the same run before declaring the official
            # index complete.  Eastmoney-only rows remain unverified leads.
            secondary=[];secondary_total=None;secondary_error=None
            try:
                secondary,secondary_total=eastmoney_announcement_query(
                    symbol.split('.')[0],a.start,a.end,
                    attempts=max(1,min(a.attempts,4)))
            except Exception as exc:
                secondary_error=type(exc).__name__+":"+str(exc)[:180]
                errors.append("EASTMONEY_SECONDARY:"+secondary_error)
            initial_secondary_gap=_secondary_gap(items,secondary)
            direct_crosscheck_used=False
            if initial_secondary_gap and source_used!="DIRECT_CNINFO":
                try:
                    direct_items,direct_count=direct_cninfo_query(
                        symbol.split('.')[0],a.start,a.end)
                    items=_merge_official(items,direct_items)
                    raw_count=max(int(raw_count or 0),int(direct_count or 0))
                    direct_crosscheck_used=True
                except Exception as exc:
                    errors.append("DIRECT_CNINFO_CROSSCHECK:"+type(exc).__name__+":"+str(exc)[:180])
            unresolved_secondary=_secondary_gap(items,secondary)
            status='LINKS_FETCHED_UNVERIFIED_ORIGIN' if items else 'EMPTY_UNCONFIRMED'
            history_count=None
            if not items and raw_count==0:
                earlier=(datetime.strptime(a.start,'%Y%m%d')-timedelta(days=160)).strftime('%Y%m%d')
                try:
                    if source_used=="DIRECT_CNINFO":
                        hist,hcount=direct_cninfo_query(symbol.split('.')[0],earlier,a.end)
                    else:
                        hist,hcount=query(ak,symbol,earlier,a.end)
                except Exception as exc:
                    errors.append("HISTORY_RECHECK:"+type(exc).__name__+':'+str(exc)[:160])
                    # A failed wide-window recheck cannot certify a zero-result window.
                    hist,hcount=[],None
                history_count=hcount
                if hist and hcount and hcount>0:
                    status='NO_NEW_PUBLICATION_IN_WINDOW_HISTORY_VERIFIED'
            if raw_count>0 and not items:
                status='SCHEMA_MISMATCH_OR_MISSING_REQUIRED_FIELDS'
            payload={'symbol':symbol,'start_date':a.start,'end_date':a.end,'status':status,
                     'items':items,'historical_recheck_raw_count':history_count,
                     'source_used':source_used,'source_attempt_errors':errors,
                     'secondary_discovery':{
                         'source':'EASTMONEY',
                         'checked':secondary_error is None,
                         'total_hits':secondary_total,
                         'in_window_items':len(secondary),
                         'initial_official_gap_count':len(initial_secondary_gap),
                         'direct_cninfo_crosscheck_used':direct_crosscheck_used,
                         'unresolved_secondary_only_count':len(unresolved_secondary),
                         'unresolved_secondary_only_leads':unresolved_secondary[:40],
                         'error':secondary_error}}
            body=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()
            digest=hashlib.sha256(body).hexdigest()
            (out/(symbol.replace('.','_')+'_'+digest[:12]+'.json')).write_bytes(body)
            receipts.append({'symbol':symbol,'status':status,'items':len(items),
                             'raw_count':raw_count,'historical_recheck_raw_count':history_count,
                             'source_used':source_used,'source_attempt_errors':errors,
                             'secondary_checked':secondary_error is None,
                             'secondary_in_window_items':len(secondary),
                             'secondary_initial_gap_count':len(initial_secondary_gap),
                             'direct_cninfo_crosscheck_used':direct_crosscheck_used,
                             'secondary_unresolved_leads':len(unresolved_secondary),
                             'sha256':digest})
        except Exception as exc:
            prior=verified_same_day_cache(symbol,a.start,a.end,out)
            if prior is not None:
                prior['current_source_error']=type(exc).__name__+':'+str(exc)[:220]
                receipts.append(prior)
            else:
                receipts.append({'symbol':symbol,'status':'ANNOUNCEMENT_QUERY_FAILED',
                                 'error':type(exc).__name__+':'+str(exc)[:220]})
        time.sleep(1.4)
    receipt={'schema':'E36_A_ANNOUNCEMENT_INDEX/v1','universe_sha256':universe['universe_sha256'],
             'run_utc':datetime.now(timezone.utc).isoformat(),'start':a.start,'end':a.end,
             'complete_original_pdf_verified':0,'rows':receipts}
    (out/'ANNOUNCEMENT_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps({'status_count':{s:sum(r['status']==s for r in receipts)
          for s in {r['status'] for r in receipts}},'total':len(receipts)},ensure_ascii=False))
    return 0 if all(r['status'] in ('LINKS_FETCHED_UNVERIFIED_ORIGIN',
        'NO_NEW_PUBLICATION_IN_WINDOW_HISTORY_VERIFIED',
        'CACHED_VERIFIED_SAME_DAY_INDEX_PROVIDER_FAILED') for r in receipts) else 1

if __name__=='__main__':raise SystemExit(main())
