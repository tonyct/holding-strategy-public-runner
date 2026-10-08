"""Freeze exact public-only inputs/derived artifacts for one public run."""
import argparse,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path

def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _load(path):return json.loads(Path(path).read_text(encoding="utf-8"))

def build(universe,health,evidence,metrics,run_id=None,run_attempt=None,commit_sha=None):
    u=_load(universe);h=_load(health);e=_load(evidence);m=_load(metrics)
    active=sorted(x["symbol"] for x in u.get("stocks",[]) if x.get("active") is True)
    if not active or len(active)!=len(set(active)):raise ValueError("INVALID_PUBLIC_RESEARCH_UNIVERSE")
    if e.get("schema")!="PUBLIC_EVIDENCE_INDEX/v1" or m.get("schema")!="PUBLIC_DETERMINISTIC_METRICS/v1":
        raise ValueError("PUBLIC_COMPUTE_INPUT_SCHEMA_INVALID")
    if m.get("active_symbol_count")!=len(active):raise ValueError("PUBLIC_METRIC_SCOPE_MISMATCH")
    return {"schema":"PUBLIC_RUN_SNAPSHOT/v1","privacy_class":"PUBLIC_MARKET_DATA_ONLY",
        "created_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "source_run_id":str(run_id or os.environ.get("GITHUB_RUN_ID") or ""),
        "source_run_attempt":str(run_attempt or os.environ.get("GITHUB_RUN_ATTEMPT") or ""),
        "source_commit_sha":commit_sha or os.environ.get("GITHUB_SHA"),
        "universe_sha256":_sha(universe),"active_symbol_count":len(active),"active_symbols":active,
        "acquisition_health":{"sha256":_sha(health),"status":h.get("status")},
        "evidence_index":{"sha256":_sha(evidence),"artifact_count":e.get("artifact_count")},
        "deterministic_metrics":{"sha256":_sha(metrics),"schema":m.get("schema")},
        "immutable_run_binding":True,"no_private_repo_dependency":True,
        "contains_account_state":False,"contains_portfolio_decision":False,
        "no_valuation":True,"no_trade_logic":True}

def main():
    p=argparse.ArgumentParser()
    for x in ("universe","health","evidence-index","metrics","output"):p.add_argument("--"+x,required=True)
    a=p.parse_args();out=build(a.universe,a.health,a.evidence_index,a.metrics)
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"source_run_id":out["source_run_id"],"artifact_count":out["evidence_index"]["artifact_count"]}))
if __name__=="__main__":main()
