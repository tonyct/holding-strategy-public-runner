import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ops.public_delivery_shards import build


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PublicDeliveryShardTests(unittest.TestCase):
    def fixture(self, d):
        r = Path(d) / "source"
        r.mkdir()
        payloads = {
            "originals/a/abc.pdf": b"%PDF-1.4\none\n%%EOF\n",
            "originals/ttm/large.pdf": b"%PDF-1.4\n" + b"t" * 120 + b"\n%%EOF\n",
            "compute/facts.json": b'{"privacy_class":"PUBLIC_MARKET_DATA_ONLY"}',
            "quotes/QUOTE_RECEIPT.json": b'{"ok":true}',
        }
        for name, data in list(payloads.items()):
            ext = Path(name).suffix
            payloads["evidence/raw/sha256/" + sha(data)[:2] + "/" + sha(data) + ext] = data
        for name, data in payloads.items():
            p = r / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        bundle = {
            "schema": "E36_PUBLIC_RESEARCH_BUNDLE/v1",
            "privacy_class": "PUBLIC_MARKET_DATA_ONLY",
            "contains_account_state": False,
            "contains_portfolio_decision": False,
            "source_run_id": "123", "source_run_attempt": "1",
            "source_commit_sha": "a" * 40,
            "files": [{"path": n, "sha256": sha(b), "size": len(b)}
                      for n, b in sorted(payloads.items())],
        }
        (r / "PUBLIC_RESEARCH_BUNDLE.json").write_text(json.dumps(bundle))
        u = Path(d) / "universe.json"
        u.write_text(json.dumps({
            "source": "PUBLIC_RESEARCH_COVERAGE_UNIVERSE_NOT_ACCOUNT_HOLDINGS",
            "strategy_id": "PUBLIC_COMPANY_RESEARCH", "stocks": []}))
        return r, u, bundle

    def test_duplicate_original_bytes_not_repacked(self):
        with tempfile.TemporaryDirectory() as d:
            r, u, manifest = self.fixture(d)
            out = Path(d) / "delivery"
            p = build(r, u, out, run_id="123", attempt="1",
                      commit_sha="a" * 40, shard_count=2)
            self.assertEqual(p["manifest_file_count"], 8)
            self.assertEqual(p["unique_content_count"], 4)
            self.assertEqual(p["duplicate_alias_count"], 4)
            self.assertEqual(sum(p["pdf_shard_bytes"]), 155)
            self.assertEqual(len(p["entries"]), 4)
            self.assertTrue((out / "metadata" / "PUBLIC_RESEARCH_BUNDLE.json").exists())
            self.assertTrue((out / "metadata" / "PUBLIC_DELIVERY_INDEX.json").exists())
            for entry in p["entries"]:
                self.assertFalse(entry["canonical_path"].startswith("evidence/raw"))
                data = (out / entry["shard"] / entry["canonical_path"]).read_bytes()
                self.assertEqual(sha(data), entry["sha256"])

    def test_mutated_bytes_hard_fail(self):
        with tempfile.TemporaryDirectory() as d:
            r, u, _ = self.fixture(d)
            (r / "originals/a/abc.pdf").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "DELIVERY_SOURCE_BYTES_INVALID"):
                build(r, u, Path(d) / "delivery", run_id="123",
                      attempt="1", commit_sha="a" * 40, shard_count=2)

    def test_privacy_and_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r, u, _ = self.fixture(d)
            j = json.loads((r / "PUBLIC_RESEARCH_BUNDLE.json").read_text())
            j["contains_account_state"] = True
            (r / "PUBLIC_RESEARCH_BUNDLE.json").write_text(json.dumps(j))
            with self.assertRaisesRegex(ValueError, "PRIVACY_INVALID"):
                build(r, u, Path(d) / "delivery", run_id="123",
                      attempt="1", commit_sha="a" * 40, shard_count=2)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r, u, _ = self.fixture(d)
            j = json.loads((r / "PUBLIC_RESEARCH_BUNDLE.json").read_text())
            j["files"].append({"path": "../outside", "sha256": "f" * 64, "size": 0})
            (r / "PUBLIC_RESEARCH_BUNDLE.json").write_text(json.dumps(j))
            with self.assertRaisesRegex(ValueError, "DELIVERY_PATH_INVALID"):
                build(r, u, Path(d) / "delivery", run_id="123",
                      attempt="1", commit_sha="a" * 40, shard_count=2)


if __name__ == "__main__":
    unittest.main()
