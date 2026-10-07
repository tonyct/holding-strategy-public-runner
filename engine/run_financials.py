"""External E36 financial collector. Never claims original filing verification.
Runtime: GitHub Actions/private repository or any persistent networked Linux worker.
"""
try:
    from .financial_period import resolve_period
except ImportError:
    from financial_period import resolve_period

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import hashlib

try:
    from .universe import load_universe, compare_previous, UniverseError
except ImportError:
    from universe import load_universe, compare_previous, UniverseError

def select_current_run_snapshot(all_files, before_files):
    """Select exactly one immutable snapshot created by this invocation."""
    before={str(x) for x in before_files}
    current=[x for x in all_files if str(x) not in before]
    if len(current)==1:
        return current[0],{"current_run_snapshot_count":1,
                          "snapshot_history_count":len(all_files)}
    return None,{"current_run_snapshot_count":len(current),
                 "snapshot_history_count":len(all_files)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--period', default='auto')
    p.add_argument('--output', default='output')
    p.add_argument('--offline-only', action='store_true')
    p.add_argument('--input-dir', default=None)
    p.add_argument('--universe-file',default='config/research_universe.json')
    p.add_argument('--previous-receipt',default=None)
    p.add_argument('--retries',type=int,default=1)
    args = p.parse_args()
    args.period=resolve_period(args.period,"A")
    if args.offline_only and not args.input_dir:
        p.error('--input-dir is necessary for offline mode')
    root = Path(args.output)
    snaps = root/'snapshots'
    root.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc).isoformat()
    try:
        universe=load_universe(args.universe_file)
        change=compare_previous(universe,args.previous_receipt)
    except (OSError,UniverseError) as exc:
        failure={'schema':'E36_external_acquisition_receipt/v2','status':'UNIVERSE_VALIDATION_FAILED','run_started_utc':start,'error':str(exc),'research_generation_created':False,'production_integration_verified':False}
        (root/'ACQUISITION_RECEIPT.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(failure,ensure_ascii=False));return 2
    a_shares=universe['a_shares']
    if not a_shares:
        receipt={'schema':'E36_external_acquisition_receipt/v2','status':'NO_ACTIVE_A_SHARES','run_started_utc':start,'universe':universe,'universe_active_symbols':universe['active'],'change':change,'research_generation_created':False,'production_integration_verified':False}
        (root/'ACQUISITION_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');return 0
    before_snapshots={ticker:{str(x) for x in snaps.glob(ticker.replace('.','_')+'_'+args.period+'_*.json')}
                      for ticker in a_shares}
    cmd = [sys.executable, str(Path(__file__).resolve().parent/'financial_adapter.py'), '--period', args.period, '--output', str(snaps), '--delay','1.5','--retries',str(max(0,min(args.retries,4))),'--symbols',*a_shares]
    if args.offline_only:
        cmd.extend(['--offline-only','--input-dir', args.input_dir])
    else:
        cmd.append('--direct-eastmoney')
    runner_error=None
    try:
        done = subprocess.run(cmd, text=True, capture_output=True, timeout=900)
        returncode=done.returncode
        out,err=done.stdout,done.stderr
    except subprocess.TimeoutExpired as exc:
        runner_error='COLLECTOR_TIMEOUT_900S'
        returncode=124
        out=exc.stdout or b''
        err=exc.stderr or b''
    except OSError as exc:
        runner_error='COLLECTOR_SPAWN_ERROR:'+type(exc).__name__
        returncode=127
        out=''
        err=str(exc)
    if isinstance(out,bytes): out=out.decode('utf-8',errors='replace')
    if isinstance(err,bytes): err=err.decode('utf-8',errors='replace')
    (root/'collector.stdout.log').write_text(out, encoding='utf-8')
    (root/'collector.stderr.log').write_text(err, encoding='utf-8')
    rows=[]
    for ticker in a_shares:
        files=list(snaps.glob(ticker.replace('.','_')+'_'+args.period+'_*.json'))
        selected,selection=select_current_run_snapshot(files,before_snapshots.get(ticker,set()))
        if selected is None:
            rows.append({'symbol':ticker,'status':'MISSING_OR_AMBIGUOUS_CURRENT_RUN_SNAPSHOT',
                         **selection})
            continue
        try:
            raw=selected.read_bytes()
            r=json.loads(raw)
        except (OSError, ValueError) as exc:
            rows.append({'symbol':ticker,'status':'INVALID_SNAPSHOT','error_type':type(exc).__name__})
            continue
        digest=hashlib.sha256(raw).hexdigest()
        ss=r.get('statements',{})
        rows.append({'symbol':ticker,'status':r.get('status'), 'snapshot_file':selected.name,
                     **selection,
                     'retrieved_statements':r.get('fetched_statements',0), 'snapshot_sha256':digest,
                     'statement_status':{k:ss.get(k,{}).get('status','MISSING') for k in ('income','balance','cashflow')},
                     'source':{k:(ss.get(k,{}).get('data') or {}).get('source') for k in ('income','balance','cashflow')},
                     'quality': 'CORE_FIELDS_ONLY_UNVERIFIED_PRIMARY' if r.get('fetched_statements')==3 else 'INCOMPLETE'})
    coverage=sum(r.get('retrieved_statements')==3 for r in rows)
    manifest={'schema':'E36_external_acquisition_receipt/v2','universe_version':universe['universe_version'],'universe_sha256':universe['universe_sha256'],'universe_source':universe['source'],'universe_active_symbols':universe['active'],'active_a_shares':a_shares,'active_hk_shares_not_collected':universe['hk_shares'],'change':change,'run_started_utc':start,'run_ended_utc':datetime.now(timezone.utc).isoformat(),
              'report_period_end':args.period,'runner_exit_code':returncode,'runner_error':runner_error,'ticker_count':len(a_shares),
              'core_three_statement_count':coverage,'complete_original_filing_verified':0,'research_generation_created':False,
              'production_integration_verified':False,'tickers':rows,
              'runner_stdout_tail':out[-4000:] if returncode!=0 else None,
              'runner_stderr_tail':err[-4000:] if returncode!=0 else None,
              'status':'CORE_FIELDS_FETCHED_UNVERIFIED' if coverage==len(a_shares) and returncode==0 else 'DATA_PARTIAL_OR_BLOCKED'}
    (root/'ACQUISITION_RECEIPT.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':manifest['status'],'core_three_statement_count':coverage,'total':len(a_shares),'receipt':str(root/'ACQUISITION_RECEIPT.json')},ensure_ascii=False))
    return 0 if coverage==len(a_shares) and returncode==0 else 1

if __name__=='__main__': raise SystemExit(main())
