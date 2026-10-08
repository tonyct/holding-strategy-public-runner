"""One-time exact-SHA public issuer historical PDF backfill.

No Private endpoints, no portfolio fields or investment computation. The
manifest is PUBLIC-only archival source metadata. Cached binaries are reused
when issuer URL, period, length and SHA stay identical.
"""
import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

HEX = re.compile(r"^[a-f0-9]{64}$")
STOCK = re.compile(r"^(?:\d{6}\.(?:SH|SZ)|\d{1,5}\.HK)$")
PERIODS = {"2025-06-30", "2025-12-31"}
MAX_PDF_BYTES = 65 * 1024 * 1024


def allow_official_url(url, ticker):
    p = urlparse(url)
    if p.scheme != "https" or p.username or p.password or p.query or p.fragment:
        return False
    if ticker.endswith(".HK"):
        return p.hostname == "www1.hkexnews.hk" and bool(re.fullmatch(
            r"/listedco/listconews/sehk/20\d\d/\d{4}/\d+\.pdf", p.path, re.I))
    return p.hostname == "static.cninfo.com.cn" and bool(re.fullmatch(
        r"/finalpage/20\d\d-\d\d-\d\d/\d{10}\.PDF", p.path, re.I))


def load_config(path):
    data = json.loads(Path(path).read_bytes())
    if (data.get("schema") != "PUBLIC_HISTORICAL_SOURCE_BACKFILL/v1"
            or data.get("privacy_class") != "PUBLIC_MARKET_DATA_ONLY"
            or data.get("contains_account_state") is not False
            or data.get("contains_portfolio_decision") is not False
            or data.get("trade_logic") is not False
            or not isinstance(data.get("files"), list)
            or not data["files"]
            or len(data["files"]) != data.get("expected_count")):
        raise ValueError("PUBLIC_TTM_SOURCE_CONFIG_INVALID")
    seen = set()
    for row in data["files"]:
        keys = {"ticker", "period_end", "official_url",
                "expected_sha256", "expected_bytes"}
        if (set(row) != keys or not isinstance(row["ticker"], str)
                or not STOCK.fullmatch(row["ticker"])
                or row["period_end"] not in PERIODS
                or not isinstance(row["expected_sha256"], str)
                or not HEX.fullmatch(row["expected_sha256"])
                or not isinstance(row["expected_bytes"], int)
                or not 0 < row["expected_bytes"] <= MAX_PDF_BYTES
                or not allow_official_url(row["official_url"], row["ticker"])):
            raise ValueError("PUBLIC_TTM_OFFICIAL_SOURCE_NOT_VERIFIABLE")
        key = (row["ticker"], row["period_end"])
        if key in seen:
            raise ValueError("PUBLIC_TTM_DUPLICATE_ISSUER_PERIOD")
        seen.add(key)
    return data


def valid_bytes(raw, row):
    return (len(raw) == row["expected_bytes"]
            and raw.startswith(b"%PDF-")
            and b"%%EOF" in raw[-8192:]
            and hashlib.sha256(raw).hexdigest() == row["expected_sha256"])


def fetch_one(row, output_dir, cache_dir, session):
    expected = row["expected_sha256"]
    dest = Path(output_dir) / (expected + ".pdf")
    candidates = [dest]
    if cache_dir:
        candidates.append(Path(cache_dir) / dest.name)
    for path in candidates:
        if path.is_file():
            data = path.read_bytes()
            if valid_bytes(data, row):
                if path != dest:
                    dest.write_bytes(data)
                return {**row, "filename": dest.name,
                        "status": "REUSED_EXACT_SHA_PUBLIC_OFFICIAL_CACHE",
                        "verified": True}
    try:
        r = session.get(row["official_url"],
                        timeout=(12, 65), stream=True, allow_redirects=False,
                        headers={"User-Agent": "PublicCompanyResearch/1.0",
                                 "Referer": ("https://www1.hkexnews.hk/"
                                             if row["ticker"].endswith(".HK")
                                             else "https://www.cninfo.com.cn/")})
        if r.status_code != 200:
            raise ValueError("OFFICIAL_HTTP_" + str(r.status_code))
        if r.headers.get("Content-Type", "").lower().startswith("text/html"):
            raise ValueError("OFFICIAL_HTML_NOT_PDF")
        contents = bytearray()
        for chunk in r.iter_content(65536):
            contents.extend(chunk)
            if len(contents) > MAX_PDF_BYTES:
                raise ValueError("OFFICIAL_PDF_TOO_LARGE")
        raw = bytes(contents)
        if not valid_bytes(raw, row):
            raise ValueError("OFFICIAL_ORIGINAL_BYTES_DO_NOT_MATCH_HISTORICAL_PIN")
        dest.write_bytes(raw)
        return {**row, "filename": dest.name, "status": "FETCHED_EXACT_SHA_OFFICIAL",
                "verified": True}
    except Exception as exc:
        # No substitution with a similar issuer report, newer PDF or inferred
        # period. A missing official original is never an approved source.
        return {**row, "filename": None, "status": "EXACT_SOURCE_UNAVAILABLE",
                "verified": False, "error_code": type(exc).__name__ + ":" +
                str(exc)[:110]}


def collect(config, output_dir, cache_dir, session):
    data = load_config(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = [fetch_one(row, out, cache_dir, session) for row in data["files"]]
    by_ticker = {}
    for rec in results:
        by_ticker.setdefault(rec["ticker"], {"files": []})["files"].append(rec)
    count = sum(r["verified"] for r in results)
    return {"schema": "PUBLIC_TTM_HISTORICAL_PINNED_ORIGINALS/v1",
            "privacy_class": "PUBLIC_MARKET_DATA_ONLY",
            "purpose": "HISTORICAL_SOURCE_RETRIEVAL_NOT_ECONOMIC_RESEARCH",
            "requested": len(results), "verified_count": count,
            "pending_count": len(results) - count, "symbols": by_ticker,
            "semantic_fact_verified": False, "trade_logic": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--cache-dir", default="")
    a = p.parse_args()
    import requests
    with requests.Session() as session:
        receipt = collect(a.config, a.output, a.cache_dir, session)
    dest = Path(a.output) / "PUBLIC_TTM_ORIGINALS_RECEIPT.json"
    dest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verified_count": receipt["verified_count"],
                      "pending_count": receipt["pending_count"],
                      "public_data_only": True}))
    # Preserve legitimate Partial acquisition; the receipt distinguishes
    # verified files from missing ones without making up financial facts.


if __name__ == "__main__":
    main()
