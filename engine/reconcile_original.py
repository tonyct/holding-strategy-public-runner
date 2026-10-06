"""Fail-closed core-five financial reconciliation against issuer report PDF.
A matching figure is NOT proof that the full statement, notes or accounting basis
has been independently audited; preserve source lineage and page-level evidence.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

FIELDS = {
    'operating_revenue': ('营业收入',),
    'attributable_net_profit': ('归属于上市公司股东的净利','归属于母公司股东的净利润','归属于母公司所有者的净利润','归属母公司股东的净利润','归母净利润'),
    'total_assets': ('资产总计','资产合计','总资产'),
    'total_liabilities': ('负债合计','总负债'),
    'operating_cashflow': ('经营活动产生的现金流量净额',)
}
NUMBERS = re.compile(r'(?<![\d.])\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|(?<![\d.])\(?-?\d{4,}(?:\.\d+)?\)?')
SCALES = (Decimal(1), Decimal(1000), Decimal(10000), Decimal(1000000))


def check_pdf(pdf_path, values):
    import fitz
    result = {}
    with fitz.open(str(pdf_path)) as doc:
        if doc.needs_pass or doc.page_count < 2:
            raise ValueError('PDF_ENCRYPTED_OR_TOO_SHORT')
        for field, labels in FIELDS.items():
            if field not in values:
                result[field] = {'status':'UPSTREAM_FIELD_MISSING'}
                continue
            try:
                expected = Decimal(str(values[field]))
            except InvalidOperation:
                result[field] = {'status':'INVALID_UPSTREAM_NUMBER'}
                continue
            matches=[]
            for page_no, page in enumerate(doc, 1):
                lines=page.get_text(sort=True).splitlines()
                for idx,line in enumerate(lines):
                    if not any(label in line for label in labels):
                        continue
                    # Same-line or next-line values; do not cross page/section boundaries.
                    block=line + (' '+lines[idx+1] if idx+1<len(lines) and len(line.strip())<24 else '')
                    for m in NUMBERS.finditer(block):
                        token=m.group().strip('()')
                        try: number=Decimal(token.replace(',',''))
                        except InvalidOperation:continue
                        for scale in SCALES:
                            tolerance=(Decimal('0.5') if '.' not in token else Decimal('0.5') / (Decimal(10)**len(token.split('.')[-1]))) * scale
                            if abs(expected-number*scale)<=tolerance:
                                matches.append({'pdf_page':page_no,'pdf_value':token,'candidate_scale_to_yuan':str(scale),'excerpt':block.strip()[:180]})
                                break
                    if matches:break
                if matches:break
            result[field]={'status':'PRIMARY_PDF_CORE_FIELD_MATCH' if matches else 'NOT_MATCHED_OR_PDF_LAYOUT',
                           'adapter_reported_value':str(expected),'evidence':matches[:1]}
    return result


def reconcile(financial_receipt, pdf_receipt, root, output):
    financial=json.loads(Path(financial_receipt).read_text(encoding='utf-8'))
    original=json.loads(Path(pdf_receipt).read_text(encoding='utf-8'))
    pdf_by_symbol={r['symbol']:r for r in original.get('rows',[])}
    results=[]
    for item in financial.get('tickers',[]):
        symbol=item['symbol']
        entry={'symbol':symbol,'checks':{},'status':'RECONCILIATION_FAILED'}
        try:
            pdf=pdf_by_symbol.get(symbol)
            if not pdf or not pdf.get('status','').startswith('ORIGINAL_PDF_BYTES_DOWNLOADED'):
                raise ValueError('ORIGINAL_PDF_MISSING_OR_REJECTED')
            if not pdf.get('issuer_identity_verified_from_pdf') or not pdf.get('report_period_text_verified'):
                raise ValueError('PDF_IDENTITY_OR_PERIOD_NOT_VERIFIED')
            pdf_path=Path(pdf_receipt).parent/pdf['filename']
            blob=pdf_path.read_bytes()
            if hashlib.sha256(blob).hexdigest()!=pdf['sha256']:
                raise ValueError('ORIGINAL_PDF_HASH_MISMATCH')
            snap=Path(root)/'snapshots'/item['snapshot_file']
            raw=snap.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['snapshot_sha256']:
                raise ValueError('FINANCIAL_SNAPSHOT_HASH_MISMATCH')
            body=json.loads(raw)
            if body.get('symbol')!=symbol or body.get('period')!=financial['report_period_end']:
                raise ValueError('FINANCIAL_SNAPSHOT_SYMBOL_OR_PERIOD_MISMATCH')
            vals={}
            for section in ('income','balance','cashflow'):
                stmt=body['statements'][section]
                if stmt['status']!='FETCHED_UNVERIFIED_PRIMARY_FILING':
                    raise ValueError(section+'_NOT_FETCHED')
                data=stmt['data']
                # Automatic yuan comparisons are permitted only for upstream values
                # explicitly normalized to yuan or native AKShare Sina records.
                normalized=data.get('normalized_cny_yuan') or {}
                if normalized:vals.update(normalized)
                elif data.get('source')=='AKSHARE_SINA':vals.update(data.get('standard_fields') or {})
                else:raise ValueError(section+'_UNIT_NOT_NORMALIZED')
            entry['checks']=check_pdf(pdf_path,vals)
            entry['pdf_sha256']=pdf['sha256']
            entry['snapshot_sha256']=item['snapshot_sha256']
            entry['status']='CORE_FIVE_MATCH_UNVERIFIED_NOTES' if all(x['status']=='PRIMARY_PDF_CORE_FIELD_MATCH' for x in entry['checks'].values()) else 'CORE_FIELD_MISMATCH_OR_MISSING'
        except Exception as exc:
            entry['error']=type(exc).__name__+':'+str(exc)[:180]
        results.append(entry)
    passed=sum(x['status']=='CORE_FIVE_MATCH_UNVERIFIED_NOTES' for x in results)
    receipt={'schema':'E36_PRIMARY_PDF_CORE_RECONCILIATION/v1','scope':'FIVE_CORE_FIELDS_PER_A_SHARE_NOT_FULL_AUDIT',
             'universe_sha256':financial.get('universe_sha256'),'requested':len(financial.get('active_a_shares',[])),
             'matched_symbols':passed,'matched_fields':sum(sum(v['status']=='PRIMARY_PDF_CORE_FIELD_MATCH' for v in x['checks'].values()) for x in results),
             'notes_verified':0,'full_statements_audited':0,'production_ready':False,'rows':results}
    Path(output).write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--financial-receipt',required=True)
    p.add_argument('--pdf-receipt',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    x=reconcile(args.financial_receipt,args.pdf_receipt,Path(args.financial_receipt).parent,args.output)
    print(json.dumps({k:x[k] for k in ('requested','matched_symbols','matched_fields','production_ready')},ensure_ascii=False))
    return 0 if x['requested']>0 and x['matched_symbols']==x['requested'] and x['matched_fields']==x['requested']*5 else 1

if __name__=='__main__':raise SystemExit(main())