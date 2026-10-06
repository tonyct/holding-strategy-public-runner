"""Read-only Eastmoney announcement discovery for A shares.

This is a secondary discovery index only. It never certifies issuer original
bytes and must not be used as a substitute for CNINFO/SSE/SZSE filings.
"""
from __future__ import annotations
import re,time
from datetime import datetime

URL="https://np-anotice-stock.eastmoney.com/api/security/ann"
UA="E36ResearchReadOnly/1.0"

class SecondaryAnnouncementError(RuntimeError): pass

def _get(session,params,attempts=3,sleep=time.sleep):
    try:
        import requests
    except ImportError as exc:
        raise SecondaryAnnouncementError("REQUESTS_NOT_INSTALLED") from exc
    last=None
    for attempt in range(max(1,attempts)):
        try:
            r=session.get(URL,params=params,headers={
                "User-Agent":UA,"Referer":"https://data.eastmoney.com/",
                "Accept":"application/json,text/plain,*/*"},
                timeout=(5,18),allow_redirects=False)
            if r.status_code in (408,429,500,502,503,504):
                last="HTTP_"+str(r.status_code)
                if attempt+1<attempts:
                    retry=r.headers.get("Retry-After")
                    delay=float(retry) if retry and str(retry).isdigit() else min(6,1.3*(2**attempt))
                    sleep(delay);continue
            r.raise_for_status()
            if len(r.content)>3*1024*1024:
                raise SecondaryAnnouncementError("EASTMONEY_RESPONSE_TOO_LARGE")
            return r.json()
        except (requests.RequestException,ValueError,SecondaryAnnouncementError) as exc:
            last=type(exc).__name__+":"+str(exc)[:160]
            if attempt+1<attempts:sleep(min(6,1.3*(2**attempt)))
    raise SecondaryAnnouncementError(last or "EASTMONEY_REQUEST_FAILED")

def query(code,start,end,session=None,max_pages=20,attempts=3,sleep=time.sleep):
    if not re.fullmatch(r"\d{6}",code): raise ValueError("BAD_A_SHARE_CODE")
    if not re.fullmatch(r"\d{8}",start) or not re.fullmatch(r"\d{8}",end):
        raise ValueError("BAD_DATE_RANGE")
    start_iso=f"{start[:4]}-{start[4:6]}-{start[6:]}"
    end_iso=f"{end[:4]}-{end[4:6]}-{end[6:]}"
    if session is None:
        try:
            import requests
        except ImportError as exc:
            raise SecondaryAnnouncementError("REQUESTS_NOT_INSTALLED") from exc
        s=requests.Session()
    else:
        s=session
    out=[]; total=None
    for page in range(1,max_pages+1):
        j=_get(s,{"sr":"-1","page_size":"50","page_index":str(page),
                  "ann_type":"A","client_source":"web","stock_list":code},
               attempts=attempts,sleep=sleep)
        data=j.get("data") or {}
        rows=data.get("list") or []
        if not isinstance(rows,list): raise SecondaryAnnouncementError("EASTMONEY_SCHEMA")
        try: total=int(data.get("total_hits") or 0)
        except (ValueError,TypeError): total=0
        if not rows: break
        for row in rows:
            if not isinstance(row,dict): continue
            date=str(row.get("notice_date") or "")[:10]
            if not (start_iso<=date<=end_iso): continue
            title=re.sub(r"<[^>]+>","",str(row.get("title") or "")).strip()
            art=str(row.get("art_code") or "").strip()
            codes={str(x.get("stock_code") or "") for x in (row.get("codes") or []) if isinstance(x,dict)}
            if codes and code not in codes: continue
            if not title or not art: continue
            cols=row.get("columns") or []
            types=[str(x.get("column_name") or "").strip() for x in cols if isinstance(x,dict) and x.get("column_name")]
            out.append({"title":title,"announced_at":date,"art_code":art,
                        "type_name":"、".join(types),
                        "url":f"https://data.eastmoney.com/notices/detail/{code}/{art}.html",
                        "source":"EASTMONEY_SECONDARY_DISCOVERY"})
        if len(out)>=total: break
        # Results are reverse chronological. Once every returned row is older
        # than the requested start, later pages cannot add in-window records.
        page_dates=[str(x.get("notice_date") or "")[:10] for x in rows if isinstance(x,dict)]
        if page_dates and all(d and d<start_iso for d in page_dates): break
        if page>=max_pages:
            raise SecondaryAnnouncementError("EASTMONEY_PAGINATION_CAP_REACHED")
        sleep(.2)
    dedup={(x["announced_at"],re.sub(r"\s+","",x["title"]).casefold()):x for x in out}
    return list(dedup.values()), total
