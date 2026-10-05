import unittest

from src.google_sheets.insights_cells import CellValue
from src.google_sheets.insights_tables import (
    INSIGHT_TAB_TITLES,
    LBL_ESTIMATED_MONTHLY_INCOME,
    LBL_IB_RETURN,
    LBL_UNREALIZED_PNL,
    build_insight_tabs,
)
from tests.fixtures_insights import current_snapshot, previous_snapshot


def _values(value):
    if isinstance(value, CellValue):
        yield value.value
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _values(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from _values(child)
    else:
        yield value


class InsightsTablesTests(unittest.TestCase):
    def test_eight_tabs_contain_required_labels_and_typed_financial_values(self):
        tabs = build_insight_tabs(
            current_snapshot(),
            config={},
            previous_snapshot=previous_snapshot(),
            previous_date="2026-09-30",
            current_date="2026-10-04",
            history_snapshots=[
                {"as_of_date": "2026-09-30", "data": previous_snapshot()},
                {"as_of_date": "2026-10-04", "data": current_snapshot()},
            ],
        )

        self.assertEqual(tuple(tabs), INSIGHT_TAB_TITLES)
        all_values = list(
            _values([block.rows for tab in tabs.values() for block in tab.blocks])
        )
        self.assertIn(LBL_IB_RETURN, all_values)
        self.assertIn(LBL_UNREALIZED_PNL, all_values)
        self.assertIn(LBL_ESTIMATED_MONTHLY_INCOME, all_values)
        self.assertEqual(LBL_IB_RETURN, "IB return - YTD - TWR")
        self.assertEqual(LBL_UNREALIZED_PNL, "Unrealized P&L vs cost")
        self.assertEqual(
            LBL_ESTIMATED_MONTHLY_INCOME,
            "Estimated investment income - monthly average",
        )
        self.assertNotIn("CRYPTO_DATA", all_values)
        self.assertEqual(tabs["Holdings"].header_offsets["holdings"], 9)
        self.assertEqual(
            tabs["Holdings"].blocks[0].rows[9],
            (
                "Asset",
                "Account",
                "Value USD",
                "% of total assets",
                "% of IB portfolio",
                "Unrealized P&L",
                "P&L currency",
                "Unrealized P&L vs cost",
            ),
        )
        self.assertIsInstance(tabs["Holdings"].blocks[0].rows[10][2], CellValue)
        self.assertEqual(tabs["Holdings"].blocks[0].rows[10][5].kind, "number")
        self.assertIn("Deviation basis", tabs["Allocation"].blocks[0].rows[1])
        self.assertIn("Target not configured", all_values)
        self.assertTrue(tabs["Overview"].charts)

    def test_other_bets_components_are_not_added_to_reported_subtotal(self):
        data = current_snapshot()
        data["OTHER_ASSETS"].update({"Equipment": 25.0, "Other Bets": 100.0})

        tabs = build_insight_tabs(data)
        component_rows = tabs["Allocation"].blocks[1].rows

        self.assertEqual(component_rows[2][0], "Equipment")
        self.assertIn("not added", component_rows[2][2])
        self.assertEqual(component_rows[3][0], "Reported Other Bets subtotal")
        self.assertEqual(component_rows[3][1].value, 100.0)


if __name__ == "__main__":
    unittest.main()
