import json,tempfile,unittest
from pathlib import Path
from engine.public_metrics import build
class PublicMetricsTests(unittest.TestCase):
 def test_dynamic_public_metrics_no_portfolio_semantics(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/"a_financials/snapshots").mkdir(parents=True);(r/"hk_financials").mkdir();(r/"quotes").mkdir()
   (r/"u.json").write_text(json.dumps({"stocks":[{"symbol":"A.SH","active":True},{"symbol":"1.HK","active":True}]}))
   a={"period":"2026-06-30","status":"CORE_THREE_STATEMENTS_UNVERIFIED","statements":{
    "income":{"data":{"currency":"CNY","standard_fields":{"revenue":"100","attributable_net_profit":"10","net_profit":"11"}}},
    "cashflow":{"data":{"standard_fields":{"operating_cashflow":"12"}}},
    "balance":{"data":{"standard_fields":{"total_assets":"200","total_liabilities":"80"}}}}}
   (r/"a_financials/snapshots/A_SH_x.json").write_text(json.dumps(a))
   hk={"report_period_end":"2026-06-30","currency":"HKD","statements":{
    "income":{"rows":[{"STD_ITEM_NAME":"营业额","AMOUNT":"100"},{"STD_ITEM_NAME":"股东应占溢利","AMOUNT":"8"}]},
    "cashflow":{"rows":[{"STD_ITEM_NAME":"经营业务现金净额","AMOUNT":"9"}]},
    "balance":{"rows":[{"STD_ITEM_NAME":"总资产","AMOUNT":"150"},{"STD_ITEM_NAME":"总负债","AMOUNT":"60"}]}}}
   (r/"hk_financials/1_HK_x.json").write_text(json.dumps(hk))
   (r/"quotes/QUOTE_RECEIPT.json").write_text(json.dumps({"rows":[{"ticker":"A.SH","close":10},{"ticker":"1.HK","close":20}]}))
   out=build(r,r/"u.json")
   self.assertEqual(out["active_symbol_count"],2);self.assertAlmostEqual(out["stocks"]["A.SH"]["financials"]["derived"]["liability_ratio"],0.4)
   self.assertAlmostEqual(out["stocks"]["1.HK"]["financials"]["derived"]["attributable_net_margin"],0.08)
   self.assertFalse(out["contains_account_state"]);self.assertTrue(out["semantics"]["no_trade_logic"])
if __name__=="__main__":unittest.main()
