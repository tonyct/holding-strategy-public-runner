"""Fetch *located* exchange PDF bytes; never claim content or accounting verification.
No login, proxy, anti-bot bypass or insecure TLS. Only pinned cninfo HTTPS URLs.
"""
import argparse
import hashlib
import json
import os
import io
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

MAX_BYTES=30*1024*1024
ALLOWED_PDF_HOSTS=('static.cninfo.com.cn','static.sse.com.cn','www.sse.com.cn','file.finance.sina.com.cn')
OFFICIAL_HOSTS=('static.cninfo.com.cn','static.sse.com.cn','www.sse.com.cn')

def fetch_one(item, output, session, previous=None):
    symbol=item['symbol']
    previous=previous or {}
    # Reuse only a previously verified original for the same symbol and period.
    if (previous.get('symbol')==symbol and previous.get('status')=='ORIGINAL_PDF_BYTES_DOWNLOADED_NOT_CONTENT_VERIFIED'
            and previous.get('report_period')==item['period'] and previous.get('issuer_name')==item['issuer_name']
            and previous.get('document_type')==item['doc_type']):
        filename=previous.get('filename','')
        file=Path(output)/filename
        if (isinstance(filename,str) and Path(filename).name==filename and filename.endswith('.pdf')
                and file.is_file() and file.stat().st_size>1000
                and hashlib.sha256(file.read_bytes()).hexdigest()==previous.get('sha256')):
            return {**previous,'cache_reused':True,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    urls=[item['url']]+item.get('alternate_urls',[])
    failures=[]
    for url in dict.fromkeys(urls):
        p=urlparse(url)
        if (p.scheme!='https' or p.hostname not in ALLOWED_PDF_HOSTS
                or not p.path.lower().endswith('.pdf')):
            failures.append({'url':url,'reason':'INVALID_OR_UNAPPROVED_SOURCE_URL'})
            continue
        try:
            data=None
            for attempt in range(3):
                try:
                    with session.get(url,stream=True,timeout=(10,60),allow_redirects=True) as response:
                        final=urlparse(response.url)
                        if final.scheme!='https' or final.hostname not in ALLOWED_PDF_HOSTS:
                            raise ValueError('UNAPPROVED_REDIRECT_TARGET')
                        if response.status_code in (408,429,500,502,503,504) and attempt<2:
                            time.sleep(2**attempt); continue
                        response.raise_for_status()
                        if response.status_code!=200: raise ValueError('NON_200_HTTP')
                        content_type=response.headers.get('Content-Type','')
                        data=bytearray()
                        for chunk in response.iter_content(chunk_size=65536):
                            data.extend(chunk)
                            if len(data)>MAX_BYTES: raise ValueError('PDF_SIZE_LIMIT_EXCEEDED')
                    if data is not None and (not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]) and attempt<2:
                        time.sleep(2**attempt)
                        continue
                    break
                except (__import__('requests').exceptions.ConnectionError,__import__('requests').exceptions.Timeout):
                    if attempt==2: raise
                    time.sleep(2**attempt)
            if data is None or not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]:
                prefix=bytes(data[:48]).hex() if data is not None else 'NO_RESPONSE_BYTES'
                raise ValueError('NOT_A_COMPLETE_PDF;content_type='+content_type[:70]+';bytes='+str(len(data) if data is not None else 0)+';prefix_hex='+prefix+';final_host='+final.hostname)
            import pymupdf
            with pymupdf.open(stream=bytes(data),filetype='pdf') as doc:
                if doc.needs_pass or doc.page_count<15: raise ValueError('SUMMARY_OR_UNREADABLE_REPORT')
                page_count=doc.page_count
                front=''.join(doc[i].get_text(sort=True) for i in range(min(15,page_count)))
                # Require evidence of actual three statements, not simply a report-like cover.
                financial=''.join(doc[i].get_text(sort=True) for i in range(page_count))
            front=re.sub(r'\s+','',front)
            financial=re.sub(r'\s+','',financial)
            issuer=re.sub(r'\s+','',item['issuer_name'])
            if issuer not in front and issuer not in financial:
                raise ValueError('ISSUER_IDENTITY_NOT_VERIFIED')
            year=item['period'][:4]
            chinese=''.join('〇一二三四五六七八九'[int(d)] for d in year)
            years=(year,chinese,chinese.replace('〇','零'),chinese.replace('〇','○'))
            if item.get('doc_type')!='FULL_INTERIM_REPORT':
                raise ValueError('SUMMARY_OR_WRONG_DOCUMENT_TYPE')
            if not any(y in front for y in years) or not any(t in front for t in ('半年度','半年报','中期报告','中期财务')):
                raise ValueError('REPORT_PERIOD_OR_TYPE_NOT_VERIFIED')
            mandatory=(('资产负债表',),('利润表','损益表'),('现金流量表',))
            if not all(any(t in financial for t in variants) for variants in mandatory):
                raise ValueError('THREE_STATEMENT_SECTIONS_NOT_FOUND_IN_REPORT')
            sha=hashlib.sha256(data).hexdigest()
            filename=symbol.replace('.','_')+'_'+item['period']+'_'+sha[:16]+'.pdf'
            dest=Path(output)/filename
            if dest.exists():
                if hashlib.sha256(dest.read_bytes()).hexdigest()!=sha:
                    raise ValueError('PERSISTED_PDF_HASH_MISMATCH')
            else:
                with dest.open('xb') as handle:
                    handle.write(data);handle.flush();os.fsync(handle.fileno())
            return {'symbol':symbol,'status':'ORIGINAL_PDF_BYTES_DOWNLOADED_NOT_CONTENT_VERIFIED',
                    'source_url':url,'source_provenance':('OFFICIAL_DIRECT' if p.hostname in OFFICIAL_HOSTS else 'THIRD_PARTY_MIRROR_STRICT_CONTENT_CHECKED'), 'filename':filename,'bytes':len(data),'pages':page_count,
                    'sha256':sha,'document_type':item['doc_type'],
                    'report_period':item['period'],'issuer_name':item['issuer_name'],'cache_reused':False,
                    'issuer_identity_verified_from_pdf':True,'report_period_text_verified':True,
                    'three_statement_sections_found':True,'statement_reconciled':False,
                    'notes_verified':False,'failed_candidates':failures}
        except Exception as exc:
            failures.append({'url':url,'reason':type(exc).__name__+':'+str(exc)[:130]})
    return {'symbol':symbol,'status':'PDF_FETCH_FAILED','failed_candidates':failures}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--universe-file',required=True);ap.add_argument('--period',required=True)
    args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    import requests
    manifest=json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    if manifest.get('schema')!='OFFICIAL_FILINGS_LOCATOR/v1':raise ValueError('INVALID_MANIFEST')
    from universe import load_universe
    active=load_universe(args.universe_file)['a_shares']
    reports=manifest.get('reports',[])
    # Exact match prevents mislabeling stale PDFs when the universe changes.
    if len(reports)!=len(active) or set(x.get('symbol') for x in reports)!=set(active):
        raise ValueError('MANIFEST_ACTIVE_UNIVERSE_MISMATCH')
    if any(x.get('period')!=args.period for x in reports):
        raise ValueError('MANIFEST_REPORT_PERIOD_MISMATCH')
    previous_file=out/'OFFICIAL_PDF_FETCH_RECEIPT.json'
    try:
        previous_data=json.loads(previous_file.read_text(encoding='utf-8'))
        previous={r['symbol']:r for r in previous_data.get('rows',[]) if isinstance(r,dict) and 'symbol' in r}
    except (OSError,ValueError):
        previous={}
    with requests.Session() as session:
        rows=[fetch_one(item,out,session,previous.get(item['symbol'])) for item in manifest['reports']]
    # Browser is a diagnostic/recovery fallback for already failed downloads only.
    # A browser result is never marked successful until fetch_one passes the same PDF checks.
    if os.getenv('ENABLE_OFFICIAL_BROWSER_RECOVERY')=='1':
        from browser_pdf_recovery import recover,BytesSession
        for item,row in zip(manifest['reports'],rows):
            if row['status']!='PDF_FETCH_FAILED':continue
            diagnostics=[]
            for url in dict.fromkeys([item['url']]+item.get('alternate_urls',[])):
                if urlparse(url).hostname not in OFFICIAL_HOSTS:continue
                try:
                    result=recover(url)
                    diagnostics.append({k:v for k,v in result.items() if k!='bytes'})
                    if result.get('status')=='ACCESS_RESTRICTED':break
                    if result.get('status')!='PDF_BYTES':continue
                    checked=fetch_one({**item,'url':url,'alternate_urls':[]},out,BytesSession(result['bytes'],url))
                    if checked['status']=='ORIGINAL_PDF_BYTES_DOWNLOADED_NOT_CONTENT_VERIFIED':
                        checked['acquisition_method']='PLAYWRIGHT_CHROMIUM'
                        checked['failed_candidates']=row['failed_candidates']
                        checked['browser_diagnostics']=diagnostics
                        row.clear();row.update(checked)
                        break
                    diagnostics.append({'status':'BROWSER_BYTES_REJECTED_BY_STRICT_VALIDATOR',
                                        'failed_candidates':checked['failed_candidates']})
                except Exception as exc:
                    diagnostics.append({'status':'BROWSER_ERROR','error_type':type(exc).__name__})
            row['browser_diagnostics']=diagnostics
    receipt={'schema':'OFFICIAL_PDF_FETCH_RECEIPT/v1','universe_sha256':load_universe(args.universe_file)['universe_sha256'],
             'report_period':args.period,'checked_at_utc':datetime.now(timezone.utc).isoformat(),
             'complete_content_verified':0,'rows':rows}
    (out/'OFFICIAL_PDF_FETCH_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps({'located':len(rows),'downloaded':sum(x['status'].startswith('ORIGINAL_PDF') for x in rows)},ensure_ascii=False))
    return 0 if len(rows)>0 and all(x['status'].startswith('ORIGINAL_PDF') for x in rows) else 1

if __name__=='__main__':raise SystemExit(main())