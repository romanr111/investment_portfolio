"""Saved-data enrichment and historical-price boundary contracts."""
import importlib
import importlib.util
from copy import deepcopy
import unittest
import tempfile
import json
from decimal import Decimal
from pathlib import Path
import pandas as pd

from test_holy_grail_progress import independent_history, exposures


def snapshot_fixture():
    return {
        "IB_DATA": {"Stocks": {f"asset_{i}": 100 for i in range(15)}},
        "TOTAL_ASSETS": 1500,
        "CASH_DATA": {"Total": 0},
        "DATA_METADATA": {"last_updated": "2026-09-30T20:00:00"},
        "POSITION_DATA": {"as_of_date": "2026-09-30"},
        "IB_PERFORMANCE": {"rate_of_return_pct": -6.8},
    }


class HolyGrailDataTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("analytics.holy_grail_data"),
                             "The saved portfolio enrichment path is not implemented")
        return importlib.import_module("analytics.holy_grail_data")

    def test_saved_holdings_enrichment_preserves_existing_values(self):
        original = snapshot_fixture()
        untouched = deepcopy(original)
        returns = independent_history().rename(columns=lambda s: "yf:" + s)
        config = {"qualifications": {"Stocks": exposures()[0]["qualification"]}}
        result = self.module().enrich_combined_data(
            original, as_of_date="2026-09-30", monthly_returns=returns, config=config,
            allow_network=False,
        )
        self.assertEqual(original, untouched)
        self.assertEqual({k:v for k,v in result.items() if k != "HOLY_GRAIL_DATA"}, original)
        self.assertAlmostEqual(result["HOLY_GRAIL_DATA"]["effective_streams"], 15)
        self.assertTrue(result["HOLY_GRAIL_DATA"]["target_achieved"])

    def test_adjusted_prices_convert_fx_without_filling_missing_months(self):
        module = self.module()
        self.assertTrue(hasattr(module, "monthly_usd_returns"), "The adjusted-price return collector is not implemented")
        prices = pd.Series([100, 110, 121, 133.1], index=pd.to_datetime(["2025-12-31", "2026-01-31", "2026-03-31", "2026-04-30"]))
        fx = pd.Series([1.1, 1.2, 1.3, 1.4], index=prices.index)
        returns = module.monthly_usd_returns(prices, "EUR", "2026-04-30", fx_prices=fx)
        self.assertAlmostEqual(returns.loc["2026-01-31"], 132/110-1)
        self.assertTrue(pd.isna(returns.loc["2026-03-31"]))
        self.assertAlmostEqual(returns.loc["2026-04-30"], (133.1*1.4)/(121*1.3)-1)

    def test_undated_holdings_cannot_confirm_achievement(self):
        original = snapshot_fixture()
        del original["DATA_METADATA"]
        del original["POSITION_DATA"]
        result = self.module().enrich_combined_data(
            original, as_of_date="2026-09-30",
            monthly_returns=independent_history().rename(columns=lambda s: "yf:" + s),
            config={"qualifications": {"Stocks": exposures()[0]["qualification"]}},
        )["HOLY_GRAIL_DATA"]
        self.assertFalse(result["target_achieved"])
        self.assertIn("valuation_date_unverified", result["constraints"])

    def test_fingerprint_survives_both_existing_decimal_serializers(self):
        from analytics.holy_grail import holdings_fingerprint, saved_progress_view
        original = snapshot_fixture()
        original["CASH_DATA"] = {"Total": Decimal("10.00"), "Breakdown": {"USD": Decimal("10.00")}}
        original["TOTAL_ASSETS"] = 1510
        result = self.module().enrich_combined_data(
            original, monthly_returns=independent_history().rename(columns=lambda s: "yf:" + s), config={},
        )
        for serializer in (str, float):
            saved = json.loads(json.dumps(result, default=serializer))
            self.assertEqual(holdings_fingerprint(saved), holdings_fingerprint(result))
            self.assertEqual(saved_progress_view(saved)["as_of"], "30.09.2026")

    def test_successful_history_is_reused_offline_and_future_returns_are_removed(self):
        module = self.module()
        self.assertTrue(hasattr(module, "collect_return_history"), "Persistent history collection is not implemented")
        prices = pd.Series(range(100, 164), index=pd.date_range(end="2026-12-31", periods=64, freq="ME"))
        calls = []
        def fetch(symbol, start, end):
            calls.append(symbol)
            return {"prices": prices, "currency": "USD", "frequency": "daily"}
        position = [{"series": "yf:TEST", "symbol": "TEST", "provider": "yfinance", "currency": None}]
        with tempfile.TemporaryDirectory() as directory:
            a, _, _ = module.collect_return_history(position, as_of_date="2026-09-30", cache_dir=directory,
                                                     allow_network=True, fetch_market=fetch)
            b, _, _ = module.collect_return_history(position, as_of_date="2026-09-30", cache_dir=directory,
                                                     allow_network=False, fetch_market=fetch)
            pd.testing.assert_frame_equal(a, b)
            self.assertEqual(calls, ["TEST"])
            self.assertLessEqual(a.index.max(), pd.Timestamp("2026-09-30"))

    def test_snapshot_replay_preserves_source_and_latest_pointer(self):
        module = self.module()
        self.assertTrue(hasattr(module, "enrich_snapshot_file"), "Safe historical snapshot replay is not implemented")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshots = root / "snapshots"
            snapshots.mkdir()
            source = snapshots / "combined_data_2026-09-30_saved.json"
            payload = {"as_of_date": "2026-09-30", "data": snapshot_fixture()}
            source.write_text(json.dumps(payload))
            latest = snapshots / "combined_data_latest.json"
            latest.write_text("original latest pointer")
            source_bytes = source.read_bytes()
            destination = root / "derived" / "q3.json"
            module.enrich_snapshot_file(source, destination, allow_network=False, cache_dir=root / "cache", config={})
            result = json.loads(destination.read_text())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(latest.read_text(), "original latest pointer")
            self.assertEqual(result["as_of_date"], "2026-09-30")
            self.assertIn("HOLY_GRAIL_DATA", result["data"])
            self.assertEqual({k:v for k,v in result["data"].items() if k != "HOLY_GRAIL_DATA"}, payload["data"])
            with self.assertRaises(ValueError):
                module.enrich_snapshot_file(source, source, allow_network=False)
            with self.assertRaises(ValueError):
                module.enrich_snapshot_file(source, latest, allow_network=False)

    def test_incomplete_final_month_is_refreshed(self):
        module = self.module()
        calls = []
        def fetch(symbol, start, end):
            calls.append(symbol)
            stamps = ["2026-08-31", "2026-09-01" if len(calls) == 1 else "2026-09-30"]
            return {"prices": pd.Series([100, 110], index=pd.to_datetime(stamps)),
                    "currency": "USD", "frequency": "daily"}
        position = [{"series": "yf:TEST", "symbol": "TEST", "provider": "yfinance"}]
        with tempfile.TemporaryDirectory() as directory:
            first, _, _ = module.collect_return_history(position, as_of_date="2026-09-30", cache_dir=directory,
                                                        fetch_market=fetch)
            second, _, _ = module.collect_return_history(position, as_of_date="2026-09-30", cache_dir=directory,
                                                         fetch_market=fetch)
            self.assertTrue(pd.isna(first.loc["2026-09-30", "yf:TEST"]))
            self.assertAlmostEqual(second.loc["2026-09-30", "yf:TEST"], 0.1)
            self.assertEqual(len(calls), 2)

    def test_cached_balance_quality_blocks_achievement_even_with_current_envelope(self):
        original = snapshot_fixture()
        del original["IB_DATA"]["Stocks"]["asset_14"]
        original["POSITION_DATA"]["crypto"] = [{"asset": "asset_14", "value_usd": 100}]
        original["DATA_QUALITY"] = {"crypto": {"freshness": "stale"}}
        history = independent_history().rename(columns=lambda s: "yf:" + s + ("-USD" if s == "asset_14" else ""))
        reviewed = exposures()[0]["qualification"]
        config = {"qualifications": {"Stocks": reviewed, "Crypto Coins": reviewed}}
        result = self.module().enrich_combined_data(original, monthly_returns=history, config=config)["HOLY_GRAIL_DATA"]
        self.assertIn("stale_valuations", result["constraints"])
        self.assertFalse(result["target_achieved"])
        original["DATA_QUALITY"]["crypto"]["freshness"] = "live"
        self.assertTrue(self.module().enrich_combined_data(original, monthly_returns=history, config=config)["HOLY_GRAIL_DATA"]["target_achieved"])


if __name__ == "__main__":
    unittest.main()
