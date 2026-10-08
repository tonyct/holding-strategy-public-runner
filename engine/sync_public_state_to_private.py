"""Optional one-way sink from Public Runner into the Private state repository.

The public computation remains independent if the credential is absent. When
present, only explicitly public-safe artifacts and public evidence bytes are
written; no private state is read into the computation.
"""
import argparse,base64,json,os,time
from pathlib import Path
import requests

API="https://api.github.com/repos/tonyct/holding-strategy-data/contents/"

def api(session,method,path,**kw):
    r=session.request(method,API+path,timeout=45,**kw)
    if r.status_code>=400: raise RuntimeError("PRIVATE_STATE_API_"+str(r.status_code)+":"+r.text[:200])
    return r.json() if r.content else {}

def put(session,path,raw,message):
    old=None
    r=session.get(API+path,timeout=30)
    if r.status_code==200: old=r.json().get("sha")
    elif r.status_code!=404: raise RuntimeError("PRIVATE_STATE_READ_"+str(r.status_code))
    body={"message":message,"content":base64.b64encode(raw).decode(),"branch":"main"}
    if old: body["sha"]=old
    return api(session,"PUT",path,json=body)

def main():
    p=argparse.ArgumentParser();p.add_argument("--snapshot",required=True);p.add_argument("--registry",required=True)
    p.add_argument("--evidence-root",default="output");a=p.parse_args()
    token=os.getenv("PRIVATE_STATE_REPO_TOKEN")
    if not token:
        print(json.dumps({"status":"SKIPPED_NO_PRIVATE_STATE_TOKEN"}));return 0
    snap=Path(a.snapshot).read_bytes();reg=Path(a.registry).read_bytes()
    for raw in (snap,reg):
        text=raw.decode("utf-8")
        if any(x in text.lower() for x in ("cost_basis","position_size","portfolio_decision")):
            raise ValueError("PUBLIC_TO_PRIVATE_PAYLOAD_NOT_PUBLIC_SAFE")
    s=requests.Session();s.headers.update({"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28"})
    put(s,"runtime/public_compute_latest.json",snap,"Sync latest public company research snapshot")
    put(s,"runtime/public_evidence_registry_latest.json",reg,"Sync latest public evidence registry")
    registry=json.loads(reg)
    root=Path(a.evidence_root)
    uploaded=0
    for row in registry.get("touched",[]):
        rel=row.get("relative_path","")
        if not rel.lower().endswith(".pdf"): continue
        src=root/rel
        if not src.is_file(): continue
        dest="evidence/public/raw/"+row["sha256"][:2]+"/"+row["sha256"]+".pdf"
        try:
            put(s,dest,src.read_bytes(),"Archive public evidence "+row["sha256"][:16])
            uploaded+=1
        except RuntimeError as exc:
            if "PRIVATE_STATE_API_422" in str(exc): continue
            raise
    print(json.dumps({"status":"SYNCED","public_pdf_objects_uploaded":uploaded}))
    return 0
if __name__=="__main__":raise SystemExit(main())
