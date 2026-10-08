"""Dynamic content-addressed registry for public research evidence."""
import argparse,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
SCHEMA="PUBLIC_DYNAMIC_EVIDENCE_REGISTRY/v1"

def load(path):
    p=Path(path)
    if not p.is_file(): return {"schema":SCHEMA,"objects":{},"identities":{}}
    x=json.loads(p.read_text())
    if x.get("schema")!=SCHEMA: raise ValueError("REGISTRY_SCHEMA_INVALID")
    return x

def main():
    p=argparse.ArgumentParser();p.add_argument("--registry",required=True);p.add_argument("--source-root",default="output")
    p.add_argument("--store-root",default="output/evidence/raw/sha256");p.add_argument("--run-id",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    reg=load(a.registry);root=Path(a.source_root).resolve();store=Path(a.store_root);before=len(reg["objects"]);touched=[]
    registry_path=Path(a.registry).resolve(); output_path=Path(a.output).resolve()
    excluded={"PUBLIC_RESEARCH_BUNDLE.json","PUBLIC_EVIDENCE_REGISTRY.json","PUBLIC_EVIDENCE_REGISTRY_UPDATE.json"}
    for path in sorted(root.rglob("*")):
        resolved=path.resolve()
        if (not path.is_file() or path.name in excluded or "evidence/raw/sha256" in str(path)
                or resolved in (registry_path,output_path)):
            continue
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();rel=str(path.relative_to(root))
        obj=reg["objects"].setdefault(sha,{"sha256":sha,"bytes":len(raw),"first_seen_run_id":a.run_id,"locations":[]})
        obj["last_seen_run_id"]=a.run_id
        if rel not in obj["locations"]: obj["locations"].append(rel)
        ident=rel
        versions=reg["identities"].setdefault(ident,[])
        if not versions or versions[-1]["sha256"]!=sha:
            versions.append({"sha256":sha,"source_run_id":a.run_id,"supersedes":versions[-1]["sha256"] if versions else None})
        if path.suffix.lower() in (".pdf",".json"):
            dest=store/sha[:2]/(sha+path.suffix.lower());dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists(): shutil.copyfile(path,dest)
        touched.append({"identity":ident,"sha256":sha})
    reg["updated_at_utc"]=datetime.now(timezone.utc).isoformat();reg["object_count"]=len(reg["objects"]);reg["identity_count"]=len(reg["identities"])
    Path(a.registry).parent.mkdir(parents=True,exist_ok=True);Path(a.registry).write_text(json.dumps(reg,ensure_ascii=False,indent=2)+"\n")
    update={"schema":"PUBLIC_EVIDENCE_REGISTRY_UPDATE/v1","source_run_id":a.run_id,"touched":touched,
            "new_object_count":len(reg["objects"])-before,"object_count":len(reg["objects"]),"fixed_document_count_assumption":False}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(update,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"objects":len(reg["objects"]),"new":update["new_object_count"],"touched":len(touched)}))
if __name__=="__main__":main()
