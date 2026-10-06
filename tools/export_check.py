#!/usr/bin/env python3
from pathlib import Path
import re, sys

ROOT=Path(sys.argv[1] if len(sys.argv)>1 else ".")
PROHIBITED=[
    r"actual_held", r"account_state", r"portfolio_decision", r"tracking_only",
    r"position_size", r"cost_basis", r"cash_nav", r"drive_bootstrap_id",
    r"user_screenshot", r"reduce_review", r"exit_review", r"XUEQIU_COOKIE",
]
DENY_PREFIXES=("runtime/","receipts/","research/main/","research/policies/","research/audits/","evidence/")
errors=[]
for p in ROOT.rglob("*"):
    if not p.is_file() or ".git" in p.parts:
        continue
    rel=p.relative_to(ROOT).as_posix()
    if rel.startswith(DENY_PREFIXES):
        errors.append(f"DENYLIST_PATH {rel}")
        continue
    if p.stat().st_size > 5_000_000:
        continue
    try:
        text=p.read_text(errors="ignore")
    except OSError:
        continue
    for pat in PROHIBITED:
        if re.search(pat,text,re.I):
            errors.append(f"PROHIBITED_TEXT {pat} {rel}")
if errors:
    print("\n".join(errors))
    raise SystemExit(1)
print("PUBLIC_EXPORT_SAFETY_PASS")
