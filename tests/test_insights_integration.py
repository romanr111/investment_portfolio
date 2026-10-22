import unittest
from copy import deepcopy
from unittest.mock import Mock
from tests.fake_sheets import FakeSpreadsheet
from tests.fixtures_insights import current_snapshot
from src.google_sheets.spreadsheet_structure import PortfolioUpdater


class InsightsIntegrationTests(unittest.TestCase):
    def test_actual_updater_reuses_unmarked_legacy_timeline_configuration(self):
        book = FakeSpreadsheet()
        timeline = book.add_worksheet("net_worth_timeline", rows=200, cols=4)
        timeline.values.update({(1, 1): 750, (1, 2): "30 Sep 2026", (1, 3): "=A1/2"})
        timeline.charts = [{"chartId": 99, "spec": {"title": "Legacy chart"}}]
        timeline.formats[(1, 1)] = {
            "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}
        }
        timeline.hidden_columns = {3}
        original = deepcopy(
            (timeline.charts, timeline.formats, timeline.hidden_columns)
        )
        updater = object.__new__(PortfolioUpdater)
        updater.spreadsheet = book
        data = current_snapshot()
        for _ in range(2):
            updater.update_portfolio(data, config={})
        self.assertEqual(timeline.values[(2, 1)], data["TOTAL_ASSETS"])
        self.assertEqual(timeline.values[(2, 2)], "04 Oct 2026")
        self.assertEqual(timeline.values[(1, 3)], "=A1/2")
        self.assertEqual(
            (timeline.charts, timeline.formats, timeline.hidden_columns), original
        )
        self.assertEqual((timeline.row_count, timeline.col_count), (200, 4))
        self.assertTrue(all(c <= 3 for r, c in timeline.values))
        data["as_of_date"] = "2026-12-31"
        updater.update_portfolio(data, config={})
        self.assertEqual(timeline.values[(3, 2)], "31 Dec 2026")
        self.assertEqual(book.worksheet("net_worth_timeline").id, timeline.id)
        self.assertEqual(len(book.sheets), 3)

    def test_actual_updater_uses_saved_values_and_only_two_tabs_on_repeated_run(self):
        book = FakeSpreadsheet()
        updater = object.__new__(PortfolioUpdater)
        updater.spreadsheet = book
        data = current_snapshot()
        broker = Mock()
        broker.get_stock_positions_analytics.side_effect = AssertionError(
            "Rendering must not query broker"
        )
        data["IB_CLIENT"] = broker
        updater.update_portfolio(data, config={})
        ids = [s.id for s in book.sheets]
        updater.update_portfolio(data, config={})
        self.assertEqual(
            [s.title for s in book.sheets], ["04 Oct 2026", "net_worth_timeline"]
        )
        self.assertEqual([s.id for s in book.sheets], ids)
        broker.get_stock_positions_analytics.assert_not_called()
        data["as_of_date"] = "2026-12-31"
        updater.update_portfolio(data, config={})
        self.assertEqual(len(book.sheets), 3)
        self.assertEqual(book.worksheet("04 Oct 2026").id, ids[0])
        self.assertEqual(book.worksheet("net_worth_timeline").id, ids[1])
