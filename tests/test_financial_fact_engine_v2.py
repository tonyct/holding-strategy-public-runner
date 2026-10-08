"""Offline safety and arithmetic regression for public fact engine."""
import unittest
from engine.financial_fact_engine_v2 import fact,ttm,ratio,delta,run
SHA="a"*64
def f(v, start="2025-01-01",end="2025-12-31",period="FY",field="operating_cash_flow",scope="CONSOLIDATED",source_page=1):
    return fact({"symbol":"600795.SH","field":field,"value":v,"currency":"CNY","period_start":start,"period_end":end,"period_type":period,"scope":scope,"source":{"document_sha256":SHA,"page":source_page}})
class FactsTest(unittest.TestCase):
    def test_provenance(self):
        with self.assertRaises(ValueError):fact({"symbol":"600795.SH","field":"revenue","value":"1","currency":"CNY","period_type":"FY","period_start":"2025-01-01","period_end":"2025-12-31","scope":"CONSOLIDATED","source":{}})
    def test_decimal_and_units(self):
        r=f("123.45");self.assertEqual(r["value"],"123.45")
    def test_ttm(self):
        a=f("100");b=f("60","2026-01-01","2026-06-30","H1_YTD");c=f("40","2025-01-01","2025-06-30","H1_YTD")
        d=ttm(a,b,c);self.assertEqual(d["value"],"120");self.assertEqual(d["period_start"],"2025-07-01")
    def test_ttm_start_guard(self):
        a=f("100");b=f("60","2026-02-01","2026-06-30","H1_YTD");c=f("40","2025-01-01","2025-06-30","H1_YTD")
        with self.assertRaises(ValueError):ttm(a,b,c)
    def test_scope_guard(self):
        a=f("100");b=f("60","2026-01-01","2026-06-30","H1_YTD",scope="PARENT");c=f("40","2025-01-01","2025-06-30","H1_YTD")
        with self.assertRaises(ValueError):ttm(a,b,c)
    def test_zero_denominator(self):
        with self.assertRaises(ValueError):ratio(f("20"),f("0"),"ratio")
    def test_delta(self):
        a=f("100");b=f("110")
        self.assertEqual(delta([a],[b])["changes"][0]["status"],"CHANGED")
    def test_conflicts(self):
        self.assertEqual(delta([],[f("100"),f("110")])["changes"][0]["status"],"CONFLICTED")
    def test_no_auto_verification(self):
        r=run([{"symbol":"600795.SH","field":"revenue","value":"5","currency":"CNY","period_start":"2025-01-01","period_end":"2025-12-31","period_type":"FY","scope":"CONSOLIDATED","source":{"document_sha256":SHA,"page":1}}])
        self.assertEqual(r["store"]["facts"][0]["verification_state"],"UNVERIFIED")
        self.assertTrue(r["compact"]["no_valuation"])
if __name__=="__main__":unittest.main()
