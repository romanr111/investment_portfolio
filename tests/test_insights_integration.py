import unittest
from unittest.mock import Mock, patch

from src.google_sheets.spreadsheet_structure import PortfolioUpdater


class InsightsIntegrationTests(unittest.TestCase):
    @patch("src.google_sheets.spreadsheet_structure.PortfolioFormatter")
    @patch("src.google_sheets.spreadsheet_structure.PortfolioTableBuilder")
    @patch("src.google_sheets.insights_refresh.refresh_insights")
    def test_portfolio_update_refreshes_insights_from_same_combined_data(
        self, refresh_insights, table_builder_class, formatter_class
    ):
        updater = object.__new__(PortfolioUpdater)
        updater.spreadsheet = object()
        worksheet = object()
        updater.portfolio_sheet = Mock()
        updater.portfolio_sheet.create_tab_at_left.return_value = worksheet
        updater._enrich_with_enhanced_stock_data = Mock()
        updater._write_fixed_income_percentage = Mock()
        updater.update_net_worth_timeline = Mock()
        table_builder = table_builder_class.return_value
        table_builder.build_left_columns.return_value = []
        table_builder.build_central_columns.return_value = []
        table_builder.category_header_rows = []
        data = {"TOTAL_ASSETS": 123.0}

        updater.update_portfolio(data)

        refresh_insights.assert_called_once_with(updater.spreadsheet, data)
        updater.update_net_worth_timeline.assert_called_once_with(123.0)
        formatter_class.return_value.format_portfolio_table.assert_called_once()


if __name__ == "__main__":
    unittest.main()
