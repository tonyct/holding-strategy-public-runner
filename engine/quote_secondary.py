"""Read-only third-party quote fallbacks. Never treat a provider date as exchange certification."""
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def symbol_code(ticker):
    code, market = ticker.split(".")
    return ({"SH": "sh", "SZ": "sz", "HK": "hk"}[market] +
            (code.zfill(5) if market == "HK" else code))


def parse_tencent(raw, symbols, now=None):
    now = now or datetime.now(timezone.utc)
    codes = {symbol_code(s): s for s in symbols}
    found = {}
    for m in re.finditer(r'v_([a-z]{2}\d{5,6})="([^"]*)";?', raw):
        code = m.group(1)
        ticker = codes.get(code)
        if not ticker:
            continue
        fields = m.group(2).split("~")
        if len(fields) < 31:
            continue
        target_code = ticker.split(".")[0].zfill(5 if ticker.endswith(".HK") else 6)
        if fields[2] != target_code:
            continue
        try:
            price = float(fields[3])
            if not math.isfinite(price) or price <= 0:
                raise ValueError("invalid price")
            times = [f for f in fields[28:33] if re.fullmatch(r"20\d{12}", f)]
            if not times:
                raise ValueError("source timestamp missing")
            market_dt = datetime.strptime(times[0], "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("Asia/Hong_Kong" if ticker.endswith(".HK")
                                else "Asia/Shanghai"))
            instant = market_dt.astimezone(timezone.utc)
            if instant > now + timedelta(minutes=10) or instant < now - timedelta(days=16):
                raise ValueError("stale/future source timestamp")
        except (ValueError, IndexError, OverflowError):
            continue
        found[ticker] = {"ticker": ticker, "status": "HISTORICAL_PROVIDER_QUOTE",
            "close": price, "currency": "HKD" if ticker.endswith(".HK") else "CNY",
            "market_session_date": market_dt.date().isoformat(),
            "source_timestamp_utc": instant.isoformat(),
            "fetched_at_utc": now.isoformat(),
            "source": "TENCENT_PUBLIC_QUOTES_NON_EXECUTABLE",
            "exchange_close_independently_certified": False}
    return found


def tencent_batch(symbols, session=None, now=None):
    import requests
    session = session or requests.Session()
    codes = ",".join(symbol_code(s) for s in symbols)
    r = session.get("https://qt.gtimg.cn/q=" + codes,
                    headers={"Accept": "text/plain", "User-Agent": "E36ResearchReadOnly/1.0"},
                    timeout=(5, 12), allow_redirects=False)
    if r.status_code != 200 or len(r.content) > 256 * 1024:
        raise ValueError("TENCENT_HTTP_OR_SIZE_ERROR:" + str(r.status_code))
    return parse_tencent(r.content.decode("gbk", "replace"), symbols, now)


def yahoo_one(ticker, session=None, now=None):
    import requests
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    code, market = ticker.split(".")
    symbol = code + (".SS" if market == "SH" else ".SZ" if market == "SZ"
                     else ".HK")
    if market == "HK":
        symbol = code.zfill(4) + ".HK"
    r = session.get("https://query2.finance.yahoo.com/v8/finance/chart/" + symbol,
                    params={"interval": "1d", "range": "15d"},
                    headers={"Accept": "application/json",
                             "User-Agent": "Mozilla/5.0 E36ResearchReadOnly/1.0"},
                    timeout=(5, 10), allow_redirects=False)
    if r.status_code != 200 or len(r.content) > 1024 * 1024:
        raise ValueError("YAHOO_HTTP_OR_SIZE_ERROR:" + str(r.status_code))
    j = r.json()
    result = j.get("chart", {}).get("result") or []
    if len(result) != 1:
        raise ValueError("YAHOO_CHART_EMPTY")
    chart = result[0]
    times = chart.get("timestamp") or []
    vals = (chart.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    for stamp, value in reversed(list(zip(times, vals))):
        if value is None:
            continue
        price = float(value)
        at = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        if (math.isfinite(price) and price > 0 and
            at <= now + timedelta(minutes=10) and at >= now - timedelta(days=16)):
            zone = ZoneInfo("Asia/Hong_Kong" if market == "HK" else "Asia/Shanghai")
            return {"ticker": ticker, "status": "HISTORICAL_PROVIDER_QUOTE",
                    "close": price, "currency": "HKD" if market == "HK" else "CNY",
                    "market_session_date": at.astimezone(zone).date().isoformat(),
                    "source_timestamp_utc": at.isoformat(),
                    "fetched_at_utc": now.isoformat(),
                    "source": "YAHOO_HISTORICAL_DELAYED_NON_EXECUTABLE",
                    "exchange_close_independently_certified": False}
    raise ValueError("YAHOO_NO_VALID_DATED_CLOSE")


def baostock_one(ticker, now=None):
    """Free BaoStock historical A-share fallback; no API key, explicit login/logout."""
    if ticker.endswith(".HK"):
        return None
    try:
        import baostock as bs
    except ImportError as exc:
        raise RuntimeError("BAOSTOCK_NOT_INSTALLED") from exc
    now = now or datetime.now(timezone.utc)
    code,market=ticker.split(".")
    bs_code=("sh." if market=="SH" else "sz.")+code
    start=(now-timedelta(days=16)).date().isoformat()
    end=now.date().isoformat()
    login=bs.login()
    try:
        if getattr(login,"error_code","0")!="0":
            raise RuntimeError("BAOSTOCK_LOGIN_"+str(getattr(login,"error_code","")))
        rs=bs.query_history_k_data_plus(bs_code,"date,close",start_date=start,
                                        end_date=end,frequency="d",adjustflag="3")
        if getattr(rs,"error_code","0")!="0":
            raise RuntimeError("BAOSTOCK_QUERY_"+str(getattr(rs,"error_code","")))
        rows=[]
        while rs.next():
            rows.append(rs.get_row_data())
        for date,value in reversed(rows):
            try:
                price=float(value);market_dt=datetime.strptime(date,"%Y-%m-%d").replace(
                    tzinfo=ZoneInfo("Asia/Shanghai"))
            except (ValueError,TypeError):
                continue
            at=market_dt.astimezone(timezone.utc)
            if math.isfinite(price) and price>0 and at<=now+timedelta(minutes=10) and at>=now-timedelta(days=16):
                return {"ticker":ticker,"status":"HISTORICAL_PROVIDER_QUOTE",
                        "close":price,"currency":"CNY","market_session_date":date,
                        "source_timestamp_utc":at.isoformat(),"fetched_at_utc":now.isoformat(),
                        "source":"BAOSTOCK_HISTORICAL_NON_EXECUTABLE",
                        "exchange_close_independently_certified":False}
        raise ValueError("BAOSTOCK_NO_VALID_DATED_CLOSE")
    finally:
        try:bs.logout()
        except Exception:pass
