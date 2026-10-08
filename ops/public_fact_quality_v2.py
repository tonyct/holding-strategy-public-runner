"""Public-only fact quality receipt. Does not independently verify candidate facts."""
import json
from collections import defaultdict
from pathlib import Path

REQUIRED=("operating_cash_flow","capital_expenditure","issued_shares")
def quality(universe,store,documents):
    active=[x["symbol"] for x in universe.get("stocks",[]) if x.get("active") is True]
    facts=store.get("facts") or []
    by_symbol=defaultdict(list)
    for item in facts:
        if item.get("symbol") in active:by_symbol[item["symbol"]].append(item)
    docs=defaultdict(list)
    for row in documents:docs[row["symbol"]].append(row)
    result={}
    for symbol in active:
        rows=by_symbol[symbol]
        fields=defaultdict(list)
        for item in rows:fields[item.get("field")].append(item)
        conflicts=[]
        groups=defaultdict(set)
        for x in rows:
            if x.get("kind")=="NORMALIZED_CANDIDATE":groups[x.get("semantic_key")].add(x.get("value"))
        for k,values in groups.items():
            if len(values)>1:conflicts.append({"semantic_key":k,"distinct_value_count":len(values)})
        missing=[field for field in REQUIRED if not fields.get(field)]
        result[symbol]={
            "source_document_count":len(docs.get(symbol,[])),
            "source_page_count":sum(int(d.get("page_count") or 0) for d in docs.get(symbol,[])),
            "fact_candidate_count":sum(x.get("kind")=="NORMALIZED_CANDIDATE" for x in rows),
            "derived_count":sum(x.get("kind")=="DETERMINISTIC_DERIVED" for x in rows),
            "field_candidate_names":sorted(fields),
            "missing_research_fields":missing,
            "numeric_conflicts":conflicts,
            "extraction_errors":[d["extraction_error"] for d in docs.get(symbol,[]) if d.get("extraction_error")],
            "decisive_primary_financial_evidence_verified":False,
            "research_state":"SOURCE_BOUND_CANDIDATES_REQUIRE_INDEPENDENT_REVIEW" if rows else "NO_SOURCE_BOUND_FACTS",
            "valuation_authorized":False,
            "trade_signal_authorized":False
        }
    from ops.public_fact_reconcile_v2 import reconcile
    comparisons=reconcile(facts,active)
    for symbol in active:
        result[symbol]["cross_source_reconciliation"]=comparisons["stocks"][symbol]
    return {"schema":"PUBLIC_FINANCIAL_FACT_QUALITY/v2","stocks":result,
            "active_symbol_count":len(active),"verified_symbol_count":0,
            "unverified_data_may_not_authorize_valuation":True,"automatic_trade_execution":False}
def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--universe",required=True);p.add_argument("--store",required=True)
    p.add_argument("--candidates",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    read=lambda x:json.loads(Path(x).read_text(encoding="utf-8"))
    out=quality(read(a.universe),read(a.store),read(a.candidates).get("documents",[]))
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
if __name__=="__main__":main()
