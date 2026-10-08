import unittest
from ops.public_fact_pipeline_v2 import parse_number, extract, report_files, build
import tempfile
import json
from pathlib import Path
class TableCandidateTests(unittest.TestCase):
    def test_numeric_cells(self):
        self.assertEqual(parse_number("(1,234.50)"),"-1234.50")
        self.assertEqual(parse_number("−2,100"),"-2100")
    def test_ambiguous_cells(self):
        for x in ("2026年","10%","--","1 2 3",""):self.assertIsNone(parse_number(x))
    def test_official_report_filter(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/"a"
            out.mkdir()
            data={"symbols":{"600795.SH":{"files":[
                {"status":"FETCHED_OFFICIAL_ORIGINAL","title":"国电电力2026年半年度报告","filename":"report.pdf"},
                {"status":"FETCHED_OFFICIAL_ORIGINAL","title":"董事会决议","filename":"other.pdf"}]}}}
            (out/"A_ORIGINALS_RECEIPT.json").write_text(json.dumps(data))
            self.assertEqual(report_files(root),{"report.pdf"})
    def test_corrupt_official_pdf_is_explicit_gap(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/"a").mkdir()
            name="600795_SH_bad.pdf"
            (root/"a"/name).write_bytes(b"not a pdf")
            receipt={"symbols":{"600795.SH":{"files":[{"filename":name,"title":"2026年半年度报告","status":"FETCHED_OFFICIAL_ORIGINAL"}]}}}
            (root/"a"/"A_ORIGINALS_RECEIPT.json").write_text(json.dumps(receipt))
            documents,out=build(root)
            self.assertEqual(len(documents),1)
            self.assertIn("extraction_error",documents[0])
            self.assertEqual(out["store"]["facts"],[])
    def test_build_respects_official_receipt_filter(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            docs,products=build(p)
            self.assertEqual(docs,[])
            self.assertEqual(products["store"]["facts"],[])
            other=p/"600795_SH_unrelated.pdf"
            import fitz
            pdf=fitz.open()
            pdf.new_page()
            pdf.save(str(other))
            pdf.close()
            docs,products=build(p)
            self.assertEqual(docs,[])
    def test_pdf_multiline_financial_label(self):
        import fitz
        with tempfile.TemporaryDirectory() as root:
            filename=Path(root)/"600795_SH_test.pdf"
            pdf=fitz.open()
            page=pdf.new_page()
            page.insert_text((50,50),"Net cash from")
            page.insert_text((50,65),"operating activities")
            pdf.save(str(filename))
            pdf.close()
            result=extract(filename,"600795.SH")
            self.assertGreaterEqual(len(result["table_candidates"]),1)
            self.assertFalse(result["semantic_fact_verified"])
    def test_pdf_source_bound_no_promotion(self):
        import fitz
        with tempfile.TemporaryDirectory() as root:
            pdf=fitz.open()
            page=pdf.new_page()
            page.insert_text((72,72),"Revenue")
            path=Path(root)/"600795_SH_mock.pdf"
            pdf.save(str(path))
            pdf.close()
            result=extract(path,"600795.SH")
            self.assertEqual(len(result["source_sha256"]),64)
            self.assertEqual(result["page_count"],1)
            self.assertEqual(result["facts"],[])
            self.assertFalse(result["semantic_fact_verified"])
if __name__=="__main__":unittest.main()
