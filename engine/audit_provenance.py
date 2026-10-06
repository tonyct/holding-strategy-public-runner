"""E36 offline financial sample audit; does not claim issuer PDF verification."""
import json,hashlib
from pathlib import Path
from decimal import Decimal
from financial_adapter import A_SHARES,STATEMENTS,normalize_frame,LocalFinancialProvider

def audit(root):
    root=Path(root); manifest=json.loads((root/'REAL_DATA_MANIFEST.json').read_text())
    issues=[]; per_symbol={}; successes=0
    for symbol in A_SHARES:
        m=manifest['symbols'].get(symbol)
        if not m: issues.append(f'{symbol}:missing_manifest'); continue
        per_symbol[symbol]={}
        for kind in STATEMENTS:
            path=root/'user_inputs'/symbol/(kind+'.json')
            if not path.is_file(): issues.append(f'{symbol}.{kind}:missing_file');continue
            raw=path.read_bytes(); rows=json.loads(raw)
            try:
                r=normalize_frame(rows,symbol=symbol,statement=kind,period=manifest['report_period'],source='USER_SUPPLIED_FILE',collected_at='AUDIT_ONLY')
                if r['source_url']!=m['source_url']:issues.append(f'{symbol}.{kind}:source_url_mismatch')
                if r['source_published_at']!=m['source_published_at']:issues.append(f'{symbol}.{kind}:published_date_mismatch')
                if r['raw_numeric_unit']!=m['original_unit']:issues.append(f'{symbol}.{kind}:unit_mismatch')
                if not r['normalized_cny_yuan']:issues.append(f'{symbol}.{kind}:unconvertible_monetary_fields')
                successes+=1
                per_symbol[symbol][kind]={'sha256':hashlib.sha256(raw).hexdigest(),'scope':r['content_scope'],
                  'source':r['source_url'],'published_at':r['source_published_at'],
                  'original_unit':r['raw_numeric_unit'],'normalized_cny_yuan':r['normalized_cny_yuan'],
                  'field_count':len(r['standard_fields']),'primary_pdf_verified':False}
            except Exception as e:issues.append(f'{symbol}.{kind}:{type(e).__name__}:{e}')
    return {'strategy_id':'HOLDING_STRATEGY','version':'4.8.0','epoch':36,
      'period':manifest['report_period'],'samples_expected':len(A_SHARES)*len(STATEMENTS),
      'samples_parsed':successes,'manifest_integrity_pass':not issues,'issues':issues,
      'report_scope':'CORE_FIELDS_ONLY_NOT_FULL_REPORT','primary_pdf_verified_count':0,
      'source_type':'PUBLIC_WEB_MANUAL_TRANSCRIPTION','stocks':per_symbol}
if __name__=='__main__':
    root=Path(__file__).resolve().parent; r=audit(root)
    p=root/'EVIDENCE_AUDIT.json';p.write_text(json.dumps(r,ensure_ascii=False,indent=2))
    print(json.dumps({'samples_parsed':r['samples_parsed'],'issues':r['issues'], 'primary_pdf_verified_count':0, 'output':str(p)},ensure_ascii=False))
    raise SystemExit(0 if r['manifest_integrity_pass'] and r['samples_parsed']==r['samples_expected'] else 1)