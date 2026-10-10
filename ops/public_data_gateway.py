"""PUBLIC-only on-demand data gateway. No private research or investment decisions."""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "PUBLIC_DATA_GATEWAY_REQUEST/v1"
SYMBOL = re.compile(r"(?:[0-9]{6}\.(?:SH|SZ)|[0-9]{1,5}\.HK)\Z")
ID = re.compile(r"[A-Za-z0-9_-]{8,80}\Z")
from ops.public_gateway_extended import CAPABILITIES as EXTENDED, execute_extended

CATEGORIES = {
    "historical_quotes": {"adapter": "baostock", "markets": ["SH", "SZ"],
                          "source_options": ["AUTO","baostock","akshare"],
                          "fields": ["date", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]},
}
CATEGORIES.update(EXTENDED)
FORBIDDEN = {"holdings", "holding", "portfolio", "position", "quantity", "cost_basis",
             "account", "balance", "nav", "cash", "pnl", "target_price",
             "valuation", "thesis", "trade", "order", "private", "shadow_cycle_id"}

def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def digest(payload):
    return hashlib.sha256(payload).hexdigest()

def validate(request):
    if not isinstance(request, dict):
        raise ValueError("REQUEST_NOT_OBJECT")
    allowed = {"schema", "request_id", "operation", "symbol", "data_type",
               "start_date", "end_date", "source", "report_period_end"}
    if set(request) - allowed or set(request) & FORBIDDEN:
        raise ValueError("REQUEST_EXTRA_OR_PRIVATE_FIELDS")
    if request.get("schema") != SCHEMA or request.get("operation") not in ("DISCOVER", "EXECUTE"):
        raise ValueError("INVALID_SCHEMA_OR_OPERATION")
    rid = request.get("request_id")
    if not isinstance(rid, str) or not ID.fullmatch(rid):
        raise ValueError("INVALID_OPAQUE_REQUEST_ID")
    if request["operation"] == "DISCOVER":
        if set(request) != {"schema", "request_id", "operation"}:
            raise ValueError("DISCOVER_HAS_EXTRA_FIELDS")
        return
    symbol = request.get("symbol")
    category = request.get("data_type")
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise ValueError("INVALID_SYMBOL")
    if category not in CATEGORIES:
        raise ValueError("UNSUPPORTED_DATA_TYPE")
    if symbol.rsplit(".", 1)[1] not in CATEGORIES[category]["markets"]:
        raise ValueError("MARKET_NOT_SUPPORTED")
    if request.get("source", "AUTO") not in CATEGORIES[category].get("source_options", ("AUTO", CATEGORIES[category]["adapter"])):
        raise ValueError("SOURCE_NOT_SUPPORTED")
    try:
        start = dt.date.fromisoformat(request["start_date"])
        end = dt.date.fromisoformat(request["end_date"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("INVALID_DATE") from exc
    if end < start or (end - start).days > 366 or end > dt.datetime.now(dt.timezone.utc).date():
        raise ValueError("INVALID_DATE_WINDOW")
    if category=="financial_statements" and end.strftime("%m-%d") not in ("03-31","06-30","09-30","12-31"):
        raise ValueError("FINANCIAL_PERIOD_MUST_BE_QUARTER_END")
    if category=="official_filings":
        if (end-start).days > 75:
            raise ValueError("ORIGINALS_REQUIRE_75_DAY_WINDOW")
        target=request.get("report_period_end")
        if target is not None:
            if (not isinstance(target,str) or not re.fullmatch(r"20[0-9]{2}-(03-31|06-30|09-30|12-31)",target)
                    or dt.date.fromisoformat(target)>end):
                raise ValueError("INVALID_TARGET_REPORT_PERIOD")
    elif "report_period_end" in request:
        raise ValueError("REPORT_PERIOD_ONLY_FOR_ORIGINAL_FILINGS")

def execute(request):
    """Execute a bounded public-only provider request; never claim issuer validation."""
    if request["data_type"]=="historical_quotes":
        from ops.public_gateway_quotes import fetch_quotes
        return fetch_quotes(request)
    if request["data_type"]!="historical_quotes":
        return execute_extended(request)
    import baostock as bs
    symbol = request["symbol"]
    market = symbol.split(".")[1].lower()
    ticker = market + "." + symbol.split(".")[0]
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError("BAOSTOCK_LOGIN_FAILED:" + str(login.error_code))
    try:
        fields = ",".join(CATEGORIES["historical_quotes"]["fields"])
        result = bs.query_history_k_data_plus(
            ticker, fields, start_date=request["start_date"], end_date=request["end_date"],
            frequency="d", adjustflag="3")
        if result.error_code != "0":
            raise RuntimeError("BAOSTOCK_QUERY_FAILED:" + str(result.error_code))
        rows = []
        while result.next():
            rows.append(dict(zip(result.fields, result.get_row_data())))
            if len(rows) > 400:
                raise RuntimeError("ROW_LIMIT_EXCEEDED")
        if not rows:
            return [], "EMPTY_RESULT"
        return rows, "FETCHED_UNVERIFIED"
    finally:
        bs.logout()

def process(request, output):
    validate(request)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    base = {"schema": "PUBLIC_DATA_GATEWAY_RECEIPT/v1",
            "request_id": request["request_id"], "operation": request["operation"],
            "created_at_utc": utc_now(), "privacy_class": "PUBLIC_MARKET_DATA_ONLY",
            "economic_verified": False, "private_research_approved": False}
    if request["operation"] == "DISCOVER":
        base.update(status="DELIVERED", capabilities=CATEGORIES, actual_fetch_count=0)
    else:
        base.update(symbol=request["symbol"], data_type=request["data_type"],
                    provider=CATEGORIES[request["data_type"]]["adapter"],
                    requested_period=[request["start_date"], request["end_date"]])
        try:
            rows, detail = execute(request)
            meta=detail if isinstance(detail,dict) else {"fetch_state":detail}
            base["provider"]=meta.get("source_used",base["provider"])
            coverage=meta.get("fetched", 1 if rows else 0)
            required=meta.get("required", 1)
            if rows:
                state="DELIVERED" if coverage>=required else "PARTIAL"
                raw = (json.dumps({"source":base["provider"], "request": request,
                                   "rows": rows}, ensure_ascii=False, sort_keys=True) + "\n").encode()
                file = output / "RAW_RESPONSE.json"
                file.write_bytes(raw)
                base.update(status=state, fetch_state=meta.get("fetch_state","FETCHED_UNVERIFIED"),
                            source_details=meta, row_count=len(rows),
                            response_file=file.name, response_sha256=digest(raw),
                            provider_reported_source=base["provider"],
                            verification_state="RAW_API_UNVERIFIED")
            else:
                base.update(status="GAP", fetch_state="EMPTY_OR_INCOMPLETE", row_count=0,
                            source_details=meta, error_code=meta.get("gap_reason","EMPTY_RESULT"))
        except Exception as exc:
            base.update(status="GAP", fetch_state="FAILED", row_count=0,
                        error_code=str(exc)[:200], exception_type=type(exc).__name__)
    raw_receipt = (json.dumps(base, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    (output / "PUBLIC_GATEWAY_RECEIPT.json").write_bytes(raw_receipt)
    return base

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, help="Public-only JSON file path")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    receipt = process(request, args.output)
    print(json.dumps({"request_id": receipt["request_id"], "status": receipt["status"],
                      "rows": receipt.get("row_count", 0)}))

if __name__ == "__main__":
    main()
