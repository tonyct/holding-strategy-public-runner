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
        scope=None;currency=None;multiplier=None;columns=None
        for pi,page in enumerate(pdf):
            text=normalize(page.get_text(sort=False))
            if "母公司现金流量表" in text:
                scope="PARENT";currency=None;multiplier=None;columns=None
            elif "合并现金流量表" in text:
                scope="CONSOLIDATED";currency=None;multiplier=None;columns=None
            if scope is None:continue
            if "单位：元币种：人民币" in text or "单位:元币种:人民币" in text:
                currency="CNY";multiplier="1"
            elif "单位：万元币种：人民币" in text or "单位:万元币种:人民币" in text:
                currency="CNY";multiplier="10000"
            elif "金额单位为人民币百万元" in text:
                currency="CNY";multiplier="1000000"
            elif "单位：元" in text or "单位:元" in text:
                currency="CNY";multiplier="1"
            if scope!="CONSOLIDATED":continue
            field_on_page=any(normalize(alias) in text for aliases in FIELDS.values() for alias in aliases)
            section_header_on_page="合并现金流量表" in text
            if not (field_on_page or section_header_on_page):continue
            for ti,table in enumerate(page.find_tables().tables):
                for ri,row in enumerate(table.extract()):
                    if not row:continue
                    if len(row)>=3 and normalize(row[0])=="项目":
                        headers=[re.search(r"(20\d{2})年半年度",normalize(x)) for x in row]
                        parsed=[(i,int(x.group(1))) for i,x in enumerate(headers) if x and i>=1]
                        columns=parsed if len(parsed)==2 else None
                    if currency!="CNY" or not multiplier or not columns:continue
                    label=normalize(row[0])
                    matched=[field for field,aliases in FIELDS.items()
                             if any(normalize(alias)==label for alias in aliases)]
                    if len(matched)!=1:continue
                    for ci,year in columns:
                        if ci>=len(row):continue
                        value=monetary(row[ci])
                        if value is None:continue
                        original_value=value
                        if matched[0]=="capital_expenditure" and value.startswith("-"):
                            value=value[1:]
                        results.append({
                          "symbol":symbol,"field":matched[0],"value":value,"currency":"CNY",
                          "period_start":f"{year}-01-01","period_end":f"{year}-06-30",
                          "period_type":"H1_YTD","scope":"CONSOLIDATED","unit_multiplier":multiplier,
                          "source":{"document_sha256":source_sha,"page":pi+1,
                            "table_index":ti,"row_index":ri,"column_index":ci,
                            "row_label":str(row[0]),"column_label":f"{year}年半年度",
                            "original_printed_value":str(row[ci]),"parsed_printed_value":original_value,
                            "capex_cash_paid_magnitude":matched[0]=="capital_expenditure"}})
    return results
