import tempfile
import unittest
from pathlib import Path
from ops.public_hk_statement_fact_v2 import extract_hk_halfyear_cashflow

class HKStrictFactTests(unittest.TestCase):
    def test_interim_text_cashflow_units(self):
        import fitz
        with tempfile.TemporaryDirectory() as root:
            filename=Path(root)/"148_HK_test.pdf"
            pdf=fitz.open();page=pdf.new_page()
            rows=["Condensed Consolidated Statement of Cash Flow","Six months ended 30 June",
                  "2026         2025","HK$'000      HK$'000",
                  "Net cash from operating activities       2,473,724    605,969"]
            for i,row in enumerate(rows):
                page.insert_text((40,60+18*i),row,fontname="cour",fontsize=10)
            pdf.save(str(filename));pdf.close()
            out=extract_hk_halfyear_cashflow(filename,"148.HK")
            self.assertEqual(len(out),2)
            self.assertEqual(out[0]["value"],"2473724")
            self.assertEqual(out[0]["unit_multiplier"],"1000")
            self.assertEqual(out[0]["period_end"],"2026-06-30")
            self.assertEqual(out[1]["period_end"],"2025-06-30")
            self.assertEqual(out[0]["scope"],"CONSOLIDATED")
    def test_no_hk_scope_no_fact(self):
        import fitz
        with tempfile.TemporaryDirectory() as root:
            filename=Path(root)/"148_HK_test.pdf"
            pdf=fitz.open();page=pdf.new_page()
            page.insert_text((40,60),"Parent Company Cash Flow")
            page.insert_text((40,80),"Net cash from operating activities 2,473,724 605,969")
            pdf.save(str(filename));pdf.close()
            self.assertEqual(extract_hk_halfyear_cashflow(filename,"148.HK"),[])
if __name__=="__main__":unittest.main()
