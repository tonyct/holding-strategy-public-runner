"""Materialize independent Public research coverage without private account data.

SHADOW can request research on an arbitrary A/H symbol through the public-only
request file. Public does not know holdings, cost basis or investment decisions.
No private repository or credential is required. Only ordinary issuer tickers
are permitted; explicit requests are additive and never mutate a private pool.
"""
import argparse
import json
import re
from pathlib import Path

SYMBOL = re.compile(r"(?:[0-9]{6}\.(?:SH|SZ)|[0-9]{1,5}\.HK)\Z")
MAX_SYMBOLS = 150


def expand(universe, requests):
    if ((universe.get("schema"), universe.get("source"), universe.get("strategy_id"))
            != ("E36_PUBLIC_RESEARCH_UNIVERSE/v1",
                "PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS",
                "PUBLIC_COMPANY_RESEARCH")):
        raise ValueError("INVALID_PUBLIC_COVERAGE_UNIVERSE")
    if ((requests.get("schema"), requests.get("source")) != (
            "PUBLIC_INDEPENDENT_COVERAGE_REQUESTS/v1",
            "PUBLIC_RESEARCH_ONLY_NOT_ACCOUNT_HOLDINGS")
            or set(requests) - {"schema", "source", "symbols"}):
        raise ValueError("PUBLIC_REQUEST_SCHEMA_OR_PRIVACY_INVALID")
    symbols = requests.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError("PUBLIC_REQUEST_SYMBOLS_INVALID")
    if (any(not isinstance(t, str) or not SYMBOL.fullmatch(t) for t in symbols)
            or len(symbols) != len(set(symbols))):
        raise ValueError("PUBLIC_REQUEST_SYMBOL_INVALID_OR_DUPLICATED")
    old = universe.get("stocks")
    if (not isinstance(old, list) or not old
            or any(not isinstance(r, dict) or set(r) != {"symbol", "active"}
                   or not isinstance(r.get("symbol"), str)
                   or type(r.get("active")) is not bool
                   or not SYMBOL.fullmatch(r["symbol"])
                   for r in old)):
        raise ValueError("PUBLIC_UNIVERSE_ROWS_INVALID")
    known = [r["symbol"] for r in old]
    if len(known) != len(set(known)) or len(known) + len(set(symbols)-set(known)) > MAX_SYMBOLS:
        raise ValueError("PUBLIC_COVERAGE_LIMIT_OR_DUPLICATE")
    result = json.loads(json.dumps(universe))
    for ticker in symbols:
        if ticker not in known:
            result["stocks"].append({"symbol": ticker, "active": True})
    return result, {"schema": "PUBLIC_COVERAGE_EXPANSION/v1",
                    "requested_count": len(symbols),
                    "added_count": len(set(symbols)-set(known)),
                    "active_symbol_count": sum(r["active"] for r in result["stocks"]),
                    "research_scope_only_not_holdings": True,
                    "no_private_repo_dependency": True,
                    "automatic_fact_approval": False,
                    "automatic_trade_execution": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--requests", required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args()
    source = Path(args.universe)
    new, receipt = expand(json.loads(source.read_bytes()),
                          json.loads(Path(args.requests).read_bytes()))
    source.write_text(json.dumps(new, ensure_ascii=False, indent=2)+"\n")
    if args.receipt:
        p = Path(args.receipt)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
