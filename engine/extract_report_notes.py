"""Extract reviewable note evidence from downloaded original reports, not investment conclusions."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

TOPICS = {
    "impairment": ("资产减值", "信用减值", "商誉减值", "存货跌价"),
    "related_party": ("关联交易", "关联方交易", "关联方及关联交易"),
    "receivables": ("应收账款", "其他应收款"),
    "contingencies": ("或有事项", "未决诉讼", "担保事项"),
    "going_concern": ("持续经营", "流动性风险"),
    "accounting_changes": ("会计政策变更", "会计估计变更"),
    "cashflow": ("经营活动产生的现金流量净额", "现金流量补充资料"),
}
def extract(receipt, out):
    import fitz
    manifest = json.loads(Path(receipt).read_text(encoding="utf-8"))
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in manifest.get("rows", []):
        row = {"symbol": item.get("symbol"), "status": "NOT_EXTRACTED",
               "notes_researched": False, "topics": {}, "source_pdf_sha256": item.get("sha256")}
        try:
            if item.get("status") != "ORIGINAL_PDF_BYTES_DOWNLOADED_NOT_CONTENT_VERIFIED":
                raise ValueError("ORIGINAL_PDF_NOT_AVAILABLE")
            path = Path(receipt).parent / item["filename"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("PDF_HASH_MISMATCH")
            with fitz.open(str(path)) as doc:
                if doc.needs_pass:
                    raise ValueError("ENCRYPTED_REPORT")
                hits_by_topic = {key: [] for key in TOPICS}
                for idx, page in enumerate(doc):
                    if all(len(hits) >= 8 for hits in hits_by_topic.values()):
                        break
                    text = re.sub(r"\s+", " ", page.get_text(sort=True))
                    for key, terms in TOPICS.items():
                        hits = hits_by_topic[key]
                        if len(hits) >= 8:
                            continue
                        for term in terms:
                            pos = text.find(term)
                            if pos >= 0:
                                hits.append({"page": idx + 1, "term": term,
                                             "excerpt": text[max(0, pos - 100):pos + 280]})
                                break
                row["topics"] = {key: {"hits": hits, "match_count_capped": len(hits)}
                                 for key, hits in hits_by_topic.items()}
            row["status"] = "EXCERPTS_EXTRACTED_RESEARCH_REQUIRED"
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            row["status"] = "EXTRACTION_FAILED"
            row["error"] = type(exc).__name__ + ":" + str(exc)[:160]
        rows.append(row)
    result = {"schema": "E36_REPORT_NOTE_EXCERPTS/v1",
              "generated_utc": datetime.now(timezone.utc).isoformat(),
              "rows": rows, "notes_researched": False, "original_pdf_content_audited": False}
    (target / "REPORT_NOTE_EXCERPTS.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if rows and all(r["status"] == "EXCERPTS_EXTRACTED_RESEARCH_REQUIRED" for r in rows) else 1
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pdf-receipt", required=True)
    p.add_argument("--output", default="output/notes")
    args = p.parse_args()
    raise SystemExit(extract(args.pdf_receipt, args.output))
