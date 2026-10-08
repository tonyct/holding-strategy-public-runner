"""Build deterministic public-only metrics from public acquisition outputs.

This module performs no valuation, portfolio, position, recommendation or trade
logic. Source verification state is inherited and never upgraded by arithmetic.
"""
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA="PUBLIC_DETERMINISTIC_METRICS/v1"

def _num(v):
    if v is None or v=="": return None
    try: return float(v)
    except (TypeError,ValueError): return None

def _ratio(a,b):
    a=_num(a); b=_num(b)
    if a is None or b in (None,0): return None
    return a/b

def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _a_snapshot(root,symbol):
    prefix=symbol.replace(".","_")+"_"
    rows=sorted((Path(root)/"a_financials/snapshots").glob(prefix+"*.json"))
    if len(rows)!=1: return None
    x=_load(rows[0]); st=x.get("statements",{})
    income=(st.get("income") or {}).get("data") or {}
    cash=(st.get("cashflow") or {}).get("data") or {}
    bal=(st.get("balance") or {}).get("data") or {}
    isf=income.get("standard_fields") or {}; csf=cash.get("standard_fields") or {}; bsf=bal.get("standard_fields") or {}
    rev=_num(isf.get("revenue") or isf.get("operating_revenue"))
    attr=_num(isf.get("attributable_net_profit")); net=_num(isf.get("net_profit"))
    ocf=_num(csf.get("operating_cashflow")); assets=_num(bsf.get("total_assets")); liabilities=_num(bsf.get("total_liabilities"))
    return {"source_file":str(rows[0].relative_to(root)),"period_end":x.get("period"),
        "currency":income.get("currency") or cash.get("currency") or bal.get("currency"),
        "source_verification_state":x.get("status") or "UNVERIFIED",
        "reported":{"revenue":rev,"attributable_net_profit":attr,"net_profit":net,
                    "operating_cashflow":ocf,"total_assets":assets,"total_liabilities":liabilities},
        "derived":{"attributable_net_margin":_ratio(attr,rev),
                   "liability_ratio":_ratio(liabilities,assets),
                   "operating_cashflow_to_attributable_profit":_ratio(ocf,attr)}}

def _rows_by_name(stmt):
    out={}
    for r in (stmt or {}).get("rows") or []:
        name=r.get("STD_ITEM_NAME")
        if name and name not in out: out[name]=_num(r.get("AMOUNT"))
    return out

def _first(mapping,names):
    for n in names:
        if mapping.get(n) is not None:return mapping[n]
    return None

def _hk_snapshot(root,symbol):
    prefix=symbol.replace(".","_")+"_"
    rows=sorted((Path(root)/"hk_financials").glob(prefix+"*.json"))
    if len(rows)!=1:return None
    x=_load(rows[0]); st=x.get("statements") or {}
    inc=_rows_by_name(st.get("income")); cash=_rows_by_name(st.get("cashflow")); bal=_rows_by_name(st.get("balance"))
    rev=_first(inc,["营业额","营业收入","收入","收益","营运收入"])
    attr=_first(inc,["股东应占溢利","本公司拥有人应占溢利","母公司拥有人应占利润"])
    net=_first(inc,["除税后溢利","净利润","持续经营业务税后利润"])
    ocf=_first(cash,["经营业务现金净额","经营活动产生的现金流量净额"])
    assets=_first(bal,["总资产","资产总计"]); liabilities=_first(bal,["总负债","负债合计"])
    return {"source_file":str(rows[0].relative_to(root)),"period_end":x.get("report_period_end"),
        "currency":x.get("currency"),"source_verification_state":"RAW_THREE_STATEMENTS_FETCHED_UNVERIFIED",
        "reported":{"revenue":rev,"attributable_net_profit":attr,"net_profit":net,
                    "operating_cashflow":ocf,"total_assets":assets,"total_liabilities":liabilities},
        "derived":{"attributable_net_margin":_ratio(attr,rev),
                   "liability_ratio":_ratio(liabilities,assets),
                   "operating_cashflow_to_attributable_profit":_ratio(ocf,attr)}}

def build(root,universe):
    root=Path(root); u=_load(universe)
    active=[x["symbol"] for x in u.get("stocks",[]) if x.get("active") is True]
    if not active or len(active)!=len(set(active)):raise ValueError("INVALID_PUBLIC_RESEARCH_UNIVERSE")
    quote_file=root/"quotes/QUOTE_RECEIPT.json"; quotes={}
    if quote_file.is_file():
        q=_load(quote_file)
        quotes={x.get("ticker"):x for x in q.get("rows",[]) if x.get("ticker")}
    stocks={}
    for symbol in active:
        fin=_hk_snapshot(root,symbol) if symbol.endswith(".HK") else _a_snapshot(root,symbol)
        q=quotes.get(symbol) or {}
        stocks[symbol]={"financials":fin or {"source_verification_state":"SOURCE_NOT_AVAILABLE"},
            "quote":{"close":_num(q.get("close")),"currency":q.get("currency"),
                     "market_session_date":q.get("market_session_date"),
                     "source_timestamp_utc":q.get("source_timestamp_utc"),
                     "source":q.get("source"),"execution_eligible":False}}
    return {"schema":SCHEMA,"scope":"PUBLIC_RESEARCH_COVERAGE_NOT_ACCOUNT_HOLDINGS",
        "computed_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "active_symbol_count":len(active),"stocks":stocks,
        "semantics":{"deterministic_arithmetic_only":True,
                     "source_verification_is_not_upgraded":True,
                     "no_valuation":True,"no_portfolio_logic":True,"no_trade_logic":True},
        "contains_account_state":False,"contains_portfolio_decision":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--universe",required=True);p.add_argument("--output",required=True)
    a=p.parse_args(); out=build(a.root,a.universe)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"schema":out["schema"],"active_symbol_count":out["active_symbol_count"]}))
if __name__=="__main__":main()
