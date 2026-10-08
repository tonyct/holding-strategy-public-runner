"""Deterministic cross-source comparison and explicit economic-input gap ledger.

This is public-only computation, not independent source verification.
"""
from collections import defaultdict
from decimal import Decimal
from engine.financial_fact_engine_v2 import number

FIELDS=("revenue","attributable_net_profit","operating_cash_flow","capital_expenditure",
        "assets","liabilities","issued_shares","minority_interest","interest_bearing_debt")
def reconcile(facts,required_symbols,abs_tolerance="0.01",rel_tolerance="0.000001"):
    groups=defaultdict(list)
    for f in facts:
        if f.get("kind")!="NORMALIZED_CANDIDATE":continue
        context=tuple(f.get(k) for k in ("symbol","field","currency","scope","period_start","period_end","period_type"))
        groups[context].append(f)
    output={}
    for symbol in required_symbols:
        items=[];missing=[]
        symgroups={k:v for k,v in groups.items() if k[0]==symbol}
        for field in FIELDS:
            if not any(k[1]==field for k in symgroups):missing.append(field)
        for key,rows in sorted(symgroups.items()):
            values=[number(f["value"]) for f in rows]
            source_hashes={f.get("source",{}).get("document_sha256") for f in rows}
            diff=max(values)-min(values)
            baseline=max(max(abs(v) for v in values),Decimal(1))
            tol=max(number(abs_tolerance),number(rel_tolerance)*baseline)
            if len(rows)==1:state="SINGLE_SOURCE_REVIEW_REQUIRED"
            elif diff>tol:state="CONFLICT_REVIEW_REQUIRED"
            elif len(source_hashes)<2:state="SAME_DOCUMENT_CONSISTENT_NOT_INDEPENDENT"
            else:state="MULTI_DOCUMENT_CONSISTENT_NOT_INDEPENDENTLY_VERIFIED"
            items.append({"field":key[1],"period_start":key[4],"period_end":key[5],
                          "scope":key[3],"currency":key[2],"period_type":key[6],
                          "status":state,"max_difference":str(diff),"tolerance":str(tol),
                          "source_sha256s":sorted(str(x) for x in source_hashes),
                          "fact_ids":[f["fact_id"] for f in rows]})
        output[symbol]={"comparisons":items,"missing_fields":missing,
                        "independent_fact_verification":False,
                        "historical_ttm_ready":False,
                        "capital_structure_reconciled":False}
    return {"schema":"PUBLIC_CROSS_SOURCE_FACT_RECONCILIATION/v2","stocks":output,
            "no_automatic_fact_verification":True,"valuation_authorized":False,
            "automatic_trade_execution":False}
