import unittest

from data.filters_constants import (
    CHINA_STOCKS_KEY,
    IB_STOCKS_KEY,
    IB_STOCKS_VALUE,
    PRECIOUS_METALS_KEY,
)
from src.brokers.ib import InteractiveBrokers
from src.google_sheets.insights_tables import build_portfolio_tab
from src.google_sheets.spreadsheet_structure import (
    create_enhanced_stocks_data,
)


class TestInteractiveBrokersPreciousMetalsAnalytics(unittest.TestCase):
    def test_stock_analytics_includes_precious_metals_and_keeps_stock_metadata_scope(self):
        ib = InteractiveBrokers.__new__(InteractiveBrokers)
        ib._enhanced_stock_data = None
        ib._portfolio_positions = {
            CHINA_STOCKS_KEY: {"700": 1000},
            IB_STOCKS_KEY: {"AAPL": 2000},
            PRECIOUS_METALS_KEY: {"GLD": 1500},
            IB_STOCKS_VALUE: 3000,
            "IB_Portfolio_Value": 10000,
        }
        ib.all_portfolio_info = [
            {"contractDesc": "700", "position": 10, "avgPrice": 100, "mktPrice": 110},
            {
                "contractDesc": "AAPL",
                "position": 5,
                "avgPrice": 300,
                "mktPrice": 330,
            },
            {"contractDesc": "GLD", "position": 2, "avgPrice": 200, "mktPrice": 220},
        ]

        analytics = ib.get_stock_positions_analytics()

        self.assertIn(PRECIOUS_METALS_KEY, analytics)
        self.assertIn("GLD", analytics[PRECIOUS_METALS_KEY])
        self.assertEqual(
            analytics[PRECIOUS_METALS_KEY]["GLD"]["unrealized_pnl_percentage"], 10.0
        )
        self.assertEqual(
            analytics[PRECIOUS_METALS_KEY]["GLD"]["percentage_of_stocks"], 0
        )

        metadata = analytics["metadata"]
        self.assertAlmostEqual(metadata["total_cost_basis"], 2500.0)
        self.assertAlmostEqual(metadata["total_unrealized_pnl"], 250.0)
        self.assertAlmostEqual(metadata["total_unrealized_pnl_percentage"], 10.0)


class TestSpreadsheetPreciousMetalsRendering(unittest.TestCase):
    def test_main_tab_keeps_precious_metals_pnl(self):
        data = {
            "IB_DATA": {
                CHINA_STOCKS_KEY: {"700": 1000},
                IB_STOCKS_KEY: {"AAPL": 2000},
                PRECIOUS_METALS_KEY: {"GLD": 1500},
            },
            "ENHANCED_STOCKS": create_enhanced_stocks_data(
                china_stocks={"700": {"unrealized_pnl_percentage": 1.2}},
                regular_stocks={"AAPL": {"unrealized_pnl_percentage": 2.3}},
                precious_metals={"GLD": {"unrealized_pnl_percentage": 5.5}},
            ),
        }
        tab = build_portfolio_tab(data, current_date="2026-09-30")
        rows = next(
            block.rows for block in tab.blocks if block.name == "holding_details"
        )
        gld_row = next(row for row in rows if row[0] == "GLD")
        self.assertEqual(gld_row[2].value, 1500)
        self.assertEqual(gld_row[7].value, 0.055)


if __name__ == "__main__":
    unittest.main()
