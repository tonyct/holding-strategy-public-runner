"""Bounded public A/H historical quotes; market currency and volume units explicit."""
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
        for key in ("open","high","low","close","volume"):
            row[key]=_number(row[key])
        if row.get("amount") is not None:
            row["amount"]=_number(row["amount"])
        low=Decimal(row["low"]);high=Decimal(row["high"])
        if (high<low or Decimal(row["volume"])<0 or
                (row.get("amount") is not None and Decimal(row["amount"])<0)):
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
    market=request["symbol"].rsplit(".",1)[1]
    code=request["symbol"].split(".")[0]
    hist=ak.stock_hk_hist if market=="HK" else ak.stock_zh_a_hist
    frame=hist(symbol=code.zfill(5) if market=="HK" else code,period="daily",
         start_date=request["start_date"].replace("-",""),
         end_date=request["end_date"].replace("-",""),adjust="")
    rows=[]
    for row in frame.to_dict(orient="records"):
        rows.append({"date":str(row.get("日期"))[:10],
                     "code":code,
                     "open":row.get("开盘"),"high":row.get("最高"),
                     "low":row.get("最低"),"close":row.get("收盘"),
                     "volume":(str(row.get("成交量")) if market=="HK"
                                else str(Decimal(str(row.get("成交量"))) * Decimal("100"))),
                     "amount":row.get("成交额"),
                     "adjustflag":"3"})
        if len(rows)>400:raise ValueError("PROVIDER_ROW_LIMIT")
    return rows

def _yahoo_chart(request):
    """Bounded HKD/USD OHLCV history. Provider has no turnover amount."""
    import requests
    import datetime as dt
    from zoneinfo import ZoneInfo
    symbol=request["symbol"]
    if not symbol.endswith((".HK",".US")):
        raise ValueError("YAHOO_CHART_ONLY_VALIDATED_FOR_HK_US")
    hk=symbol.endswith(".HK")
    code=symbol.split(".")[0]
    provider_symbol=code.zfill(4)+".HK" if hk else code
    zone=ZoneInfo("Asia/Hong_Kong" if hk else "America/New_York")
    currency="HKD" if hk else "USD"
    start=dt.date.fromisoformat(request["start_date"])
    end=dt.date.fromisoformat(request["end_date"])
    period1=int(dt.datetime.combine(start,dt.time.min,zone).timestamp())
    period2=int(dt.datetime.combine(end+dt.timedelta(days=1),dt.time.min,zone).timestamp())
    errors=[]
    for host in ("query2.finance.yahoo.com","query1.finance.yahoo.com"):
        try:
            url="https://"+host+"/v8/finance/chart/"+provider_symbol
            resp=requests.get(url,params={"period1":period1,"period2":period2,
                 "interval":"1d","events":"history"},timeout=(5,15),
                 headers={"Accept":"application/json",
                          "User-Agent":"Mozilla/5.0 (compatible; PublicResearch/1.0)"},
                 allow_redirects=False)
            if resp.status_code!=200 or len(resp.content)>2_000_000:
                raise ValueError("YAHOO_HTTP_OR_SIZE_"+str(resp.status_code))
            blocks=(resp.json().get("chart") or {}).get("result") or []
            if len(blocks)!=1:raise ValueError("YAHOO_RESULT_AMBIGUOUS_OR_EMPTY")
            block=blocks[0];meta=block.get("meta") or {}
            if meta.get("currency")!=currency or meta.get("symbol")!=provider_symbol:
                raise ValueError("YAHOO_CURRENCY_OR_SYMBOL_MISMATCH")
            stamps=block.get("timestamp") or []
            quotes=((block.get("indicators") or {}).get("quote") or [{}])[0]
            if any(len(quotes.get(k) or [])<len(stamps) for k in ("open","high","low","close","volume")):
                raise ValueError("YAHOO_PRICE_VECTOR_INCOMPLETE")
            result=[]
            for i,epoch in enumerate(stamps):
                day=dt.datetime.fromtimestamp(int(epoch),dt.timezone.utc).astimezone(zone).date()
                if not start<=day<=end:continue
                row={"date":day.isoformat(),"code":code,
                     "open":quotes["open"][i],"high":quotes["high"][i],
                     "low":quotes["low"][i],"close":quotes["close"][i],
                     "volume":quotes["volume"][i],"amount":None,"adjustflag":"3"}
                if any(row[k] is None for k in ("open","high","low","close","volume")):
                    continue
                result.append(row)
                if len(result)>400:raise ValueError("YAHOO_ROW_LIMIT")
            return result
        except Exception as exc:
            errors.append(type(exc).__name__+":"+str(exc)[:100])
    raise RuntimeError("YAHOO_CHART_ALL_HOSTS_FAILED:"+";".join(errors))

def fetch_quotes(request):
    selected=request.get("source","AUTO")
    hk=request["symbol"].endswith(".HK")
    us=request["symbol"].endswith(".US")
    names=(["yahoo_chart"] if us else ["akshare","yahoo_chart"] if hk else ["baostock","akshare"]) if selected=="AUTO" else [selected]
    if (hk or us) and "baostock" in names:
        raise ValueError("NON_A_SHARE_BAOSTOCK_NOT_SUPPORTED")
    if us and any(source!="yahoo_chart" for source in names):
        raise ValueError("US_ONLY_SUPPORTS_YAHOO_CHART")
    attempts=[]
    for source in names:
        try:
            handler={"baostock":_baostock,"akshare":_akshare,"yahoo_chart":_yahoo_chart}.get(source)
            if handler is None:raise ValueError("UNKNOWN_APPROVED_SOURCE")
            rows=handler(request)
            if not rows:
                attempts.append({"source":source,"outcome":"EMPTY"})
                continue
            rows=_validate(rows,request)
            missing_turnover=any(row.get("amount") is None for row in rows)
            return rows,{"required":2 if missing_turnover else 1,
                         "fetched":1,"source_used":source,
                         "fetch_state":"RAW_QUOTES_FETCHED_UNVERIFIED",
                         "source_attempts":attempts,
                         "missing_fields":["amount"] if missing_turnover else [],
                         "quote_currency":"HKD" if hk else "USD" if us else "CNY",
                         "normalized_volume_unit":"shares" if us else "AS_RETURNED" if hk else "shares",
                         "provider_raw_volume_unit":("shares" if us else "AS_RETURNED" if hk else
                           "lots_of_100_shares" if source=="akshare" else "shares")}
        except Exception as exc:
            attempts.append({"source":source,"outcome":"FAILED",
                             "reason":type(exc).__name__+":"+str(exc)[:120]})
    return [],{"required":1,"fetched":0,"source_attempts":attempts,
               "gap_reason":"ALL_ALLOWED_QUOTE_SOURCES_UNAVAILABLE"}
