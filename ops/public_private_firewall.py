"""Public publication firewall: private holdings AND private-derived data stay private."""
import argparse
import json
import re
from pathlib import Path

PRIVATE_KEYS = {
    "holdings", "actual_holdings", "actual_held", "user_holdings", "account_holdings",
    "account_state", "account_balance", "account_balances", "account_cash",
    "account_nav", "cash_nav", "portfolio", "portfolio_holdings", "portfolio_positions",
    "portfolio_weight", "portfolio_weights", "portfolio_risk", "portfolio_return",
    "portfolio_decision", "portfolio_action", "position", "positions", "position_size",
    "position_quantity", "position_weight", "position_cost", "cost_basis",
    "average_cost", "broker_account", "broker_order", "account_orders",
    "realized_pnl", "unrealized_pnl", "account_pnl", "user_fills",
    "rebalancing", "personal_buy_price", "personal_sell_price",
    "private_valuation", "private_assumptions", "frozen_parameters",
    "private_generation", "private_commit", "main_runtime_state",
    "shadow_private_runtime_state", "private_research_output",
    "private_research_result", "raw_shadow_cycle_id", "user_screenshot",
}
PRIVATE_FLAGS = {
    "derived_from_private", "derived_from_holdings", "contains_private_inputs",
    "contains_private_results", "contains_account_state", "contains_portfolio_decision",
}
TAINT_FIELDS = {
    "privacy_class", "classification", "source_classification",
    "input_classification", "output_classification", "data_classification",
    "source_sensitivity", "derived_from",
}
PRIVATE_MARKER = re.compile(r"^(PRIVATE|ACCOUNT|PORTFOLIO|CONFIDENTIAL|USER_SPECIFIC)(?:$|[_:/-])",re.I)
PRIVATE_TEXT = re.compile(
    r"holding-strategy-" r"data(?:-1)?|HOLDING_STRATEGY|"
    r"\b(?:actual_held|account_state|portfolio_decision|cost_basis|"
    r"position_size|cash_nav|private_commit|private_generation|"
    r"raw_shadow_cycle_id|user_screenshot)\b",re.I)
ALLOWED_REASONS = {
    "PUBLIC_REFRESH", "SHADOW_PUBLIC_DATA_STALE", "PUBLIC_BUNDLE_STALE",
    "PUBLIC_DATA_STALE", "MANUAL_PUBLIC_REFRESH", "PUBLIC_ONLY_REFRESH",
}
OPAQUE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{7,79}$")

class PrivateDataBlocked(ValueError):
    pass

def name_of(key):
    return re.sub(r"[^a-z0-9]+","_",str(key).lower()).strip("_")

def check_json(item, allow_public_routing_control=False):
    if isinstance(item,dict):
        for k,v in item.items():
            key=name_of(k)
            # Exact public schema/location exception only. This is a negative
            # authority assertion, never evidence of Private approval.
            if (allow_public_routing_control and k=="private_consumption_approved"
                and item.get("schema")=="PUBLIC_API_FIRST_FACT_ROUTING/v1"
                and v is False):
                continue
            if key in PRIVATE_KEYS or key.startswith(("private_","account_","portfolio_","broker_")):
                raise PrivateDataBlocked("PRIVATE_FIELD:"+key)
            if key in PRIVATE_FLAGS and v is not False:
                raise PrivateDataBlocked("PRIVATE_FLAG:"+key)
            if key in TAINT_FIELDS:
                values=v if isinstance(v,list) else [v]
                if any(isinstance(x,str) and (PRIVATE_MARKER.match(x) or name_of(x) in PRIVATE_KEYS or name_of(x).startswith(("user_","broker_"))) for x in values):
                    raise PrivateDataBlocked("PRIVATE_DERIVED_DATA:"+key)
            check_json(v)
    elif isinstance(item,list):
        for v in item:check_json(v)
    elif isinstance(item,str) and PRIVATE_TEXT.search(item):
        raise PrivateDataBlocked("PRIVATE_REFERENCE_IN_PUBLIC_OUTPUT")
    return True

def check_request(reason, request_id):
    if reason and reason not in ALLOWED_REASONS:
        raise PrivateDataBlocked("UNSAFE_PUBLIC_REFRESH_REASON")
    if request_id and not OPAQUE_ID.fullmatch(request_id):
        raise PrivateDataBlocked("UNSAFE_PUBLIC_REFRESH_IDENTIFIER")
    return True

def check_public_universe(obj):
    if (obj.get("schema")!="E36_PUBLIC_RESEARCH_UNIVERSE/v1"
        or obj.get("source")!="PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS"
        or obj.get("strategy_id")!="PUBLIC_COMPANY_RESEARCH"):
        raise PrivateDataBlocked("PUBLIC_UNIVERSE_SOURCE_NOT_INDEPENDENT")
    if set(obj)-{"schema","source","strategy_id","universe_version","disclaimer","stocks"}:
        raise PrivateDataBlocked("PUBLIC_UNIVERSE_UNKNOWN_TOP_FIELDS")
    for row in obj.get("stocks",[]):
        if set(row)!={"symbol","active"}:
            raise PrivateDataBlocked("PUBLIC_UNIVERSE_HAS_PRIVATE_FIELDS")
    return True

def validate(root,manifest,universe):
    check_public_universe(json.loads(Path(universe).read_text()))
    data=json.loads(Path(manifest).read_text())
    if (data.get("privacy_class")!="PUBLIC_MARKET_DATA_ONLY" or
        data.get("source_repository")!="tonyct/holding-strategy-public-runner" or
        data.get("contains_account_state") is not False or
        data.get("contains_portfolio_decision") is not False):
        raise PrivateDataBlocked("PUBLIC_MANIFEST_PRIVACY_UNVERIFIED")
    check_json(data)
    request=data.get("refresh_request")
    if request:
        check_request(request.get("reason"),request.get("request_id"))
    files=set()
    base=Path(root)
    for path in base.rglob("*"):
        if path.is_symlink():
            raise PrivateDataBlocked("PUBLIC_SYMLINK_NOT_ALLOWED")
        if not path.is_file():
            continue
        rel=path.relative_to(base).as_posix()
        if path.suffix.lower() not in {".json",".log",".pdf"}:
            raise PrivateDataBlocked("PUBLIC_UNEXPECTED_FILE_TYPE")
        if path.suffix.lower()==".json":
            check_json(
                json.loads(path.read_text(encoding="utf-8")),
                allow_public_routing_control=(rel=="compute/PUBLIC_API_FIRST_ROUTING_V1.json"),
            )
        elif path.suffix.lower()==".log":
            if PRIVATE_TEXT.search(path.read_text(encoding="utf-8")):
                raise PrivateDataBlocked("PRIVATE_TEXT_IN_PUBLIC_LOG")
        files.add(rel)
    described={str(x.get("path")) for x in data.get("files",[])}
    files.discard(Path(manifest).relative_to(base).as_posix())
    if files!=described:
        raise PrivateDataBlocked("PUBLIC_OUTPUT_INVENTORY_MISMATCH")
    return len(files)

def main():
    p=argparse.ArgumentParser()
    for key in ("root","manifest","universe"):
        p.add_argument("--"+key,required=True)
    a=p.parse_args()
    try:
        count=validate(a.root,a.manifest,a.universe)
    except (ValueError,OSError,TypeError) as e:
        # Never print rejected payload values in public workflow logs.
        raise SystemExit("PUBLIC_PRIVATE_FIREWALL_BLOCK:"+type(e).__name__)
    print("PUBLIC_PRIVATE_FIREWALL_PASS files="+str(count))

if __name__=="__main__":
    main()
