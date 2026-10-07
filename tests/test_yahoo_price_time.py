import unittest
from datetime import datetime, timezone

from engine.quote_secondary import parse_yahoo

NOW = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
BAR = int(datetime(2026, 10, 7, 1, 30, tzinfo=timezone.utc).timestamp())
OBSERVED = int(datetime(2026, 10, 7, 8, 8, tzinfo=timezone.utc).timestamp())


class YahooPriceTimeTests(unittest.TestCase):
    def chart(self):
        return {"meta": {"symbol": "0148.HK", "currency": "HKD",
                         "regularMarketPrice": 60.55, "regularMarketTime": OBSERVED},
                "timestamp": [BAR], "indicators": {"quote": [{"close": [60.549999]}]}}

    def test_provider_observation_controls_price_and_time(self):
        row = parse_yahoo("148.HK", self.chart(), NOW)
        self.assertEqual(row["close"], 60.55)
        self.assertEqual(row["source_timestamp_utc"], "2026-10-07T08:08:00+00:00")
        self.assertEqual(row["source_timestamp_role"], "PROVIDER_PRICE_OBSERVATION")
        self.assertFalse(row["exchange_close_independently_certified"])

    def test_daily_bar_start_is_never_reported_as_actual_price_time(self):
        chart = self.chart()
        chart["meta"].pop("regularMarketTime")
        row = parse_yahoo("148.HK", chart, NOW)
        self.assertIsNone(row["source_timestamp_utc"])
        self.assertEqual(row["bar_start_timestamp_utc"], "2026-10-07T01:30:00+00:00")
        self.assertEqual(row["market_session_date"], "2026-10-07")

    def test_wrong_instrument_is_rejected(self):
        chart = self.chart()
        chart["meta"]["symbol"] = "0700.HK"
        with self.assertRaisesRegex(ValueError, "SYMBOL_MISMATCH"):
            parse_yahoo("148.HK", chart, NOW)

    def test_wrong_currency_is_rejected(self):
        chart = self.chart()
        chart["meta"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "CURRENCY_MISMATCH"):
            parse_yahoo("148.HK", chart, NOW)

    def test_future_metadata_does_not_make_a_bar_price_fresh(self):
        chart = self.chart()
        chart["meta"]["regularMarketTime"] = int(NOW.timestamp()) + 3600
        self.assertIsNone(parse_yahoo("148.HK", chart, NOW)["source_timestamp_utc"])

    def test_bad_metadata_price_does_not_become_an_executable_quote(self):
        chart = self.chart()
        chart["meta"]["regularMarketPrice"] = -1
        row = parse_yahoo("148.HK", chart, NOW)
        self.assertEqual(row["source_timestamp_role"], "UNKNOWN_PRICE_OBSERVATION_TIME")


if __name__ == "__main__":
    unittest.main()
