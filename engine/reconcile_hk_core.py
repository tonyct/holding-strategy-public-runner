"""Validate twelve financial rows in four archived original HKEX interim reports.
Amounts are report-native thousands. This does not validate FX, all notes or trades.
"""
import argparse, hashlib, json, re, zipfile, os
from pathlib import Path
from datetime import datetime, timezone
import fitz

EXPECTED = {
 "148.HK": ("HKD", [(2,"Revenue","29,131,393"),(2,"Owners of the Company","2,711,413"),(8,"Net cash from operating activities","2,473,724")]),
 "2233.HK": ("RMB", [(29,"Revenue","4,526,885"),(29,"Owners of the Company","378,770"),(34,"NET CASH FROM OPERATING ACTIVITIES","702,234")]),
 "3933.HK": ("RMB", [(6,"Revenue","6,165,949"),(6,"Owners of the Company","347,644"),(10,"Net cash from operating activities","34,732")]),
 "9926.HK": ("RMB", [(71,"REVENUE","1,805,681"),(72,"Owners of the parent","(424,220)"),(77,"Net cash flows from/(used in) operating activities","290,277")])
}
FIELDS=("revenue","attributable_profit","operating_cash_flow")
def validate(archive):
 with zipfile.ZipFile(archive) as z:
  if z.testzip(): raise ValueError("ZIP_CORRUPT")
  receipt=json.loads(z.read("hk_origin/HKEX_RECEIPT.json"))
  report={"schema":"E36_HK_PRIMARY_CORE/v1","asof":datetime.now(timezone.utc).isoformat(),
          "source_run_id":int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,"period":"2026-06-30","checked":0,
          "fx_verified":False,"full_statement_verified":False,"notes_verified":False,"stocks":{}}
  for symbol,(currency,rows) in EXPECTED.items():
   matches=[f for f in receipt["symbols"][symbol]["files"] if "INTERIM REPORT" in f["title"].upper() and f.get("filename")]
   if len(matches)!=1: raise ValueError("PDF_SELECTION_AMBIGUOUS:"+symbol)
   record=matches[0]; raw=z.read("hk_origin/"+record["filename"])
   sha=hashlib.sha256(raw).hexdigest()
   if sha!=record["sha256"] or not record.get("identity_verified") or not record.get("year_2026_in_front_pages"):
    raise ValueError("PDF_INTEGRITY_OR_IDENTITY:"+symbol)
   output={"pdf":record["filename"],"sha256":sha,"currency":currency,"unit":"THOUSANDS","fields":{}}
   with fitz.open(stream=raw,filetype="pdf") as pdf:
    for field,(page,label,amount) in zip(FIELDS,rows):
     lines=pdf[page-1].get_text(sort=True).splitlines()
     hits=[line.strip() for line in lines if label.lower() in line.lower()
           and re.search(r"(?<![0-9,])"+re.escape(amount)+r"(?![0-9])",line)]
     if len(hits)!=1: raise ValueError("ROW_NOT_UNIQUE:"+symbol+":"+field)
     output["fields"][field]={"page":page,"row":hits[0],"amount_native":str(int(amount.replace(",","").replace("(","-").replace(")",""))*1000)}
     report["checked"]+=1
   report["stocks"][symbol]=output
  report["status"]="PRIMARY_CORE_12_OF_12" if report["checked"]==12 else "INCOMPLETE"
  return report

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--artifact",required=True);parser.add_argument("--output",required=True)
 args=parser.parse_args()
 try: result=validate(args.artifact)
 except Exception as exc: result={"status":"FAIL_CLOSED","error":str(exc),"production_ready":False}
 Path(args.output).parent.mkdir(parents=True,exist_ok=True)
 Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":result["status"],"checked":result.get("checked",0)}))
 raise SystemExit(0 if result["status"]=="PRIMARY_CORE_12_OF_12" else 1)
