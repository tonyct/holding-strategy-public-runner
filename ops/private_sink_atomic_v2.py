"""Atomic Public to Private v2 archival. Private stores bytes and state only."""
import argparse,base64,hashlib,json,os
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

def call(token,path,data=None,method="GET"):
    req=Request("https://api.github.com"+path,data=None if data is None else json.dumps(data).encode(),method=method,
       headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
       "X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"})
    with urlopen(req,timeout=30) as response:return json.load(response)
def graphql(token,query,variables):
    req=Request("https://api.github.com/graphql",data=json.dumps({"query":query,"variables":variables}).encode(),
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
    with urlopen(req,timeout=30) as response: answer=json.load(response)
    if answer.get("errors"):raise ValueError("GRAPHQL_REJECTED")
    return answer["data"]
def preflight(root,run_id,prior):
    root=Path(root)
    if not str(run_id).isdigit() or int(run_id)<1:raise ValueError("INVALID_RUN")
    if prior and prior.get("schema")!="PRIVATE_PUBLIC_INPUT_POINTER/v2":raise ValueError("INCOMPATIBLE_POINTER")
    if prior and int(prior.get("source",{}).get("run_id",0))>=int(run_id):raise ValueError("STALE_RUN")
    required=["PUBLIC_RESEARCH_BUNDLE.json","ACQUISITION_HEALTH.json"]
    files={}
    for name in required:
        path=root/name
        if not path.is_file():raise ValueError("MISSING_REQUIRED_"+name)
        files[name]=path.read_bytes()
    bundle=json.loads(files[required[0]])
    if str(bundle.get("source_run_id"))!=str(run_id):raise ValueError("RUN_MISMATCH")
    if bundle.get("contains_account_state") is not False or bundle.get("contains_portfolio_decision") is not False:
        raise ValueError("PRIVACY_CONTRACT")
    for folder in ("compute","state"):
        for path in sorted((root/folder).glob("*.json")):
            files[str(path.relative_to(root))]=path.read_bytes()
    for name,data in files.items():json.loads(data)
    summary=[{"path":p,"sha256":hashlib.sha256(v).hexdigest()} for p,v in sorted(files.items())]
    pointer={"schema":"PRIVATE_PUBLIC_INPUT_POINTER/v2","strategy_id":"HOLDING_STRATEGY",
       "active_version":prior.get("active_version") if prior else None,
       "epoch":prior.get("epoch") if prior else None,
       "source":{"repository":"tonyct/holding-strategy-public-runner","run_id":str(run_id),
                 "run_attempt":bundle.get("source_run_attempt"),"source_commit_sha":bundle.get("source_commit_sha"),
                 "completed_at_utc":bundle.get("completed_at_utc")},
       "public_compute":bundle.get("public_compute",{}),
       "private_storage":{"base_path":"runtime/public_inputs/runs/"+str(run_id)+"/",
              "selected_json_file_count":len(files),"selected_public_safe_json_lineage_stored":True,
              "sync_method":"GIT_TREE_ATOMIC_COMMIT_CAS",
              "manifest_sha256":hashlib.sha256(json.dumps(summary,sort_keys=True).encode()).hexdigest()},
       "files":summary,
       "semantics":{"public_safe_only":True,"latest_public_input_is_not_a_shadow_generation":True,
              "latest_public_input_is_not_a_main_generation":True,"valuation_revision_authorized":False,
              "buy_sell_prices_authorized":False,"formal_trade_authorized":False},
       "automatic_trade_execution":False,"orders_submitted":0}
    return files,pointer
def publish(token,repo,root,run_id):
    owner,name=repo.split("/",1)
    q='query($o:String!,$n:String!){repository(owner:$o,name:$n){id ref(qualifiedName:"refs/heads/main"){id target{oid ... on Commit{tree{oid}}}}}}'
    repository=graphql(token,q,{"o":owner,"n":name})["repository"]
    head=repository["ref"]["target"]["oid"]
    tree=repository["ref"]["target"]["tree"]["oid"]
    try:
        raw=call(token,"/repos/"+repo+"/contents/runtime/public_inputs/latest.json?ref=main")
        prior=json.loads(base64.b64decode(raw["content"]))
    except HTTPError as exc:
        if exc.code!=404:raise
        prior=None
    files,pointer=preflight(root,run_id,prior)
    elements=[]
    for path,data in sorted(files.items()):
        blob=call(token,"/repos/"+repo+"/git/blobs",
              {"content":base64.b64encode(data).decode(),"encoding":"base64"},"POST")["sha"]
        elements.append({"path":"runtime/public_inputs/runs/"+str(run_id)+"/"+path,
                         "mode":"100644","type":"blob","sha":blob})
    raw=(json.dumps(pointer,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    blob=call(token,"/repos/"+repo+"/git/blobs",{"content":base64.b64encode(raw).decode(),
        "encoding":"base64"},"POST")["sha"]
    elements.append({"path":"runtime/public_inputs/latest.json","mode":"100644","type":"blob","sha":blob})
    newtree=call(token,"/repos/"+repo+"/git/trees",{"base_tree":tree,"tree":elements},"POST")["sha"]
    commit=call(token,"/repos/"+repo+"/git/commits",
               {"message":"Archive Public input "+str(run_id),"tree":newtree,"parents":[head]},"POST")["sha"]
    mutation="mutation($input:UpdateRefsInput!){updateRefs(input:$input){clientMutationId}}"
    graphql(token,mutation,{"input":{"repositoryId":repository["id"],"refUpdates":[
            {"name":"refs/heads/main","beforeOid":head,"afterOid":commit,"force":False}]}})
    return {"status":"SYNCED","private_commit":commit,"source_run_id":str(run_id),"file_count":len(files)}
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",default="output")
    parser.add_argument("--repo",default="tonyct/holding-strategy-data")
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--status-output",required=True)
    opts=parser.parse_args()
    token=os.environ.get("PRIVATE_STATE_WRITE_TOKEN","").strip()
    result={"status":"NOT_CONFIGURED","reason":"PRIVATE_STATE_WRITE_TOKEN_MISSING"} if not token else publish(
        token,opts.repo,opts.root,opts.run_id)
    result.update(schema="PUBLIC_TO_PRIVATE_STATE_SINK/v2",source_run_id=opts.run_id)
    dest=Path(opts.status_output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result))
if __name__=="__main__":main()
