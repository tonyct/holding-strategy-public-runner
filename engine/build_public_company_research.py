"""Build reusable company-level research facts from public sources only.

This produces source-bound reported facts and evidence status. It explicitly
does not produce private strategy valuation, buy/sell prices or portfolio actions.
"""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

HK_KEYS={
 "总资产":"total_assets","总负债":"total_liabilities","营业额":"revenue","收益":"revenue",
 "收入":"revenue","股东应占溢利":"attributable_profit","本公司拥有人应占溢利":"attributable_profit",
 "经营活动所得现金净额":"operating_cashflow","经营业务所得现金流量净额":"operating_cashflow"
}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path,default=None):
    p=Path(path)
    if not p.is_file(): return default if default is not None else {}
    return json.loads(p.read_text())

def a_facts(root):
    receipt=load(root/"a_financials/ACQUISITION_RECEIPT.json",{})
    out={}
    for row in receipt.get("tickers",[]):
        symbol=row.get("symbol");fn=row.get("snapshot_file")
        p=root/"a_financials/snapshots"/str(fn)
        rec={"structured_status":row.get("status"),"structured_sha256":row.get("snapshot_sha256"),
             "reported_core_fields":{}}
        if p.is_file() and sha(p)==row.get("snapshot_sha256"):
            snap=load(p,{})
            facts={}
            for sec in ("income","balance","cashflow"):
                data=((snap.get("statements") or {}).get(sec) or {}).get("data") or {}
                for k,v in (data.get("standard_fields") or {}).items():
                    if v is not None: facts[k]=v
            rec["reported_core_fields"]=facts
            rec["report_period"]=snap.get("period")
        out[symbol]=rec
    return out

def hk_facts(root):
    receipt=load(root/"hk_financials/HK_FINANCIAL_RECEIPT.json",{})
    out={}
    for row in receipt.get("rows",[]):
        symbol=row.get("symbol");expected=row.get("sha256")
        matches=sorted((root/"hk_financials").glob(symbol.replace(".","_")+"_"+str(expected)[:16]+"*.json"))
        rec={"structured_status":row.get("status"),"structured_sha256":expected,"reported_core_fields":{}}
        if matches and sha(matches[0])==expected:
            snap=load(matches[0],{});facts={}
            for sec in ("income","balance","cashflow"):
                for item in (((snap.get("statements") or {}).get(sec) or {}).get("rows") or []):
                    name=str(item.get("STD_ITEM_NAME") or "").strip()
                    key=next((v for k,v in HK_KEYS.items() if k in name),None)
                    val=item.get("AMOUNT")
                    if key and val not in (None,"nan",""): facts.setdefault(key,val)
            rec["reported_core_fields"]=facts;rec["report_period"]=snap.get("report_period_end")
            rec["currency"]=snap.get("currency")
        out[symbol]=rec
    return out

def official_status(root):
    out={}
    for receipt in (root/"official_a/OFFICIAL_PDF_FETCH_RECEIPT.json",
                    root/"official_hk/HK_FILING_RECEIPT.json"):
        x=load(receipt,{})
        for row in x.get("rows",[]):
            out[row.get("symbol")]={"status":row.get("status"),"sha256":row.get("sha256"),
                                    "filename":row.get("filename")}
    return out

def build(root,universe):
    root=Path(root);u=load(universe,{})
    symbols=[x["symbol"] for x in u.get("stocks",[]) if x.get("active")]
    af=a_facts(root);hf=hk_facts(root);official=official_status(root)
    community=load(root/"community/COMMUNITY_DIRECT_DISCOVERY.json",{})
    news=load(root/"news/NEWS_DISCOVERY.json",{})
    stocks={}
    for s in symbols:
        rec=(hf if s.endswith(".HK") else af).get(s,{})
        rec["official_original"]=official.get(s,{"status":"NOT_AVAILABLE_THIS_RUN"})
        rec["evidence_state"]=("OFFICIAL_ORIGINAL_AVAILABLE_REVIEWABLE"
            if rec["official_original"].get("sha256") else "STRUCTURED_PUBLIC_SOURCE_ONLY_OR_PENDING")
        rec["valuation_authorized"]=False;rec["trade_action_authorized"]=False
        stocks[s]=rec
    return {"schema":"PUBLIC_COMPANY_RESEARCH_SNAPSHOT/v1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "universe_version":u.get("universe_version"),"symbols":stocks,
        "community_lead_count":community.get("lead_count"),
        "news_lead_count":news.get("lead_count"),
        "scope":"PUBLIC_COMPANY_FACTS_AND_EVIDENCE_ONLY",
        "public_only_contract":True,"private_strategy_valuation_included":False,"buy_sell_prices_included":False,
        "automatic_trade_execution":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",default="output")
    p.add_argument("--universe",default="config/research_universe.json");p.add_argument("--output",required=True);a=p.parse_args()
    out=build(a.root,a.universe);Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"symbols":len(out["symbols"]),"scope":out["scope"]}))
if __name__=="__main__":main()
