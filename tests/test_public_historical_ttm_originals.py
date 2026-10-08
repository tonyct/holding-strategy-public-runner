"""Offline regressions for Public exact-SHA historical PDF backfill."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from ops.public_historical_ttm_originals import collect, load_config, allow_official_url

PDF = b"%PDF-1.7\nsynthetic official-issuer test fixture\n%%EOF\n"
SHA = hashlib.sha256(PDF).hexdigest()

class FakeResponse:
    status_code = 200
    headers = {"Content-Type":"application/pdf"}
    def iter_content(self, n):
        yield PDF

class FakeSession:
    def __init__(self):
        self.calls = 0
    def get(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse()

def fixture(path, *, valid_sha=True):
    config = {
        "schema":"PUBLIC_HISTORICAL_SOURCE_BACKFILL/v1",
        "privacy_class":"PUBLIC_MARKET_DATA_ONLY",
        "contains_account_state":False,
        "contains_portfolio_decision":False,
        "trade_logic":False,
        "expected_count":1,
        "files":[{
            "ticker":"600941.SH",
            "period_end":"2025-06-30",
            "official_url":"https://static.cninfo.com.cn/finalpage/2025-08-08/1224425060.PDF",
            "expected_sha256":SHA if valid_sha else "0"*64,
            "expected_bytes":len(PDF)}]
    }
    Path(path).write_text(json.dumps(config))
    return config

class PublicHistoricOriginalTests(unittest.TestCase):
    def test_fetch_verified_source_and_cache_reuse_without_network(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/"config.json"
            fixture(src)
            stage=Path(root)/"stage"
            sess=FakeSession()
            a=collect(src,stage,None,sess)
            self.assertEqual(a["verified_count"],1)
            self.assertEqual(a["pending_count"],0)
            self.assertEqual(sess.calls,1)
            self.assertEqual((stage/(SHA+".pdf")).read_bytes(),PDF)
            stage2=Path(root)/"next"
            b=collect(src,stage2,stage,sess)
            self.assertEqual(b["verified_count"],1)
            self.assertEqual(sess.calls,1)
            self.assertEqual(b["symbols"]["600941.SH"]["files"][0]["status"],
                             "REUSED_EXACT_SHA_PUBLIC_OFFICIAL_CACHE")

    def test_exact_persistent_cache_is_written_and_used_on_next_run(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/"config.json"
            fixture(src)
            cache=Path(root)/"cache"
            session=FakeSession()
            first=collect(src,Path(root)/"stage1",cache,session)
            self.assertEqual(first["verified_count"],1)
            self.assertEqual((cache/(SHA+".pdf")).read_bytes(),PDF)
            second=collect(src,Path(root)/"stage2",cache,session)
            self.assertEqual(second["verified_count"],1)
            self.assertEqual(session.calls,1)
            self.assertEqual(second["symbols"]["600941.SH"]["files"][0]["status"],
                             "REUSED_EXACT_SHA_PUBLIC_OFFICIAL_CACHE")

    def test_changed_historical_digest_is_not_forgiven(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/"config.json"
            fixture(src,valid_sha=False)
            stage=Path(root)/"stage"
            s=FakeSession()
            r=collect(src,stage,None,s)
            self.assertEqual(r["verified_count"],0)
            self.assertEqual(r["pending_count"],1)
            self.assertEqual(r["symbols"]["600941.SH"]["files"][0]["status"],
                             "EXACT_SOURCE_UNAVAILABLE")
            self.assertFalse((stage/("0"*64+".pdf")).exists())

    def test_only_public_official_urls_and_no_account_fields(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/"config.json"
            x=fixture(src)
            for url in ["http://static.cninfo.com.cn/finalpage/2025-08-08/1224425060.PDF",
                        "https://evil.example/report.pdf",
                        "https://static.cninfo.com.cn/other.pdf",
                        "https://static.cninfo.com.cn/finalpage/2025-08-08/1224425060.PDF?token=x"]:
                self.assertFalse(allow_official_url(url,"600941.SH"))
                x["files"][0]["official_url"]=url
                src.write_text(json.dumps(x))
                with self.assertRaisesRegex(ValueError,"SOURCE_NOT_VERIFIABLE"):
                    load_config(src)
            x=fixture(src)
            x["files"][0]["account_holdings"]={"private":True}
            src.write_text(json.dumps(x))
            with self.assertRaisesRegex(ValueError,"SOURCE_NOT_VERIFIABLE"):
                load_config(src)

    def test_actual_pinned_recovery_config_has_no_private_fields(self):
        p=Path("config/public_historical_original_backfill_20261008.json")
        cfg=load_config(p)
        self.assertEqual(cfg["expected_count"],22)
        self.assertEqual(len(set((x["ticker"],x["period_end"]) for x in cfg["files"])),22)
        self.assertEqual(len(set(x["ticker"] for x in cfg["files"])),11)
        self.assertFalse(cfg["contains_account_state"])
        self.assertFalse(cfg["contains_portfolio_decision"])

if __name__=="__main__":
    unittest.main()
