"""Direct CNINFO announcement index fallback.

Used when AKShare's wrapper fails or returns an ambiguous empty result.  This
does not bypass authentication or anti-bot controls; it calls CNINFO's public
search endpoints with bounded pagination, explicit timeouts and polite pacing.
"""
from __future__ import annotations
import re,time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

TOP="https://www.cninfo.com.cn/new/information/topSearch/query"
QUERY="https://www.cninfo.com.cn/new/hisAnnouncement/query"
UA="E36ResearchReadOnly/1.0"

class CNInfoError(RuntimeError): pass

def _post(session,url,data,timeout=(5,18),attempts=3,sleep=time.sleep):
    last=None
    for i in range(attempts):
        try:
            r=session.post(url,data=data,headers={
                "User-Agent":UA,
                "Referer":"https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search&lastPage=index",
                "Accept":"application/json,text/plain,*/*",
            },timeout=timeout,allow_redirects=False)
            if r.status_code in (408,429,500,502,503,504):
                last=f"HTTP_{r.status_code}"
                if i+1<attempts:
                    retry=r.headers.get("Retry-After")
                    delay=float(retry) if retry and retry.isdigit() else min(6,1.3*(2**i))
                    sleep(delay);continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last=type(exc).__name__+":"+str(exc)[:160]
            if i+1<attempts:sleep(min(6,1.3*(2**i)))
    raise CNInfoError(last or "CNINFO_REQUEST_FAILED")

def orgid(session,code):
    data=_post(session,TOP,{"keyWord":code,"maxNum":"10"})
    if not isinstance(data,list):raise CNInfoError("CNINFO_TOPSEARCH_SCHEMA")
    hits=[x for x in data if isinstance(x,dict) and str(x.get("code","")).startswith(code)
          and isinstance(x.get("orgId"),str) and x.get("orgId")]
    ids=list(dict.fromkeys(x["orgId"] for x in hits))
    if len(ids)!=1:raise CNInfoError("CNINFO_ORGID_NOT_UNIQUE")
    return ids[0]

def query(code,start,end,session=None,max_pages=20,sleep=time.sleep):
    if not re.fullmatch(r"\d{6}",code):raise ValueError("BAD_CNINFO_CODE")
    if not re.fullmatch(r"\d{8}",start) or not re.fullmatch(r"\d{8}",end):
        raise ValueError("BAD_CNINFO_DATE")
    if session is None:
        import requests
        s=requests.Session()
    else:
        s=session
    oid=orgid(s,code)
    column="sse" if code.startswith(("5","6","9")) else "szse"
    items=[];total=None
    for page in range(1,max_pages+1):
        j=_post(s,QUERY,{"pageNum":str(page),"pageSize":"30","column":column,
            "tabName":"fulltext","plate":"","stock":f"{code},{oid}","searchkey":"",
            "secid":"","category":"","trade":"","seDate":f"{start[:4]}-{start[4:6]}-{start[6:]}~{end[:4]}-{end[4:6]}-{end[6:]}",
            "sortName":"","sortType":"","isHLtitle":"true"},sleep=sleep)
        rows=j.get("announcements") or []
        if not isinstance(rows,list):raise CNInfoError("CNINFO_ANNOUNCEMENTS_SCHEMA")
        total=int(j.get("totalAnnouncement") or 0)
        for a in rows:
            if not isinstance(a,dict):continue
            sec=str(a.get("secCode") or code).zfill(6)
            if sec!=code:continue
            aid=str(a.get("announcementId") or "")
            adjunct=str(a.get("adjunctUrl") or "")
            title=str(a.get("announcementTitle") or "")
            ts=a.get("announcementTime")
            if not aid or not title:continue
            try:date=datetime.fromtimestamp(float(ts)/1000,tz=ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
            except (TypeError,ValueError,OverflowError):continue
            # Preserve the same CNINFO index-link contract expected by A-window.
            link=("https://www.cninfo.com.cn/new/disclosure/detail?"
                  +urlencode({"stockCode":code,"announcementId":aid,"orgId":oid,
                              "announcementTime":date}))
            items.append({"title":title,"url":link,"announced_at":date,
                          "announcement_id":aid,"adjunct_url":adjunct})
        if not j.get("hasMore") or len(items)>=total:break
        sleep(.25)
    if total is None:raise CNInfoError("CNINFO_NO_RESPONSE")
    if total>len(items) and page>=max_pages:raise CNInfoError("CNINFO_PAGINATION_CAP")
    dedup={x["announcement_id"]:x for x in items}
    return list(dedup.values()),total
