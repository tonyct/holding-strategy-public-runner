"""Strict CN consolidated half-year cash-flow source-bound fact candidates.

No source is marked verified. Ambiguous report headers, scopes and units fail closed.
"""
import hashlib
import re
from pathlib import Path

FIELDS={
    "operating_cash_flow":("经营活动产生的现金流量净额",),
    "capital_expenditure":("购建固定资产、无形资产和其他长期资产支付的现金",),
}
def normalize(s):
    return re.sub(r"\s+","",str(s or "")).replace("，","").replace("、","").casefold()
def monetary(s):
    x=str(s or "").strip().replace(",","").replace("−","-")
    return x if re.fullmatch(r"-?\d+(?:\.\d+)?",x) else None

def extract_a_halfyear_cashflow(path,symbol):
    import fitz
    source_sha=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    results=[]
    with fitz.open(str(path)) as pdf:
        scope=None;currency=None;columns=None
        for pi,page in enumerate(pdf):
            text=normalize(page.get_text(sort=True))
            if "母公司现金流量表" in text:
                scope="PARENT";currency=None;columns=None
            elif "合并现金流量表" in text:
                scope="CONSOLIDATED";currency=None;columns=None
            if scope is None:continue
            if "单位：元币种：人民币" in text or "单位:元币种:人民币" in text:
                currency="CNY"
            if scope!="CONSOLIDATED":continue
            for ti,table in enumerate(page.find_tables().tables):
                for ri,row in enumerate(table.extract()):
                    if not row:continue
                    if len(row)>3 and normalize(row[0])=="项目":
                        headers=[re.search(r"(20\d{2})年半年度",normalize(x)) for x in row]
                        columns=([(i,int(x.group(1))) for i,x in enumerate(headers) if x and i>=1]
                                 if len(headers)>3 and headers[2] and headers[3] else None)
                    if currency!="CNY" or not columns:continue
                    label=normalize(row[0])
                    matched=[field for field,aliases in FIELDS.items()
                             if any(normalize(alias)==label for alias in aliases)]
                    if len(matched)!=1:continue
                    for ci,year in columns:
                        if ci>=len(row):continue
                        value=monetary(row[ci])
                        if value is None:continue
                        results.append({
                          "symbol":symbol,"field":matched[0],"value":value,"currency":"CNY",
                          "period_start":f"{year}-01-01","period_end":f"{year}-06-30",
                          "period_type":"H1_YTD","scope":"CONSOLIDATED",
                          "source":{"document_sha256":source_sha,"page":pi+1,
                            "table_index":ti,"row_index":ri,"column_index":ci,
                            "row_label":str(row[0]),"column_label":f"{year}年半年度"}})
    return results
