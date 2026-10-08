"""Public-to-private v2 data-only sync entrypoint. Fail closed, no trading."""
import argparse,os,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--root",default="output");p.add_argument("--run-id",required=True)
 p.add_argument("--status-output",required=True)
 a=p.parse_args()
 token=os.getenv("PRIVATE_STATE_WRITE_TOKEN","").strip()
 result={"schema":"PUBLIC_TO_PRIVATE_STATE_SINK/v2","source_run_id":a.run_id,
         "status":"NOT_CONFIGURED" if not token else "DEPLOYMENT_NOT_VERIFIED",
         "reason":"PRIVATE_STATE_WRITE_TOKEN_MISSING" if not token else "REQUIRES_ATOMIC_PUBLISHER",
         "private_head_modified":False,"orders_submitted":0}
 dest=Path(a.status_output);dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_text(json.dumps(result,indent=2)+"\n")
 print(json.dumps(result))
if __name__=="__main__":main()
