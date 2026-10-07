"""E36 A-share financial data gateway. No changes to SHADOW/MAIN/INTRADAY control flow.

Optional runtime dependency: `pip install akshare pandas`. No account or scraping bypass.
Only financial data; official issuer/exchange financial PDF verification is separate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable

A_SHARES = ('600941.SH', '001286.SZ', '603993.SH', '600499.SH', '600795.SH', '603871.SH', '601857.SH')
STATEMENTS = ('income', 'balance', 'cashflow')
# Reject irrelevant numeric metadata being counted as a complete statement.
CORE_FIELDS = {'income': frozenset(('revenue','operating_revenue','attributable_net_profit','net_profit')),
               'balance': frozenset(('total_assets','total_liabilities')),
               'cashflow': frozenset(('operating_cashflow',))}
SINA_NAMES = {'income': '利润表', 'balance': '资产负债表', 'cashflow': '现金流量表'}
EM_APIS = {'income': 'stock_profit_sheet_by_report_em',
           'balance': 'stock_balance_sheet_by_report_em',
           'cashflow': 'stock_cash_flow_sheet_by_report_em'}
DATE_FIELDS = ('REPORT_DATE', '报告日', '报告期', '报告日期', '报表日期', '截止日期', '报表截止日期', '会计期间', '截止日')
# Standard names are evidence conveniences, never substitute for retained raw original fields.
ALIASES = {
    'TOTAL_OPERATE_INCOME': 'revenue', 'TOTAL_OPERATING_REVENUE': 'revenue', '营业总收入': 'revenue',
    'OPERATE_INCOME': 'operating_revenue', '营业收入': 'operating_revenue',
    'PARENT_NETPROFIT': 'attributable_net_profit', '归属于母公司所有者的净利润': 'attributable_net_profit',
    'NETPROFIT': 'net_profit', '净利润': 'net_profit',
    'TOTAL_ASSETS': 'total_assets', '资产总计': 'total_assets',
    'TOTAL_LIABILITIES': 'total_liabilities', '负债合计': 'total_liabilities',
    'NETCASH_OPERATE': 'operating_cashflow', '经营活动产生的现金流量净额': 'operating_cashflow',
}

class SourceUnavailable(Exception): pass


def canonical_symbol(symbol: str) -> str:
    x = symbol.upper().strip()
    if not re.fullmatch(r'\d{6}\.(SH|SZ)', x):
        raise ValueError(f'Only 6-digit A-share .SH/.SZ supported: {symbol!r}')
    return x


def ak_prefix(symbol: str) -> str:
    code, exchange = canonical_symbol(symbol).split('.')
    return exchange + code


def sina_prefix(symbol: str) -> str:
    code, exchange = canonical_symbol(symbol).split('.')
    return ('sh' if exchange == 'SH' else 'sz') + code


def get_akshare():
    try:
        import akshare  # lazy: importing library may initialize optional code
        return akshare
    except ImportError as exc:
        raise SourceUnavailable('AKShare is not installed; install in a network-enabled worker: pip install akshare pandas') from exc


def report_date(value) -> str | None:
    if value is None: return None
    s = str(value).strip()
    if not s or s.lower() in ('nan', 'nat', 'none'): return None
    m = re.search(r'((?:19|20)\d{2})[-/]?(\d{2})[-/]?(\d{2})', s)
    if m:
        try: return datetime(int(m[1]), int(m[2]), int(m[3])).date().isoformat()
        except ValueError: return None
    return None


def normalize_number(value):
    if value is None or isinstance(value, bool): return None
    if isinstance(value, (int, float)):
        if isinstance(value,float) and not math.isfinite(value): return None
        return str(Decimal(str(value)))
    if isinstance(value,str):
        s=value.strip().replace(',','')
        if s in ('','--','—','-','None','nan','NaN','不适用'):return None
        try:
            n=Decimal(s)
            return str(n) if n.is_finite() else None
        except InvalidOperation:return None
    return None


def frame_records(frame):
    """Accept AKShare DataFrame; dictionaries/lists allowed for hermetic test fixtures."""
    if hasattr(frame,'to_dict'):
        return frame.to_dict(orient='records')
    if isinstance(frame,dict):
        return [frame]
    if isinstance(frame,list):
        return frame
    raise SourceUnavailable(f'unsupported frame type {type(frame).__name__}')


def normalize_frame(frame, *, symbol: str, statement: str, period: str, source: str,
                    collected_at: str, expected_currency='CNY') -> dict:
    rows=frame_records(frame)
    if not rows:raise SourceUnavailable('empty_dataframe')
    candidates=[]
    for row in rows:
        if not isinstance(row,dict):continue
        date=next((report_date(row[k]) for k in DATE_FIELDS if k in row and report_date(row[k])),None)
        if date==period:candidates.append(row)
    if not candidates: raise SourceUnavailable(f'requested_period_not_found:{period}')
    if len(candidates)>1: raise SourceUnavailable(f'ambiguous_report_rows:{len(candidates)}')
    row=candidates[0]
    raw={str(k): (None if v is None or str(v).strip().lower() in ('nan','nat') else str(v)) for k,v in row.items()}
    data={}
    for k,v in row.items():
        name=ALIASES.get(str(k).strip().upper()) or ALIASES.get(str(k).strip())
        if name:
            num=normalize_number(v)
            if num is not None:
                if name in data and data[name]!=num: raise SourceUnavailable(f'conflicting_mapped_field:{name}')
                data[name]=num
    if not any(normalize_number(v) is not None for k,v in row.items() if k not in DATE_FIELDS):
        raise SourceUnavailable('report_row_has_no_numeric_data')
    if not CORE_FIELDS[statement].intersection(data):
        raise SourceUnavailable(f'missing_core_financial_fields:{statement}')
    return {'symbol':symbol,'statement':statement,'report_period_end':period,
            'basis':'REPORTED_PERIOD_AS_PROVIDED_NOT_ASSUMED_SINGLE_QUARTER',
            'currency':expected_currency,'raw_numeric_unit':(str(row.get('SOURCE_UNIT')) if str(row.get('SOURCE_UNIT','')) in ('CNY_MILLIONS','CNY_YUAN','CNY_TEN_THOUSANDS','CNY_THOUSANDS') else 'AS_RETURNED_BY_SOURCE_VERIFY_BEFORE_COMPARISON'),
            'standard_fields':data,'original_fields':raw,
            'normalized_cny_yuan':normalize_currency_units(data,str(row.get('SOURCE_UNIT') or '')),
            'content_scope':'CORE_FIELDS_ONLY' if source=='USER_SUPPLIED_FILE' else 'FIELDS_RETURNED_COMPLETENESS_UNVERIFIED',
            'source_url':str(row.get('SOURCE_URL') or '') or None,'source_document':str(row.get('SOURCE_DOCUMENT') or '') or None,'accounting_scope':str(row.get('ACCOUNTING_SCOPE') or '') or 'UNVERIFIED','source':source,'source_family':'SINA' if source=='AKSHARE_SINA' else ('USER_SUPPLIED' if source=='USER_SUPPLIED_FILE' else 'EASTMONEY'),
            'source_published_at':next((report_date(row[k]) for k in ('NOTICE_DATE','ANNOUNCEMENT_DATE','公告日期','披露日期','公告日') if k in row and report_date(row[k])),None),'collected_at':collected_at,
            'quality':'FETCHED_UNVERIFIED_PRIMARY_FILING'}


UNIT_FACTORS={'CNY_YUAN':Decimal('1'),'CNY_THOUSANDS':Decimal('1000'),
              'CNY_TEN_THOUSANDS':Decimal('10000'),'CNY_MILLIONS':Decimal('1000000')}

def normalize_currency_units(fields, unit):
    """Convert monetary fields to CNY yuan; NEVER convert per-share/ratio fields."""
    factor=UNIT_FACTORS.get(unit)
    return {k:str(Decimal(v)*factor) for k,v in fields.items()
            if factor is not None and k in ('revenue','operating_revenue','attributable_net_profit',
                                              'net_profit','total_assets','total_liabilities','operating_cashflow')}

class RateLimiter:
    def __init__(self, interval=1.2, clock=None, sleep=None):
        self.interval=float(interval)
        self.clock=clock or time.monotonic
        self.sleep=sleep or time.sleep
        self.last={}
    def wait(self,family):
        now=self.clock()
        until=self.last.get(family,now)
        if until>now:self.sleep(until-now)
        self.last[family]=self.clock()+self.interval


class SourceHealth:
    """Per-run breaker with bounded half-open recovery probes.

    Repeated transport failures temporarily suppress a source so fallbacks get
    a chance, but the source is not abandoned for the entire run.  After a
    small number of skipped requests one half-open probe is allowed. Semantic
    or report-period misses never trip the breaker.
    """
    def __init__(self, threshold=3, probe_after_skips=2):
        self.threshold=max(1,int(threshold))
        self.probe_after_skips=max(1,int(probe_after_skips))
        self.state={}
    def is_open(self,source):
        row=self.state.get(source)
        if not row or row.get('open') is not True:
            return False
        row['skipped_while_open']=int(row.get('skipped_while_open',0))+1
        if row['skipped_while_open']>=self.probe_after_skips:
            row['open']=False
            row['half_open_probe']=True
            row['skipped_while_open']=0
            return False
        return True
    def success(self,source):
        self.state[source]={'consecutive_transport_failures':0,'open':False,
                            'skipped_while_open':0,'half_open_probe':False}
    def failure(self,source,error):
        text=(type(error).__name__+':'+str(error)).casefold()
        transient=any(x in text for x in (
            'timeout','connectionerror','connection aborted','connection reset',
            'temporarily unavailable','remote disconnected','429','500','502','503','504'))
        if not transient:
            return False
        row=self.state.setdefault(source,{'consecutive_transport_failures':0,'open':False,
                                          'skipped_while_open':0,'half_open_probe':False})
        if row.get('half_open_probe'):
            row.update(consecutive_transport_failures=self.threshold,open=True,
                       skipped_while_open=0,half_open_probe=False)
            return True
        row['consecutive_transport_failures']+=1
        if row['consecutive_transport_failures']>=self.threshold:
            row['open']=True
            row['skipped_while_open']=0
        return row['open']
    def snapshot(self):
        return {k:dict(v) for k,v in self.state.items()}



class AKShareProviders:
    def __init__(self,ak=None):self.ak=ak or get_akshare()
    def fetch(self,source:str,statement:str,symbol:str):
        if source=='AKSHARE_SINA':
            return self.ak.stock_financial_report_sina(stock=sina_prefix(symbol),symbol=SINA_NAMES[statement])
        if source=='AKSHARE_EASTMONEY':
            return getattr(self.ak,EM_APIS[statement])(symbol=ak_prefix(symbol))
        raise ValueError('Unknown source '+source)


class LocalFinancialProvider:
    """Explicitly supplied, auditable CSV/JSON rows. Not an automated data-source connection.

    Layout: INPUT_DIR/SYMBOL/STATEMENT.csv|json. The file must contain a report
    period column and a core mapped field. Its presence does not verify issuer origin.
    """
    def __init__(self, directory): self.directory=Path(directory)
    def fetch(self, source, statement, symbol):
        if source != 'USER_SUPPLIED_FILE': raise ValueError(source)
        root=self.directory/canonical_symbol(symbol)
        csvpath=root/f'{statement}.csv'
        jsonpath=root/f'{statement}.json'
        if jsonpath.is_file():
            with jsonpath.open(encoding='utf-8-sig') as f: return json.load(f)
        if csvpath.is_file():
            import csv
            with csvpath.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
        raise SourceUnavailable(f'file_missing:{jsonpath} or {csvpath}')


class FinancialAdapter:
    def __init__(self,providers=None,limiter=None,retries=1,sleep=None,now=None,local_provider=None,direct_provider=None,offline_only=False,source_health=None):
        self.providers=providers or AKShareProviders()
        self.limiter=limiter or RateLimiter()
        self.retries=retries
        self.sleep=sleep or time.sleep
        self.now=now or (lambda:datetime.now(timezone.utc).isoformat())
        self.local_provider=local_provider
        self.direct_provider=direct_provider
        self.offline_only=offline_only
        self.source_health=source_health or SourceHealth()

    def fetch_statement(self,symbol,statement,period):
        symbol=canonical_symbol(symbol)
        if statement not in STATEMENTS:raise ValueError('unsupported statement '+statement)
        if not re.fullmatch(r'20\d\d-(03-31|06-30|09-30|12-31)',period):
            raise ValueError('period must be YYYY-03-31/06-30/09-30/12-31')
        attempts=[]
        sources=['USER_SUPPLIED_FILE'] if self.offline_only else ['AKSHARE_SINA','AKSHARE_EASTMONEY']
        if self.direct_provider is not None and not self.offline_only: sources.append('DIRECT_EASTMONEY')
        if self.local_provider is not None and not self.offline_only: sources.append('USER_SUPPLIED_FILE')
        for source in sources:
            if self.source_health.is_open(source):
                attempts.append({'source':source,'try':0,'error':'SOURCE_CIRCUIT_OPEN_AFTER_REPEATED_TRANSPORT_FAILURES'})
                continue
            for attempt in range(self.retries+1):
                try:
                    self.limiter.wait('SINA' if source=='AKSHARE_SINA' else ('USER_SUPPLIED' if source=='USER_SUPPLIED_FILE' else 'EASTMONEY'))
                    if source=='DIRECT_EASTMONEY':
                        frame=self.direct_provider.fetch(source,statement,symbol,period)
                    else:
                        frame=(self.local_provider if source=='USER_SUPPLIED_FILE' else self.providers).fetch(source,statement,symbol)
                    result=normalize_frame(frame,symbol=symbol,statement=statement,period=period,
                                           source=source,collected_at=self.now())
                    if source=='USER_SUPPLIED_FILE':
                        result['source_family']='USER_SUPPLIED';result['quality']='FETCHED_UNVERIFIED_USER_FILE'
                    self.source_health.success(source)
                    return {'status':result['quality'],'data':result,'attempts':attempts}
                except Exception as exc:
                    msg=f'{type(exc).__name__}:{str(exc)[:220]}'
                    attempts.append({'source':source,'try':attempt+1,'error':msg})
                    opened=self.source_health.failure(source,exc)
                    # Missing exact report period or empty upstream response is not transient.
                    if isinstance(exc,SourceUnavailable) and any(t in str(exc) for t in
                        ('requested_period_not_found','empty_dataframe','no_numeric_data','ambiguous_report_rows','missing_core_financial_fields','empty_statement','file_missing')):
                        break
                    if opened: break
                    if attempt<self.retries:self.sleep(min(8,1.5*(2**attempt)+random.random()*.2))
        return {'status':'SOURCE_UNAVAILABLE','data':None,'attempts':attempts}

    def fetch_company(self,symbol,period):
        out={k:self.fetch_statement(symbol,k,period) for k in STATEMENTS}
        count=sum(out[k]['status'] in ('FETCHED_UNVERIFIED_PRIMARY_FILING','FETCHED_UNVERIFIED_USER_FILE') for k in STATEMENTS)
        return {'symbol':canonical_symbol(symbol),'period':period,
                'status':'CORE_THREE_STATEMENTS_UNVERIFIED' if count==3 else 'DATA_PARTIAL' if count else 'SOURCE_UNAVAILABLE',
                'completeness':'CORE_FIELDS_ONLY_NOT_FULL_REPORT' if count==3 else 'INCOMPLETE',
                'fetched_statements':count,'required_statements':3,'statements':out,
                'source_health':self.source_health.snapshot()}


def persist_snapshot(record,folder):
    """Immutable point-in-time acquisition snapshot: preserve revisions rather than overwrite."""
    Path(folder).mkdir(parents=True,exist_ok=True)
    payload=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    digest=hashlib.sha256(payload).hexdigest()
    path=Path(folder)/(f'{record["symbol"].replace(".","_")}_{record["period"]}_{digest[:16]}.json')
    if path.exists():
        if path.read_bytes()!=payload:raise RuntimeError('hash_collision_or_modified_snapshot')
        return str(path)
    tmp=path.with_suffix('.tmp')
    with open(tmp,'xb') as f:
        f.write(payload);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    return str(path)


def main():
    p=argparse.ArgumentParser(description='Real AKShare A-share financial fetcher; no simulated success')
    p.add_argument('--period',default='2026-06-30')
    p.add_argument('--symbols',nargs='*',default=list(A_SHARES))
    p.add_argument('--output',default='snapshots')
    p.add_argument('--delay',type=float,default=1.2)
    p.add_argument('--retries',type=int,default=1)
    p.add_argument('--input-dir',default=None,help='Optional user-provided SYMBOL/income,balance,cashflow CSV or JSON files')
    p.add_argument('--offline-only',action='store_true',help='Use ONLY explicitly provided local data; skip unavailable network calls')
    p.add_argument('--direct-eastmoney',action='store_true',help='Enable public Eastmoney requests fallback, no AKShare required')
    args=p.parse_args()
    try:
        provider=AKShareProviders()
    except SourceUnavailable as exc:
        if not args.input_dir and not args.direct_eastmoney:
            print(json.dumps({'status':'ENVIRONMENT_BLOCKED','reason':str(exc)},ensure_ascii=False));return 2
        provider=None
    if args.offline_only and not args.input_dir: p.error('--offline-only requires --input-dir')
    if provider is None:
        class UnavailableProvider:
            def fetch(self,source,statement,symbol):raise SourceUnavailable('akshare_not_installed')
        provider=UnavailableProvider()
    direct_provider=None
    direct_provider_state="NOT_REQUESTED"
    if args.direct_eastmoney:
        try:
            from direct_eastmoney import DirectEastmoneyProvider
            direct_provider=DirectEastmoneyProvider()
            direct_provider_state="AVAILABLE"
        except ModuleNotFoundError as exc:
            if exc.name != "direct_eastmoney":
                raise
            direct_provider_state="OPTIONAL_MODULE_MISSING_AKSHARE_FALLBACK"
            print(json.dumps({"warning":"DIRECT_EASTMONEY_MODULE_UNAVAILABLE","fallback":"AKSHARE_SINA_AND_EASTMONEY"}),file=sys.stderr)
    adapter=FinancialAdapter(providers=provider,limiter=RateLimiter(0 if args.offline_only else args.delay),
                             retries=max(0,min(args.retries,4)),
                             local_provider=LocalFinancialProvider(args.input_dir) if args.input_dir else None,
                             direct_provider=direct_provider,offline_only=args.offline_only)
    result=[]
    for symbol in args.symbols:
        try:
            data=adapter.fetch_company(symbol,args.period)
            data['snapshot_path']=persist_snapshot(data,args.output)
        except Exception as exc:
            data={'symbol':symbol,'status':'ERROR','error':f'{type(exc).__name__}:{str(exc)[:200]}'}
        result.append(data)
        print(json.dumps({'symbol':symbol,'status':data['status'],
                          'statements':data.get('fetched_statements',0),
                          'snapshot_path':data.get('snapshot_path')},ensure_ascii=False))
    print(json.dumps({'total':len(result),'three_statements':sum(d['status']=='CORE_THREE_STATEMENTS_UNVERIFIED' for d in result),
                      'partial':sum(d['status']=='DATA_PARTIAL' for d in result),
                      'direct_eastmoney_provider':direct_provider_state},ensure_ascii=False))
    return 0 if all(d['status']=='CORE_THREE_STATEMENTS_UNVERIFIED' for d in result) else 1

if __name__=='__main__':raise SystemExit(main())