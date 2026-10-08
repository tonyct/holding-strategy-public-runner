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
NUMBER=re.compile(r"^\(?[-−]?\d[\d,]*(?:\.\d+)?\)?$")
def parse_number(raw):
    s=str(raw).strip().replace(" ","").replace("−","-")
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
            # Table cells preserve row and column geometry; extraction is deliberately conservative.
            try: tables=page.find_tables().tables
            except Exception: tables=[]
            for ti,table in enumerate(tables):
                rows=table.extract()
                for ri,row in enumerate(rows):
                    if not row: continue
                    label=str(row[0] or "").strip().casefold()
                    matches=[field for field,aliases in LABELS.items() if any(alias.casefold() in label for alias in aliases)]
                    if not matches:continue
                    values=[(ci,parse_number(cell)) for ci,cell in enumerate(row[1:],1)]
                    values=[(ci,v) for ci,v in values if v is not None]
                    item={"symbol":symbol,"field_candidates":matches,"page":pi+1,"table_index":ti,
                          "row_index":ri,"row_label":str(row[0]),"numeric_cells":[{"column":ci,"printed_value":v} for ci,v in values],
                          "source_sha256":sha,"state":"COLUMN_PERIOD_SCOPE_UNIT_UNRESOLVED"}
                    # No value is auto-promoted without confirmed header, unit, reporting dates and consolidation scope.
                    ambiguous.append(item)
    return {"symbol":symbol,"source_sha256":sha,"page_count":pages,"table_candidates":ambiguous,
            "facts":[],"semantic_fact_verified":False}
def build(root):
    root=Path(root);documents=[];facts=[]
    for path in sorted(root.rglob("*.pdf")):
        m=re.match(r"(\d+_[A-Z]+)_",path.name)
        if not m: continue
        documents.append(extract(path,m.group(1).replace("_",".")))
    # fail closed: zero verified/normalized facts until all semantic axes are bound.
    out=run(facts)
    return documents,out
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--out-dir",required=True);a=p.parse_args()
    documents,products=build(a.root);root=Path(a.out_dir);root.mkdir(parents=True,exist_ok=True)
    artifacts={"PUBLIC_TABLE_CANDIDATES_V2.json":{"schema":"PUBLIC_TABLE_CANDIDATES/v2","documents":documents,"automatic_fact_promotion":False},
      "PUBLIC_FACT_STORE_V2.json":products["store"],"PUBLIC_COMPACT_FACT_PACKET_V2.json":products["compact"],"PUBLIC_DELTA_PACKET_V2.json":products["delta"]}
    for name,value in artifacts.items():
        (root/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"documents":len(documents),"table_candidates":sum(len(x["table_candidates"]) for x in documents),"auto_verified":0}))
if __name__=="__main__":main()
