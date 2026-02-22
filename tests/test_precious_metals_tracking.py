import unittest

from data.filters_constants import (
    CHINA_STOCKS_KEY,
    IB_STOCKS_KEY,
    IB_STOCKS_VALUE,
    PRECIOUS_METALS_KEY,
)
from src.brokers.ib import InteractiveBrokers
from src.google_sheets.spreadsheet_structure import (
    PortfolioTableBuilder,
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
    def test_builder_adds_precious_metals_pnl_to_column_f(self):
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
        builder = PortfolioTableBuilder(data)

        rows = builder.build_left_columns()

        header_row_idx = next(idx for idx, row in enumerate(rows) if row[3] == "Precious Metals")
        gld_row = next(row for row in rows if row[3] == "GLD")

        self.assertIn(header_row_idx, builder.category_header_rows)
        self.assertEqual(gld_row[4], "1500")
        self.assertEqual(gld_row[5], 0.055)

    def test_create_enhanced_stocks_data_includes_precious_metals_defaults(self):
        enhanced = create_enhanced_stocks_data(
            precious_metals={"GLD": {"market_value": 1500}}
        )

        self.assertIn("Precious Metals", enhanced)
        self.assertIn("GLD", enhanced["Precious Metals"])
        self.assertIn("metadata", enhanced)
        self.assertIn("total_cost_basis", enhanced["metadata"])
        self.assertIn("total_unrealized_pnl", enhanced["metadata"])
        self.assertIn("total_unrealized_pnl_percentage", enhanced["metadata"])


if __name__ == "__main__":
    unittest.main()
