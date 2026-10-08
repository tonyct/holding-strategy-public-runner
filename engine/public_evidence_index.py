"""Index a dynamic set of public output artifacts by content hash."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

EXCLUDE={"PUBLIC_RESEARCH_BUNDLE.json","PUBLIC_EVIDENCE_INDEX.json","PUBLIC_RUN_SNAPSHOT.json"}

def _declared(path):
    if path.suffix.lower()!=".json":return {}
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        if isinstance(x,dict):return {"schema":x.get("schema"),"declared_status":x.get("status") or x.get("quality")}
    except (OSError,UnicodeError,ValueError,TypeError):pass
    return {}

def build(root):
    root=Path(root).resolve(); rows=[]; counts={}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in EXCLUDE:continue
        raw=p.read_bytes(); rel=str(p.relative_to(root));category=rel.split("/",1)[0] if "/" in rel else "root"
        row={"path":rel,"sha256":hashlib.sha256(raw).hexdigest(),"size":len(raw),"category":category,
             "integrity_state":"BYTE_HASHED",**_declared(p)}
        rows.append(row);counts[category]=counts.get(category,0)+1
    return {"schema":"PUBLIC_EVIDENCE_INDEX/v1","privacy_class":"PUBLIC_MARKET_DATA_ONLY",
        "generated_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "artifact_count":len(rows),"category_counts":counts,"artifacts":rows,
        "dynamic_cardinality":True,"fixed_document_count_assumed":False,
        "contains_account_state":False,"contains_portfolio_decision":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    out=build(a.root);Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"artifact_count":out["artifact_count"],"category_counts":out["category_counts"]}))
if __name__=="__main__":main()
