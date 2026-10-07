"""Bounded best-effort E36 historical A/H quotes, with provider session dates.

Prices are historical source readings, never executable orders or exchange-certified
final closes. Fetch failures are per symbol and cannot become a false quote.
"""
import argparse
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
try:
    from .universe import load_universe
except ImportError:  # CLI execution: python engine/collect_quotes.py
    from universe import load_universe


try:
    from .quote_secondary import tencent_batch, yahoo_one, baostock_one
except ImportError:
    from quote_secondary import tencent_batch, yahoo_one, baostock_one

def normalized_row(symbol, frame, fetched_at):
    if frame is None or not hasattr(frame, "empty") or frame.empty:
        return {"ticker": symbol, "status": "SOURCE_UNAVAILABLE_EMPTY"}
    row = frame.iloc[-1]
    date = str(row.get("日期") or row.get("date") or "").strip()[:10]
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d").date()
        if parsed > fetched_at.date() or parsed < (fetched_at - timedelta(days=15)).date():
            raise ValueError("BAD_SESSION_DATE")
        close = float(row.get("收盘") if row.get("收盘") is not None else row.get("close"))
        if not math.isfinite(close) or close <= 0:
            raise ValueError("BAD_PRICE")
    except (ValueError, TypeError, OverflowError):
        return {"ticker": symbol, "status": "SOURCE_UNAVAILABLE_BAD_SCHEMA"}
    return {"ticker": symbol, "status": "HISTORICAL_PROVIDER_QUOTE",
            "close": close, "currency": "HKD" if symbol.endswith(".HK") else "CNY",
            "market_session_date": date, "fetched_at_utc": fetched_at.isoformat(),
            "source": "AKSHARE_HISTORICAL_NON_EXECUTABLE",
            "exchange_close_independently_certified": False}


def collect(universe, source, now=None, attempts=2, delay=0.8,
            tencent_fetch=None, yahoo_fetch=None, baostock_fetch=None):
    now = now or datetime.now(timezone.utc)
    codes = list(universe["active"])
    batch_error = None
    try:
        tencent = (tencent_fetch or tencent_batch)(codes, now=now)
        if not isinstance(tencent, dict):
            raise ValueError("INVALID_BATCH_SCHEMA")
    except Exception as exc:
        tencent = {}
        batch_error = type(exc).__name__ + ":" + str(exc)[:140]
    rows = []
    start = (now - timedelta(days=15)).strftime("%Y%m%d")
    end = now.strftime("%Y%m%d")
    for symbol in codes:
        row = tencent.get(symbol)
        errors = {"tencent": batch_error or "SYMBOL_OR_TIMESTAMP_UNAVAILABLE"}
        if row is None:
            try:
                row = (yahoo_fetch or yahoo_one)(symbol, now=now)
            except Exception as exc:
                errors["yahoo"] = type(exc).__name__ + ":" + str(exc)[:130]
        if row is None:
            for attempt in range(attempts):
                try:
                    if source is None:
                        raise RuntimeError("AKSHARE_NOT_INSTALLED")
                    if symbol.endswith(".HK"):
                        frame = source.stock_hk_hist(symbol=symbol[:-3].zfill(5),
                            period="daily", start_date=start, end_date=end, adjust="")
                    else:
                        frame = source.stock_zh_a_hist(symbol=symbol[:-3],
                            period="daily", start_date=start, end_date=end, adjust="")
                    row = normalized_row(symbol, frame, now)
                    if row["status"] == "HISTORICAL_PROVIDER_QUOTE":
                        break
                    errors["akshare"] = row["status"]
                except Exception as exc:
                    errors["akshare"] = type(exc).__name__ + ":" + str(exc)[:130]
                if attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 2))
        if ((row is None or row.get("status") != "HISTORICAL_PROVIDER_QUOTE")
                and not symbol.endswith(".HK")):
            try:
                row=(baostock_fetch or baostock_one)(symbol,now=now)
            except Exception as exc:
                errors["baostock"]=type(exc).__name__+":"+str(exc)[:130]
        if row is None or row["status"] != "HISTORICAL_PROVIDER_QUOTE":
            row = {"ticker": symbol, "status": "SOURCE_UNAVAILABLE",
                   "failures": errors,
                   "source": "TENCENT_YAHOO_AKSHARE_BAOSTOCK_FALLBACK"}
        rows.append(row)
        if delay:
            time.sleep(delay)
    return {"schema": "E36_HISTORICAL_QUOTES/v1",
            "research_scope_id": "PUBLIC_COMPANY_RESEARCH",
            "checked_at_utc": now.isoformat(),
            "universe_sha256": universe["universe_sha256"],
            "rows": rows,
            "quotes_with_source_session": sum(r["status"] == "HISTORICAL_PROVIDER_QUOTE"
                                              for r in rows),
            "no_live_execution": True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--universe-file", default="config/research_universe.json")
    p.add_argument("--output", default="output/quotes/QUOTE_RECEIPT.json")
    p.add_argument("--delay", type=float, default=0.8)
    p.add_argument("--attempts", type=int, default=2)
    a = p.parse_args()
    u = load_universe(a.universe_file)
    try:
        import akshare as source
    except ImportError:
        source = None
    result = collect(u, source, attempts=max(1,min(a.attempts,4)), delay=max(0, a.delay))
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"quotes_with_session": result["quotes_with_source_session"],
                      "checked": len(result["rows"])}, ensure_ascii=False))
    return 0 if result["quotes_with_source_session"] == len(u["active"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
