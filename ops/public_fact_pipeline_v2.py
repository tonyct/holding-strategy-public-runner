"""Conservative source-bound PDF table extraction. Unknown context never becomes a financial fact."""
import argparse,hashlib,json,re
from pathlib import Path
from engine.financial_fact_engine_v2 import run
LABELS={
 "operating_cash_flow":("经营活动产生的现金流量净额","net cash generated from operating activities","net cash from operating activities"),
 "revenue":("营业收入","营业额","revenue"),
 "attributable_net_profit":("归属于母公司股东的净利润","归属于上市公司股东的净利润","profit attributable to owners"),
 "capital_expenditure":("购建固定资产、无形资产和其他长期资产支付的现金","purchase of property, plant and equipment"),
 "issued_shares":("股份总数","已发行股份总数","number of issued shares"),
}
REPORT_PATTERNS=("年度报告","半年度报告","季度报告","财务报告","业绩公告","业绩报告","annual report","interim report","quarterly report","interim results","annual results","financial statements","results announcement")
def report_files(root):
    root=Path(root)
    names=set()
    for receipt in (root/"a/A_ORIGINALS_RECEIPT.json",root/"hk/HK_ORIGINALS_RECEIPT.json"):
        if not receipt.is_file():continue
        data=json.loads(receipt.read_text(encoding="utf-8"))
        for row in (data.get("symbols") or {}).values():
            for f in row.get("files",[]):
                title=str(f.get("title") or "").casefold()
                if f.get("status")=="FETCHED_OFFICIAL_ORIGINAL" and any(k in title for k in REPORT_PATTERNS):
                    if f.get("filename"):names.add(f["filename"])
    return names
NUMBER=re.compile(r"^\(?[-−]?\d[\d,]*(?:\.\d+)?\)?$")
def parse_number(raw):
    s=str(raw).strip().replace("−","-")
    if any(ch.isspace() for ch in s): return None
    if not NUMBER.fullmatch(s): return None
    if s.startswith("("): s="-"+s[1:-1]
    return s.replace(",","")
def extract(pdf_path,symbol):
    import fitz
    sha=hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    candidates=[];ambiguous=[];pages=0
    with fitz.open(str(pdf_path)) as doc:
        pages=doc.page_count
        for pi,page in enumerate(doc):
            # Avoid expensive table recognition on unrelated pages.
            normalized=re.sub(r"\s+","",page.get_text(sort=False).casefold())
            has_financial_label=any(re.sub(r"\s+","",alias).casefold() in normalized for aliases in LABELS.values() for alias in aliases)
            if not has_financial_label:continue
            # Table cells preserve row and column geometry; extraction is deliberately conservative.
            try: tables=page.find_tables().tables
            except Exception: tables=[]
            if not tables:
                lines=page.get_text(sort=True).splitlines()
                for li,line in enumerate(lines):
                    low=re.sub(r"\\s+","",(line+" "+(lines[li+1] if li+1<len(lines) else "")).casefold())
                    fields=[field for field,aliases in LABELS.items() if any(re.sub(r"\\s+","",alias).casefold() in low for alias in aliases)]
                    if fields:
                        ambiguous.append({"symbol":symbol,"field_candidates":fields,"page":pi+1,
                          "text_line":li+1,"literal_excerpt":" ".join(lines[max(0,li-1):li+3])[:600],
                          "source_sha256":sha,"state":"TEXT_FALLBACK_COLUMN_PERIOD_SCOPE_UNIT_UNRESOLVED"})
            for ti,table in enumerate(tables):
                rows=table.extract()
                for ri,row in enumerate(rows):
                    if not row: continue
                    label=re.sub(r"\s+","",str(row[0] or "")).casefold()
                    matches=[field for field,aliases in LABELS.items() if any(re.sub(r"\s+","",alias).casefold() in label for alias in aliases)]
                    if not matches:continue
                    values=[(ci,parse_number(cell)) for ci,cell in enumerate(row[1:],1)]
                    values=[(ci,v) for ci,v in values if v is not None]
                    item={"symbol":symbol,"field_candidates":matches,"page":pi+1,"table_index":ti,
                          "row_index":ri,"row_label":str(row[0]),"numeric_cells":[{"column":ci,"printed_value":v} for ci,v in values],
                          "source_sha256":sha,"state":"COLUMN_PERIOD_SCOPE_UNIT_UNRESOLVED"}
                    # No value is auto-promoted without confirmed header, unit, reporting dates and consolidation scope.
                    ambiguous.append(item)
    facts=[]
    if symbol.endswith((".SH",".SZ")):
        from ops.public_a_statement_fact_v2 import extract_a_halfyear_cashflow
        facts=extract_a_halfyear_cashflow(pdf_path,symbol)
    elif symbol.endswith(".HK"):
        from ops.public_hk_statement_fact_v2 import extract_hk_halfyear_cashflow
        facts=extract_hk_halfyear_cashflow(pdf_path,symbol)
    return {"symbol":symbol,"source_sha256":sha,"page_count":pages,"table_candidates":ambiguous,
            "facts":facts,"semantic_fact_verified":False}
def build(root,prior=None):
    root=Path(root);documents=[];facts=[]
    selected=report_files(root)
    for path in sorted(root.rglob("*.pdf")):
        if path.name not in selected: continue
        m=re.match(r"(\d+_[A-Z]+)_",path.name)
        if not m: continue
        document=extract(path,m.group(1).replace("_","."))
        documents.append(document)
        facts.extend(document["facts"])
    # All normalized rows remain UNVERIFIED pending independent research review.
    out=run(facts,prior)
    return documents,out
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--out-dir",required=True);p.add_argument("--previous");a=p.parse_args()
    prior=[]
    if a.previous and Path(a.previous).is_file():
        prior=json.loads(Path(a.previous).read_text(encoding="utf-8")).get("facts",[])
    documents,products=build(a.root,prior);root=Path(a.out_dir);root.mkdir(parents=True,exist_ok=True)
    artifacts={"PUBLIC_TABLE_CANDIDATES_V2.json":{"schema":"PUBLIC_TABLE_CANDIDATES/v2","documents":documents,"automatic_fact_promotion":False},
      "PUBLIC_FACT_STORE_V2.json":products["store"],"PUBLIC_COMPACT_FACT_PACKET_V2.json":products["compact"],"PUBLIC_DELTA_PACKET_V2.json":products["delta"]}
    for name,value in artifacts.items():
        (root/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"documents":len(documents),"table_candidates":sum(len(x["table_candidates"]) for x in documents),"auto_verified":0}))
if __name__=="__main__":main()
