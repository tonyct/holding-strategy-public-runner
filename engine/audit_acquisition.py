"""Report honest coverage for every active E36 research symbol across independent sources."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from universe import load_universe

def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}

def audit(universe_file, output_dir):
    universe = load_universe(universe_file)
    output_dir = Path(output_dir)
    acquired = read(output_dir / "ACQUISITION_RECEIPT.json")
    original = read(output_dir / "official_filings" / "OFFICIAL_PDF_FETCH_RECEIPT.json")
    announcements = read(output_dir / "announcements" / "ANNOUNCEMENT_RECEIPT.json")
    notes = read(output_dir / "notes" / "REPORT_NOTE_EXCERPTS.json")
    xueqiu = read(output_dir / "xueqiu" / "XUEQIU_SCAN_RECEIPT.json")
    hk = read(output_dir / "hk_official_filings" / "HK_FILING_RECEIPT.json")
    hk_financial = read(output_dir / "hk_financials" / "HK_FINANCIAL_RECEIPT.json")
    source_rows = {
        "financial": {r.get("symbol"): r for r in acquired.get("tickers", [])},
        "pdf": {r.get("symbol"): r for r in original.get("rows", [])},
        "announcements": {r.get("symbol"): r for r in announcements.get("rows", [])},
        "notes": {r.get("symbol"): r for r in notes.get("rows", [])},
        "xueqiu": {r.get("symbol"): r for r in xueqiu.get("symbols", [])},
        "hk_pdf": {r.get("symbol"): r for r in hk.get("rows", [])},
        "hk_financial": {r.get("symbol"): r for r in hk_financial.get("rows", [])},
    }
    hashes = {
        "financial": acquired.get("universe_sha256"),
        "announcements": announcements.get("universe_sha256"),
        "xueqiu": xueqiu.get("universe_sha256"),
    }
    result = []
    verified_raw_financial = 0
    downloaded_original = 0
    for symbol in universe["active"]:
        a_share = symbol in universe["a_shares"]
        statuses = {}
        for source, by_symbol in source_rows.items():
            r = by_symbol.get(symbol, {})
            statuses[source] = r.get("status", "MISSING")
            if source in hashes and hashes[source] != universe["universe_sha256"]:
                statuses[source] = "UNIVERSE_HASH_MISMATCH_OR_MISSING"
        if not a_share:
            statuses["financial"] = statuses["hk_financial"] if hk_financial.get("universe_sha256") == universe["universe_sha256"] else "HK_FINANCIAL_UNIVERSE_MISMATCH_OR_MISSING"
            statuses["pdf"] = statuses["hk_pdf"] if hk.get("universe_sha256") == universe["universe_sha256"] else "HK_SOURCE_UNIVERSE_MISMATCH_OR_MISSING"
            statuses["announcements"] = "HK_ANNOUNCEMENT_COLLECTOR_NOT_IMPLEMENTED"
            statuses["notes"] = "HK_REPORT_NOTE_EXTRACTION_NOT_IMPLEMENTED"
        by_symbol=source_rows["financial"]
        financial_ok = ((a_share and by_symbol.get(symbol, {}).get("retrieved_statements") == 3 and statuses["financial"] == "CORE_THREE_STATEMENTS_UNVERIFIED") or
                        (not a_share and statuses["financial"] == "RAW_THREE_STATEMENTS_FETCHED_UNVERIFIED"))
        # A-share acquisition receipt stores CORE_THREE_STATEMENTS_UNVERIFIED as the per-symbol status.
        if financial_ok: verified_raw_financial += 1
        if (statuses["pdf"] == "ORIGINAL_PDF_BYTES_DOWNLOADED_NOT_CONTENT_VERIFIED" or
            statuses["pdf"] == "HKEX_PDF_IDENTITY_PERIOD_VERIFIED_NOT_NOTES_AUDITED"):
            downloaded_original += 1
        result.append({"symbol": symbol, "market": "A" if a_share else "HK", "sources": statuses,
                       "three_statements_fetched": financial_ok,
                       "original_pdf_downloaded": statuses["pdf"] in ("ORIGINAL_PDF_BYTES_DOWNLOADED_NOT_CONTENT_VERIFIED", "HKEX_PDF_IDENTITY_PERIOD_VERIFIED_NOT_NOTES_AUDITED"),
                       "all_acquisition_verified": False})
    report = {
        "schema": "E36_ACQUISITION_COVERAGE/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "universe_sha256": universe["universe_sha256"],
        "active_count": len(result),
        "three_statements_fetched_count": verified_raw_financial,
        "original_pdf_downloaded_count": downloaded_original,
        "acquisition_complete": False,
        "research_complete": False,
        "rows": result,
    }
    target = output_dir / "ACQUISITION_COVERAGE.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--universe-file", default="config/research_universe.json")
    p.add_argument("--output", default="output")
    args = p.parse_args()
    r = audit(args.universe_file, args.output)
    print(json.dumps({"acquisition_complete": r["acquisition_complete"],
                      "active_count": r["active_count"],
                      "coverage_file": str(Path(args.output) / "ACQUISITION_COVERAGE.json")}))
