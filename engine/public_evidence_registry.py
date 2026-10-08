"""Build a dynamic public-evidence registry from this run's outputs.

The registry is content-addressed and count-free: it accepts any number of new
JSON/PDF objects. It makes no portfolio, valuation or trade conclusion.
"""
import argparse,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path

def build(root,previous=None):
    root=Path(root).resolve()
    prior={"objects":{},"identities":{}}
    if previous and Path(previous).is_file():
        try:
            x=json.loads(Path(previous).read_text())
            if x.get("schema")=="PUBLIC_EVIDENCE_REGISTRY/v1": prior=x
        except Exception: pass
    objects=dict(prior.get("objects") or {})
    identities={k:list(v) for k,v in (prior.get("identities") or {}).items()}
    touched=[];now=datetime.now(timezone.utc).isoformat()
    allowed=("official_a","official_hk","a_financials","hk_financials","a","community","news","ir","quotes")
    for folder in allowed:
        base=root/folder
        if not base.exists(): continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.is_symlink(): continue
            raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest()
            rel=str(p.relative_to(root))
            objects.setdefault(sha,{"sha256":sha,"size":len(raw),"first_seen_utc":now,
                "content_uri":"public-evidence://sha256/"+sha})
            identity=rel
            versions=identities.setdefault(identity,[])
            if not any(v.get("sha256")==sha for v in versions):
                versions.append({"sha256":sha,"seen_utc":now,
                    "supersedes":versions[-1]["sha256"] if versions else None})
            touched.append({"identity":identity,"sha256":sha,"size":len(raw),"relative_path":rel})
    return {"schema":"PUBLIC_EVIDENCE_REGISTRY/v1","generated_utc":now,
        "object_count":len(objects),"identity_count":len(identities),
        "objects":objects,"identities":identities,"touched":touched,
        "public_only_contract":True,"investment_decision_authorized":False,"automatic_trade_execution":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",default="output")
    p.add_argument("--previous");p.add_argument("--output",required=True);a=p.parse_args()
    out=build(a.root,a.previous);Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"objects":out["object_count"],"identities":out["identity_count"]}))
if __name__=="__main__":main()
