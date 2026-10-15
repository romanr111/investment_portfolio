import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.data_source import DataSource, FINANCIAL_FREEDOM_GOAL


class DataSourceInsightsTests(unittest.TestCase):
    def test_combined_snapshot_serializes_the_configured_fire_target(self):
        source = object.__new__(DataSource)
        source._data_timestamp = 1791115200
        source._calculate_asset_allocation = lambda: {}
        analytics = {"Stocks": {"SYNTH": {"unrealized_pnl_percentage": 7.05}}}
        source.ib = SimpleNamespace(performance_ytd={}, get_stock_positions_analytics=lambda: analytics)
        source.index_performance_data = {}
        source.ib_data = {}
        source.crypto = SimpleNamespace(
            get_total_crypto_value=lambda: 0,
            crypto_market_values={},
            quantities={},
        )
        source.fi_data = {"group_weighted_interest": {}}
        source.cash = SimpleNamespace(total_cash=0, as_dict=lambda: {})
        source.total_assets = 0
        source.ff_progress = "0%"
        source._save_combined_data_to_json = Mock()

        with patch("src.data_source.time.time", return_value=1791115260):
            combined_data = source.get_combined_data()

        self.assertEqual(
            combined_data["FINANCIAL_FREEDOM_GOAL_TARGET"], FINANCIAL_FREEDOM_GOAL
        )
        self.assertEqual(combined_data.get("ENHANCED_STOCKS"), analytics)
        source._save_combined_data_to_json.assert_called_once_with(combined_data)


if __name__ == "__main__":
    unittest.main()
