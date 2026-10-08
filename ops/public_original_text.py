"""Extract public financial fact candidates from SHA-bound official PDFs."""
import argparse,hashlib,json,re
from pathlib import Path
LABELS=("营业收入","归属于上市公司股东的净利润","经营活动产生的现金流量净额","自由现金流","资本性支出","资本开支",
        "revenue","profit attributable","net cash from operating activities","free cash flow","capital expenditure",
        "issued shares","share capital","总股本","股份总数")
NUM=re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")

def one(path):
    import fitz
    rows=[]
    with fitz.open(str(path)) as pdf:
        for i in range(pdf.page_count):
            text=pdf[i].get_text(sort=True);low=text.casefold()
            for label in LABELS:
                pos=low.find(label.casefold())
                if pos<0: continue
                ex=text[max(0,pos-120):min(len(text),pos+600)]
                nums=NUM.findall(ex)
                if nums: rows.append({"page":i+1,"label":label,"literal_excerpt":ex[:700],"numbers_as_printed":nums[:16]})
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",default="output/originals");p.add_argument("--output",required=True);a=p.parse_args()
    root=Path(a.root);symbols={};sources={}
    for pth in sorted(root.rglob("*.pdf")):
        raw=pth.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        m=re.match(r"(\d+_[A-Z]+)_",pth.name);ticker=(m.group(1).replace("_",".") if m else "UNKNOWN")
        candidates=one(pth)
        sid=ticker+":"+sha[:16]
        sources[sid]={"ticker":ticker,"sha256":sha,"relative_path":str(pth),"bytes":len(raw)}
        symbols.setdefault(ticker,[]).append({"source_id":sid,"candidate_count":len(candidates),"field_candidates":candidates})
    out={"schema":"PUBLIC_ORIGINAL_TEXT_CANDIDATES/v1","symbols":symbols,"sources":sources,
         "semantic_fact_verified":False,"portfolio_decision":False,"trade_signal":False}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"sources":len(sources),"tickers":len(symbols)}))
if __name__=="__main__":main()
