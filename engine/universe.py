"""Public research coverage universe loader. No account or holdings semantics."""
import hashlib
import json
import re
from pathlib import Path

class UniverseError(ValueError):
    pass

def load_universe(path):
    raw = Path(path).read_bytes()
    if len(raw) > 1024 * 1024:
        raise UniverseError("UNIVERSE_TOO_LARGE")
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise UniverseError("INVALID_UNIVERSE_JSON") from exc

    if (not isinstance(obj, dict)
            or obj.get("schema") != "E36_PUBLIC_RESEARCH_UNIVERSE/v1"
            or obj.get("strategy_id") != "PUBLIC_COMPANY_RESEARCH"):
        raise UniverseError("PUBLIC_UNIVERSE_IDENTITY_MISMATCH")

    version = obj.get("universe_version")
    if not isinstance(version, str) or not version.strip():
        raise UniverseError("MISSING_UNIVERSE_VERSION")

    if obj.get("source") != "PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS":
        raise UniverseError("PUBLIC_UNIVERSE_SOURCE_MISMATCH")

    stocks = obj.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        raise UniverseError("EMPTY_OR_INVALID_UNIVERSE")

    seen, active, inactive = set(), [], []
    for entry in stocks:
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("symbol"), str)
                or type(entry.get("active")) is not bool):
            raise UniverseError("INVALID_STOCK_ENTRY")
        symbol = entry["symbol"].strip().upper()
        if not re.fullmatch(r"(?:\d{6}\.(?:SH|SZ)|\d{1,5}\.HK)", symbol):
            raise UniverseError("BAD_SYMBOL:" + symbol)
        if symbol in seen:
            raise UniverseError("DUPLICATE_SYMBOL:" + symbol)
        seen.add(symbol)
        (active if entry["active"] else inactive).append(symbol)

    if not active:
        raise UniverseError("NO_ACTIVE_STOCKS")

    return {
        "universe_version": version,
        "universe_sha256": hashlib.sha256(raw).hexdigest(),
        "source": obj["source"],
        "active": active,
        "inactive": inactive,
        "a_shares": [s for s in active if s.endswith((".SH", ".SZ"))],
        "hk_shares": [s for s in active if s.endswith(".HK")],
    }

def compare_previous(current, previous_receipt=None):
    if not previous_receipt:
        return {"status":"NO_COMPARABLE_PREVIOUS_RECEIPT","added":[],"removed":[],"retained":[]}
    try:
        old = json.loads(Path(previous_receipt).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status":"PREVIOUS_RECEIPT_UNAVAILABLE","added":[],"removed":[],"retained":[]}
    prior = set(old.get("universe_active_symbols") or [])
    now = set(current["active"])
    return {
        "status":"COMPARED",
        "added":sorted(now-prior),
        "removed":sorted(prior-now),
        "retained":sorted(now&prior),
    }
