import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from collect_community_direct import build_post_record, normalize_board_code

class CommunityBoardIdentityTests(unittest.TestCase):
    def test_hk_board_normalization(self):
        self.assertEqual(normalize_board_code("HK00148"), "hk00148")
        self.assertEqual(normalize_board_code("148.HK"), "hk00148")

    def test_post_url_uses_source_board_and_detects_cross_board(self):
        row = build_post_record("603993.SH", "603993", {
            "post_id": "1769136700",
            "post_title": "AI算力金属涨价",
            "stockbar_code": "601899",
            "stockbar_name": "紫金矿业吧",
            "post_comment_count": 38,
            "post_click_count": 8322,
        })
        self.assertEqual(row["source_board_code"], "601899")
        self.assertEqual(row["url"], "https://guba.eastmoney.com/news,601899,1769136700.html")
        self.assertFalse(row["target_board_match"])
        self.assertEqual(row["discovery_relation"], "CROSS_BOARD")
        self.assertFalse(row["qualified_for_target_specific_shadow_verification"])
        self.assertFalse(row["raw_post_verified"])

    def test_exact_hk_board_is_target_specific_but_body_stays_unverified(self):
        row = build_post_record("148.HK", "hk00148", {
            "post_id": "2000000000",
            "post_title": "PCB概念上涨",
            "stockbar_code": "hk00148",
            "stockbar_name": "建滔集团吧",
        })
        self.assertTrue(row["target_board_match"])
        self.assertTrue(row["qualified_for_target_specific_shadow_verification"])
        self.assertEqual(row["post_content_status"], "TITLE_ONLY_BODY_NOT_FETCHED")
        self.assertFalse(row["raw_post_verified"])

    def test_missing_source_board_is_never_target_specific(self):
        row = build_post_record("600499.SH", "600499", {
            "post_id": "1",
            "post_title": "负极扩产",
        })
        self.assertIsNone(row["url"])
        self.assertEqual(row["discovery_relation"], "BOARD_UNKNOWN")
        self.assertFalse(row["qualified_for_target_specific_shadow_verification"])

if __name__ == "__main__":
    unittest.main()
