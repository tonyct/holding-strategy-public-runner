"""Regression: Public SHA archive aliases never create extra physical payloads."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.public_evidence_registry import main


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PublicCASPhysicalDedupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "output"
        (self.root / "originals").mkdir(parents=True)
        self.reg = self.root / "state/PUBLIC_DYNAMIC_EVIDENCE_REGISTRY.json"
        self.receipt = self.root / "state/PUBLIC_EVIDENCE_REGISTRY_UPDATE.json"

    def run_registry(self):
        argv = ["registry", "--registry", str(self.reg), "--source-root",
                str(self.root), "--store-root",
                str(self.root / "evidence/raw/sha256"), "--run-id", "123",
                "--output", str(self.receipt)]
        with patch("sys.argv", argv):
            main()

    def test_exact_sha_pdf_and_json_have_one_inode_each(self):
        samples = {"issuer.pdf": b"%PDF-1.4\nreal bytes\n%%EOF\n",
                   "filing.json": b'{"source":"issuer"}'}
        for name, raw in samples.items():
            (self.root / "originals" / name).write_bytes(raw)
        self.run_registry()
        for name, raw in samples.items():
            src = self.root / "originals" / name
            dest = self.root / "evidence/raw/sha256" / sha(raw)[:2] / (
                sha(raw) + src.suffix)
            self.assertEqual(dest.read_bytes(), raw)
            self.assertTrue(src.samefile(dest))
            self.assertEqual(src.stat().st_ino, dest.stat().st_ino)
            self.assertGreaterEqual(src.stat().st_nlink, 2)
        reg = json.loads(self.reg.read_bytes())
        self.assertEqual(reg["object_count"], 2)
        self.assertEqual(len(reg["identities"]), 2)
        self.run_registry()
        self.assertEqual(json.loads(self.reg.read_bytes())["object_count"], 2)

    def test_separate_existing_same_sha_is_refused_not_deleted(self):
        raw = b"%PDF-1.4\nnot mutable"
        src = self.root / "originals/a.pdf"
        src.write_bytes(raw)
        dest = self.root / "evidence/raw/sha256" / sha(raw)[:2] / (
            sha(raw) + ".pdf")
        dest.parent.mkdir(parents=True)
        dest.write_bytes(raw)
        self.assertFalse(src.samefile(dest))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PHYSICAL_COPY"):
            self.run_registry()
        self.assertEqual(src.read_bytes(), raw)
        self.assertEqual(dest.read_bytes(), raw)

    def test_existing_wrong_sha_fails_closed_without_overwrite(self):
        raw = b"%PDF-1.4\nsource"
        src = self.root / "originals/a.pdf"
        src.write_bytes(raw)
        dest = self.root / "evidence/raw/sha256" / sha(raw)[:2] / (
            sha(raw) + ".pdf")
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"unrelated existing content")
        with self.assertRaisesRegex(ValueError, "EXISTING_SHA_CONFLICT"):
            self.run_registry()
        self.assertEqual(dest.read_bytes(), b"unrelated existing content")

    def test_hardlink_unavailable_never_falls_back_to_copy(self):
        raw = b"%PDF-1.4\noriginal"
        (self.root / "originals/a.pdf").write_bytes(raw)
        with patch("ops.public_evidence_registry.os.link",
                   side_effect=OSError("unsupported")):
            with self.assertRaisesRegex(ValueError, "HARDLINK_REQUIRED"):
                self.run_registry()
        dest = self.root / "evidence/raw/sha256" / sha(raw)[:2] / (
            sha(raw) + ".pdf")
        self.assertFalse(dest.exists())

    def test_source_symlink_is_not_archived(self):
        raw = b"%PDF-1.4\nno linked source"
        original = self.root / "originals/a.pdf"
        original.write_bytes(raw)
        (self.root / "originals/b.pdf").symlink_to(original)
        with self.assertRaisesRegex(ValueError, "SYMLINK_FORBIDDEN"):
            self.run_registry()


if __name__ == "__main__":
    unittest.main()
