"""Conservative acquisition targets, never proof of an issuer's actual filing.

Use the collected report date/original announcement as the availability proof.
Explicit historical periods continue to work for replay and TTM construction.
"""
from datetime import date,datetime

def latest_due_period(as_of,market="A"):
    if isinstance(as_of,str):as_of=datetime.strptime(as_of,"%Y-%m-%d").date()
    y=as_of.year
    if market not in ("A","HK"):raise ValueError("UNKNOWN_FINANCIAL_MARKET")
    if market=="A" and as_of>=date(y,10,31):return f"{y}-09-30"
    if as_of>=date(y,8,31):return f"{y}-06-30"
    if as_of>=date(y,4,30):return f"{y}-03-31" if market=="A" else f"{y-1}-12-31"
    return f"{y-1}-09-30" if market=="A" else f"{y-1}-06-30"

def resolve_period(value,market="A",as_of=None):
    if value=="auto":return latest_due_period(as_of or date.today(),market)
    return datetime.strptime(value,"%Y-%m-%d").date().isoformat()
