"""Public only reprocesses rolling-window originals, never archived TTM."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import public_original_text


class PublicTextScopeTests(unittest.TestCase):
    def test_historical_ttm_archive_not_reparsed_or_ticker_unknown(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)/"originals"
            for folder in ("a","ttm"):
                (root/folder).mkdir(parents=True)
            current=root/"a/600941_SH_1225573518_26e900128123.pdf"
            historical=root/"ttm/" + ("a"*64+".pdf")
            current.write_bytes(b"PDF_CURRENT_SOURCE_FIXTURE")
            historical.write_bytes(b"PDF_HISTORIC_DO_NOT_PARSE_FIXTURE")
            output=Path(name)/"PUBLIC_ORIGINAL_TEXT_CANDIDATES.json"
            with patch.object(public_original_text,"one",
                              return_value=[{"page":1,"label":"OCF"}]) as extracted:
                with patch.object(sys,"argv",["public_original_text",
                          "--root",str(root),"--output",str(output)]):
                    public_original_text.main()
            d=json.loads(output.read_text())
            self.assertEqual(extracted.call_count,1)
            self.assertEqual(extracted.call_args.args[0],current)
            self.assertEqual(set(d["symbols"]),{"600941.SH"})
            self.assertNotIn("UNKNOWN",d["symbols"])
            self.assertEqual(len(d["sources"]),1)

if __name__=="__main__":
    unittest.main()
