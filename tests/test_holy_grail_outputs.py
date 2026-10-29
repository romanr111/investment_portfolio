"""Both output adapters consume one saved result, without collecting market data."""
import importlib
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from test_holy_grail_data import saved_legacy_fixture
from src.google_sheets.insights_tables import build_portfolio_tab
from src.google_sheets.insights_cells import render_blocks

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "portfolio_yic_reports"))
from generate_quarterly_report import build_report_data
from quarterly_report_html import render_report
from test_quarterly_report_html import _make_analyzer


def sheet_table(data):
    return render_blocks(build_portfolio_tab(data).blocks)[0]


class HolyGrailOutputTests(unittest.TestCase):
    def saved(self):
        return saved_legacy_fixture("qualified")

    def html(self, data):
        return render_report(build_report_data(_make_analyzer(), "20260930", -6.8, 9.3,
                                               {"Stocks": 100}, {"Stocks": 100}, data))

    def test_legacy_sheets_and_html_use_the_same_saved_count_offline(self):
        saved = self.saved()
        del saved["DIVERSIFICATION_DATA"]
        with patch("analytics.holy_grail_data.collect_return_history", side_effect=AssertionError("Outputs must not collect data")):
            table = sheet_table(saved)
            self.assertTrue(any(row[:2] == ["Диверсифікація /100", "Нова оцінка відсутня"] for row in table),
                            "The current spreadsheet does not display saved Holy Grail progress")
            document = self.html(saved)
            self.assertIn("Диверсифікація: Holy Grail", document)
            self.assertIn("Попередній метод", document)
            self.assertNotIn('<p class="hg-value">100,0%</p>', document)
            self.assertIn("15,00", document)
            self.assertIn("30.09.2026", document)

    def test_unreviewed_hundred_percent_is_not_an_achievement_headline(self):
        from analytics.holy_grail import saved_progress_view
        data = self.saved()
        data["HOLY_GRAIL_DATA"].update(target_achieved=False, constraints=["qualification_pending"])
        view = saved_progress_view(data)
        self.assertEqual(view["headline"], "Ціль не підтверджена")
        self.assertIsNone(view["fraction"])

    def test_changed_holdings_and_wrong_quarter_reject_a_saved_score(self):
        from analytics.holy_grail import saved_progress_view
        data = self.saved()
        data["IB_DATA"]["Stocks"]["asset_0"] = 200
        self.assertIsNone(saved_progress_view(data)["fraction"])
        self.assertIsNone(saved_progress_view(self.saved(), expected_date="2026-06-30")["fraction"])

    def test_public_report_does_not_serialize_private_provenance(self):
        data = self.saved()
        data["HOLY_GRAIL_DATA"]["source_provenance"] = {"secret_account_name": "PRIVATE-BALANCE-12345"}
        self.assertNotIn("PRIVATE-BALANCE", self.html(data))

    def test_changed_input_quality_rejects_an_earlier_achievement(self):
        from analytics.holy_grail import saved_progress_view
        data = self.saved()
        self.assertEqual(saved_progress_view(data)["fraction"], 1)
        data["DATA_QUALITY"] = {"crypto": {"freshness": "stale"}}
        self.assertIsNone(saved_progress_view(data)["fraction"])
        self.assertNotIn("Ціль досягнута", saved_progress_view(data)["status"])

    def test_sheet_formatting_targets_numeric_fraction_and_only_new_details(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from src.google_sheets.formatting import PortfolioFormatter
        sheet = SimpleNamespace(id=27, spreadsheet=Mock())
        PortfolioFormatter(sheet).format_holy_grail((100, 120))
        requests = sheet.spreadsheet.batch_update.call_args.args[0]["requests"]
        number = requests[0]["repeatCell"]
        self.assertEqual(number["range"]["startRowIndex"], 9)
        self.assertEqual(number["cell"]["userEnteredFormat"]["numberFormat"]["pattern"], "0.0%")
        group = next(request["addDimensionGroup"] for request in requests if "addDimensionGroup" in request)
        self.assertEqual(group["range"]["startIndex"], 100)
        self.assertEqual(group["range"]["endIndex"], 120)


if __name__ == "__main__":
    unittest.main()
