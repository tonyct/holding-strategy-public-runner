"""Source-bound HK consolidated H1 cashflow candidates from explicit text columns."""
import hashlib,re
from pathlib import Path

def extract_hk_halfyear_cashflow(path,symbol):
    import fitz
    sha=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    result=[]
    with fitz.open(str(path)) as pdf:
        for pi,page in enumerate(pdf):
            lines=page.get_text(sort=True).splitlines()
            normalized=" ".join(x.strip().casefold() for x in lines)
            if not ("consolidated statement of cash flow" in normalized
                    and "six months ended 30 june" in normalized):
                continue
            years=re.search(r"\b(20\d{2})\s+(20\d{2})\b",normalized)
            if not years or "hk$’000" not in normalized and "hk$'000" not in normalized:
                continue
            year1,year2=int(years.group(1)),int(years.group(2))
            for line_no,line in enumerate(lines,1):
                match=re.fullmatch(r"\s*Net cash from operating activities\s+([\d,()\-]+)\s+([\d,()\-]+)\s*",line,re.I)
                if not match:continue
                for col,(year,raw) in enumerate(((year1,match.group(1)),(year2,match.group(2))),1):
                    v=raw.replace(",","")
                    if v.startswith("(") and v.endswith(")"):v="-"+v[1:-1]
                    if not re.fullmatch(r"-?\d+",v):continue
                    result.append({"symbol":symbol,"field":"operating_cash_flow","value":v,
                      "unit_multiplier":"1000","currency":"HKD",
                      "period_start":f"{year}-01-01","period_end":f"{year}-06-30",
                      "period_type":"H1_YTD","scope":"CONSOLIDATED",
                      "source":{"document_sha256":sha,"page":pi+1,"line_number":line_no,
                        "literal_line":line.strip(),"column_index":col,"column_label":str(year),
                        "unit_label":"HK$’000"}})
    return result
