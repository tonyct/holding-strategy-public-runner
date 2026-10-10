"""PUBLIC historic A-share quote source routing with bounded provider fallback."""
import datetime as dt
from decimal import Decimal, InvalidOperation

def _number(v):
    try:
        n=Decimal(str(v).replace(",",""))
        if not n.is_finite():
            raise ValueError("NOT_FINITE")
        return str(n)
    except (ValueError,InvalidOperation,TypeError):
        raise ValueError("BAD_PROVIDER_NUMERIC_VALUE")

def _validate(rows,request):
    code=request["symbol"].split(".")[0]
    lo=dt.date.fromisoformat(request["start_date"])
    hi=dt.date.fromisoformat(request["end_date"])
    seen=set()
    for row in rows:
        stamp=dt.date.fromisoformat(str(row["date"]))
        if not lo<=stamp<=hi or stamp in seen:
            raise ValueError("QUOTE_DATE_OUT_OF_SCOPE_OR_DUPLICATE")
        seen.add(stamp)
        if str(row["code"]).split(".")[-1] != code:
            raise ValueError("QUOTE_SYMBOL_MISMATCH")
        for key in ("open","high","low","close","volume","amount"):
            row[key]=_number(row[key])
        low=Decimal(row["low"]);high=Decimal(row["high"])
        if high<low or Decimal(row["volume"])<0 or Decimal(row["amount"])<0:
            raise ValueError("INVALID_QUOTE_RANGE")
    return rows

def _baostock(request):
    import baostock as bs
    code,market=request["symbol"].split(".")
    session=bs.login()
    if session.error_code!="0":
        raise RuntimeError("BAOSTOCK_LOGIN_FAILED:"+str(session.error_code))
    try:
        fields="date,code,open,high,low,close,volume,amount,adjustflag"
        result=bs.query_history_k_data_plus(market.lower()+"."+code,fields,
            start_date=request["start_date"],end_date=request["end_date"],
            frequency="d",adjustflag="3")
        if result.error_code!="0":
            raise RuntimeError("BAOSTOCK_DATA_QUERY_FAILED:"+str(result.error_code))
        rows=[]
        while result.next():
            rows.append(dict(zip(result.fields,result.get_row_data())))
            if len(rows)>400:raise ValueError("PROVIDER_ROW_LIMIT")
        return rows
    finally:
        bs.logout()

def _akshare(request):
    import akshare as ak
    frame=ak.stock_zh_a_hist(symbol=request["symbol"][:6],period="daily",
         start_date=request["start_date"].replace("-",""),
         end_date=request["end_date"].replace("-",""),adjust="")
    rows=[]
    for row in frame.to_dict(orient="records"):
        rows.append({"date":str(row.get("日期"))[:10],
                     "code":request["symbol"][:6],
                     "open":row.get("开盘"),"high":row.get("最高"),
                     "low":row.get("最低"),"close":row.get("收盘"),
                     "volume":row.get("成交量"),"amount":row.get("成交额"),
                     "adjustflag":"3"})
        if len(rows)>400:raise ValueError("PROVIDER_ROW_LIMIT")
    return rows

def fetch_quotes(request):
    selected=request.get("source","AUTO")
    names=["baostock","akshare"] if selected=="AUTO" else [selected]
    attempts=[]
    for source in names:
        try:
            rows=(_baostock if source=="baostock" else _akshare)(request)
            if not rows:
                attempts.append({"source":source,"outcome":"EMPTY"})
                continue
            rows=_validate(rows,request)
            return rows,{"required":1,"fetched":1,"source_used":source,
                         "fetch_state":"RAW_QUOTES_FETCHED_UNVERIFIED",
                         "source_attempts":attempts}
        except Exception as exc:
            attempts.append({"source":source,"outcome":"FAILED",
                             "reason":type(exc).__name__+":"+str(exc)[:120]})
    return [],{"required":1,"fetched":0,"source_attempts":attempts,
               "gap_reason":"ALL_ALLOWED_QUOTE_SOURCES_UNAVAILABLE"}
