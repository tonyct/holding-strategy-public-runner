import unittest
from ops.public_fact_pipeline_v2 import parse_number
class TableCandidateTests(unittest.TestCase):
    def test_numeric_cells(self):
        self.assertEqual(parse_number("(1,234.50)"),"-1234.50")
        self.assertEqual(parse_number("−2,100"),"-2100")
    def test_ambiguous_cells(self):
        for x in ("2026年","10%","--","1 2 3",""):self.assertIsNone(parse_number(x))
if __name__=="__main__":unittest.main()
