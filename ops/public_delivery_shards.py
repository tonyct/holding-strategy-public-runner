"""Build source-verified, de-duplicated and bounded Public delivery shards.

This is a transport transformation only: the authoritative Public manifest,
research universe, original PDF bytes, and evidence identities never change.
The legacy full artifact remains the backward-compatible delivery until the
Private consumer is independently validated.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

SCHEMA = "E36_PUBLIC_SHARDED_DELIVERY/v1"
BUNDLE = "PUBLIC_RESEARCH_BUNDLE.json"


def digest_file(path):
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return h.hexdigest(), size


def safe_rel(name):
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("DELIVERY_PATH_INVALID")
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "." in p.parts or p.as_posix() != name:
        raise ValueError("DELIVERY_PATH_INVALID:" + name)
    return p


def within(root, name):
    parts = safe_rel(name)
    root = Path(root).resolve()
    candidate = root.joinpath(*parts.parts)
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("DELIVERY_PATH_ESCAPE:" + name)
    if candidate.is_symlink():
        raise ValueError("DELIVERY_SYMLINK_FORBIDDEN:" + name)
    return candidate


def build(source_root, universe_file, transport_root, *, run_id, attempt,
          commit_sha, shard_count=8):
    root = Path(source_root).resolve()
    dest = Path(transport_root).resolve()
    if dest == root or dest.is_relative_to(root):
        raise ValueError("DELIVERY_DEST_INSIDE_SOURCE")
    if not isinstance(shard_count, int) or not 2 <= shard_count <= 32:
        raise ValueError("DELIVERY_SHARD_COUNT_INVALID")
    bundle_path = within(root, BUNDLE)
    bundle_raw = bundle_path.read_bytes()
    bundle = json.loads(bundle_raw)
    if (bundle.get("schema") != "E36_PUBLIC_RESEARCH_BUNDLE/v1"
            or bundle.get("privacy_class") != "PUBLIC_MARKET_DATA_ONLY"
            or bundle.get("contains_account_state") is not False
            or bundle.get("contains_portfolio_decision") is not False
            or str(bundle.get("source_run_id")) != str(run_id)
            or str(bundle.get("source_run_attempt")) != str(attempt)
            or bundle.get("source_commit_sha") != commit_sha
            or not isinstance(bundle.get("files"), list)):
        raise ValueError("DELIVERY_BUNDLE_IDENTITY_OR_PRIVACY_INVALID")
    raw_universe = Path(universe_file).read_bytes()
    universe = json.loads(raw_universe)
    if (universe.get("source") != "PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS"
            or universe.get("strategy_id") != "PUBLIC_COMPANY_RESEARCH"):
        raise ValueError("DELIVERY_UNIVERSE_SCOPE_INVALID")

    by_sha = {}
    paths = set()
    for item in bundle["files"]:
        name, sha, size = item.get("path"), item.get("sha256"), item.get("size")
        safe_rel(name)
        if (name in paths or not isinstance(sha, str) or len(sha) != 64
                or not isinstance(size, int) or size < 0):
            raise ValueError("DELIVERY_MANIFEST_ROW_INVALID")
        paths.add(name)
        file_path = within(root, name)
        actual_sha, actual_size = digest_file(file_path)
        if (actual_sha, actual_size) != (sha, size):
            raise ValueError("DELIVERY_SOURCE_BYTES_INVALID:" + name)
        record = by_sha.setdefault(sha, {"sha256": sha, "size": size, "aliases": []})
        if record["size"] != size:
            raise ValueError("DELIVERY_HASH_SIZE_CONFLICT")
        record["aliases"].append(name)

    entries = []
    for sha, record in by_sha.items():
        # Never pick a registry duplicate as the canonical source when an
        # issuer-facing logical path is available.
        canonical = sorted(record["aliases"], key=lambda p: (
            p.startswith("evidence/raw/sha256/"), p))[0]
        record["canonical_path"] = canonical
        record["aliases"].sort()
        record["is_pdf"] = canonical.lower().endswith(".pdf")
        entries.append(record)

    sizes = [0] * shard_count
    for record in sorted((x for x in entries if x["is_pdf"]),
                         key=lambda x: (-x["size"], x["sha256"])):
        bucket = min(range(shard_count), key=lambda i: (sizes[i], i))
        record["shard"] = "pdf-%02d" % bucket
        sizes[bucket] += record["size"]
    for record in entries:
        if not record["is_pdf"]:
            record["shard"] = "metadata"
        record.pop("is_pdf")

    if dest.exists() and any(dest.iterdir()):
        raise ValueError("DELIVERY_DEST_NOT_EMPTY")
    dest.mkdir(parents=True, exist_ok=True)
    for record in sorted(entries, key=lambda x: x["canonical_path"]):
        canonical = record["canonical_path"]
        target = dest / record["shard"] / canonical
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(within(root, canonical), target)
        if digest_file(target) != (record["sha256"], record["size"]):
            raise ValueError("DELIVERY_COPY_VERIFY_FAILED:" + canonical)

    meta = dest / "metadata"
    (meta / "config").mkdir(exist_ok=True)
    (meta / BUNDLE).write_bytes(bundle_raw)
    (meta / "config" / "research_universe.json").write_bytes(raw_universe)
    index = {
        "schema": SCHEMA,
        "privacy_class": "PUBLIC_MARKET_DATA_ONLY",
        "source_run_id": str(run_id), "source_run_attempt": str(attempt),
        "source_commit_sha": commit_sha,
        "manifest_sha256": hashlib.sha256(bundle_raw).hexdigest(),
        "public_universe_sha256": hashlib.sha256(raw_universe).hexdigest(),
        "manifest_file_count": len(paths),
        "unique_content_count": len(entries),
        "duplicate_alias_count": len(paths) - len(entries),
        "unique_payload_bytes": sum(x["size"] for x in entries),
        "logical_manifest_bytes": sum(x["size"] for x in bundle["files"]),
        "pdf_shard_count": shard_count,
        "pdf_shard_bytes": sizes,
        "artifact_name_template": "public-delivery-{shard}-" + str(run_id) + "-" + str(attempt),
        "entries": sorted(entries, key=lambda x: x["canonical_path"]),
        "transport_is_not_semantic_approval": True,
        "trade_execution_authorized": False,
    }
    (meta / "PUBLIC_DELIVERY_INDEX.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--universe", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--attempt", required=True)
    ap.add_argument("--commit-sha", required=True)
    ap.add_argument("--shards", type=int, default=8)
    args = ap.parse_args()
    index = build(args.root, args.universe, args.output,
                  run_id=args.run_id, attempt=args.attempt,
                  commit_sha=args.commit_sha, shard_count=args.shards)
    print(json.dumps({k: index[k] for k in (
        "manifest_file_count", "unique_content_count",
        "duplicate_alias_count", "unique_payload_bytes", "pdf_shard_bytes")}))


if __name__ == "__main__":
    main()
