"""Write public-safe research outputs into the private state repository without running Private Actions.

The token should be a fine-grained credential scoped only to contents:write on
the target private repository. This sink never reads private strategy/state
files; it writes only under runtime/public_inputs/.
"""
import argparse,base64,hashlib,json,os
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

def request(token,repo,method,path,payload=None):
    url="https://api.github.com/repos/"+repo+"/contents/"+path
    raw=None if payload is None else json.dumps(payload,separators=(",",":")).encode()
    req=Request(url,data=raw,method=method,headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
      "X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"})
    try:
        with urlopen(req,timeout=30) as r:return r.status,json.load(r)
    except HTTPError as e:
        if e.code==404:return 404,{}
        raise

def put(token,repo,path,raw,message):
    status,old=request(token,repo,"GET",path)
    payload={"message":message,"content":base64.b64encode(raw).decode(),"branch":"main"}
    if status==200: payload["sha"]=old["sha"]
    code,res=request(token,repo,"PUT",path,payload)
    if code not in (200,201): raise ValueError("PRIVATE_SINK_WRITE_FAILED:"+str(code))
    return res.get("content",{}).get("sha")

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",default="output");p.add_argument("--repo",default="tonyct/holding-strategy-data")
    p.add_argument("--run-id",required=True);p.add_argument("--status-output",required=True);a=p.parse_args()
    token=os.getenv("PRIVATE_STATE_WRITE_TOKEN","").strip()
    status={"schema":"PUBLIC_TO_PRIVATE_STATE_SINK/v1","source_run_id":a.run_id,"target_repository":a.repo,
            "target_prefix":"runtime/public_inputs/","contains_private_read":False}
    if not token:
        status.update(status="NOT_CONFIGURED",reason="PRIVATE_STATE_WRITE_TOKEN_MISSING")
    else:
        root=Path(a.root);selected=[]
        for pattern in ("PUBLIC_RESEARCH_BUNDLE.json","ACQUISITION_HEALTH.json","compute/*.json",
                        "state/*.json","originals/**/*RECEIPT.json"):
            selected.extend(x for x in root.glob(pattern) if x.is_file())
        prefix="runtime/public_inputs/runs/"+str(a.run_id)
        written=[]
        for src in sorted(set(selected)):
            rel=str(src.relative_to(root));raw=src.read_bytes()
            sha=put(token,a.repo,prefix+"/"+rel,raw,"Store public research input "+str(a.run_id))
            written.append({"path":rel,"sha256":hashlib.sha256(raw).hexdigest(),"github_blob_sha":sha})
        evidence_written=[]
        for src in sorted((root/"evidence/raw/sha256").rglob("*")) if (root/"evidence/raw/sha256").exists() else []:
            if not src.is_file() or src.suffix.lower()!=".pdf": continue
            rel=str(src.relative_to(root/"evidence/raw/sha256"))
            raw=src.read_bytes()
            dest="evidence/public/raw/sha256/"+rel
            try:
                sha=put(token,a.repo,dest,raw,"Archive public evidence "+a.run_id)
                evidence_written.append({"path":dest,"sha256":hashlib.sha256(raw).hexdigest(),"github_blob_sha":sha})
            except HTTPError as exc:
                if exc.code!=422: raise
        pointer={"schema":"PRIVATE_PUBLIC_INPUT_POINTER/v1","source_run_id":a.run_id,"files":written,
                 "public_evidence_files":evidence_written,"public_safe_only":True,
                 "automatic_trade_execution":False,"orders_submitted":0}
        put(token,a.repo,"runtime/public_inputs/latest.json",(json.dumps(pointer,ensure_ascii=False,indent=2)+"\n").encode(),
            "Advance public research input pointer "+str(a.run_id))
        status.update(status="SYNCED",file_count=len(written),evidence_file_count=len(evidence_written))
    Path(a.status_output).parent.mkdir(parents=True,exist_ok=True);Path(a.status_output).write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(status))
if __name__=="__main__":main()
