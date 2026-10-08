"""Public-only API-first data routing, freshness and model-review fallback contract.

Never promotes model output or third-party API values to independently verified facts.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from collections import defaultdict

CORE=("revenue","attributable_net_profit","net_profit","operating_cash_flow",
      "capital_expenditure","assets","liabilities","cash","interest_bearing_debt",
      "issued_shares","minority_interest")
MARKET=("price","market_cap","pe","pe_ttm","pb","dividend_yield")
SNAPSHOT=("cash","assets","liabilities","interest_bearing_debt","issued_shares","minority_interest")
ALLOWED_SOURCES=("PUBLIC_API","OFFICIAL_REPORT","AI_DOCUMENT_EXTRACTION")
RANK={"OFFICIAL_REPORT":0,"PUBLIC_API":1,"AI_DOCUMENT_EXTRACTION":2}
def _time(value):
    try:
        x=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if x.tzinfo is None: return None
        return x.astimezone(timezone.utc)
    except (ValueError,TypeError):return None
def _valid_number(v):
    try:return Decimal(str(v).replace(",","")).is_finite()
    except (ValueError,TypeError,InvalidOperation):return False
def validate(row):
    if not isinstance(row,dict):return "NOT_OBJECT"
    for name in ("symbol","field","value","source_type","source_id","observed_at"):
        if row.get(name) is None or row.get(name)=="":return "MISSING_"+name.upper()
    if row["source_type"] not in ALLOWED_SOURCES:return "INVALID_SOURCE_TYPE"
    if row["field"] not in CORE+MARKET:return "UNSUPPORTED_FIELD"
    if not _valid_number(row["value"]):return "INVALID_NUMBER"
    if _time(row["observed_at"]) is None:return "INVALID_OBSERVED_AT"
    if row["field"] in CORE:
        for name in ("currency","period_end","period_type","scope","unit_multiplier"):
            if row.get(name) in (None,""):return "MISSING_"+name.upper()
        if row["scope"] not in ("CONSOLIDATED","PARENT","ENTITY","UNKNOWN"):return "INVALID_SCOPE"
        if row["field"] not in SNAPSHOT and not row.get("period_start"):return "MISSING_PERIOD_START"
        try:
            if Decimal(str(row["unit_multiplier"]))<=0:return "INVALID_MULTIPLIER"
        except (ValueError,InvalidOperation):return "INVALID_MULTIPLIER"
    else:
        if not row.get("price_session") and row["field"] in MARKET:
            return "MISSING_PRICE_SESSION"
        if row["field"] in ("pe","pe_ttm","pb","dividend_yield"):
            if not row.get("metric_definition") or not row.get("denominator_period"):
                return "MISSING_METRIC_BASIS"
    if row["source_type"]=="OFFICIAL_REPORT":
        if not row.get("document_sha256") or not isinstance(row.get("page"),int) or row["page"]<1:
            return "MISSING_REPORT_EVIDENCE"
    if row["source_type"]=="AI_DOCUMENT_EXTRACTION":
        if not row.get("document_sha256") or not isinstance(row.get("page"),int) or row["page"]<1:
            return "AI_EVIDENCE_REQUIRED"
        if not row.get("literal_excerpt"):return "AI_LITERAL_EVIDENCE_REQUIRED"
    return None
def route(symbols,records,now_iso,market_ttl_hours=24):
    now=_time(now_iso)
    if now is None:raise ValueError("INVALID_NOW")
    symbols=list(dict.fromkeys(symbols))
    by=defaultdict(list);rejected=[]
    for row in records:
        err=validate(row)
        if err:
            rejected.append({"symbol":row.get("symbol") if isinstance(row,dict) else None,
                             "field":row.get("field") if isinstance(row,dict) else None,"reason":err})
            continue
        if row["symbol"] in symbols:by[(row["symbol"],row["field"])].append(row)
    selected={};gaps=[];tasks=[]
    for symbol in symbols:
        for field in CORE+MARKET:
            options=by[(symbol,field)]
            if field in MARKET:
                options=[r for r in options if now-timedelta(hours=market_ttl_hours)<=_time(r["observed_at"])<=now]
            if not options:
                reason="STALE_OR_MISSING_MARKET" if field in MARKET else "MISSING_FACT"
                gaps.append({"symbol":symbol,"field":field,"reason":reason})
                if field in CORE:
                    tasks.append({"symbol":symbol,"field":field,"action":"SEARCH_OFFICIAL_REPORT_THEN_AI_IF_NEEDED",
                                  "automatic_verification":False})
                continue
            # Different periods and currencies must never be silently merged.
            contexts={(r.get("currency"),r.get("period_start"),r.get("period_end"),
                       r.get("scope"),r.get("period_type")) for r in options} if field in CORE else {(r.get("price_session"),r.get("metric_definition"),r.get("denominator_period")) for r in options}
            if len(contexts)>1:
                gaps.append({"symbol":symbol,"field":field,"reason":"MIXED_CONTEXT_REQUIRES_RECONCILIATION"})
                tasks.append({"symbol":symbol,"field":field,"action":"INDEPENDENT_CONTEXT_REVIEW","automatic_verification":False})
                continue
            values={str(Decimal(str(r["value"]))*Decimal(str(r.get("unit_multiplier",1)))) for r in options}
            if len(values)>1:
                gaps.append({"symbol":symbol,"field":field,"reason":"SOURCE_VALUE_CONFLICT"})
                tasks.append({"symbol":symbol,"field":field,"action":"INDEPENDENT_SOURCE_RECONCILIATION","automatic_verification":False})
                continue
            item=sorted(options,key=lambda r:(RANK[r["source_type"]],-_time(r["observed_at"]).timestamp(),r["source_id"]))[0]
            selected.setdefault(symbol,{})[field]={"value_normalized":str(Decimal(str(item["value"]))*Decimal(str(item.get("unit_multiplier",1)))),
                "currency":item.get("currency"),"source_type":item["source_type"],"source_id":item["source_id"],
                "period_start":item.get("period_start"),"period_end":item.get("period_end"),
                "price_session":item.get("price_session"),"observed_at":item["observed_at"],
                "verification_state":"UNVERIFIED","usable_for_frozen_valuation":False}
    return {"schema":"PUBLIC_API_FIRST_FACT_ROUTING/v1","symbols":symbols,"selected_candidates":selected,
            "gaps":gaps,"ai_fallback_tasks":tasks,"rejected_records":rejected,
            "model_output_auto_approved":False,"can_modify_private_head":False,
            "automatic_trade_execution":False}
