import unittest
from tests.fake_sheets import FakeSpreadsheet
from tests.fixtures_insights import current_snapshot
from src.google_sheets.insights_refresh import refresh_insights


class InsightsWriterTests(unittest.TestCase):
    def test_supported_partial_receipts_keep_native_currency_and_coverage(self):
        data = current_snapshot()
        data["INCOME_RECEIPTS"] = {
            "state": "Incomplete",
            "coverage_start": "2026-09-01",
            "coverage_end": "2026-09-30",
            "rows": [
                {
                    "date": "2026-09-15",
                    "source": "Synthetic receipt",
                    "amount": 12.5,
                    "currency": "HKD",
                    "cash_treatment": "Reinvested",
                }
            ],
        }
        book = FakeSpreadsheet()
        refresh_insights(book, data, config={})
        sheet = book.worksheet("04 Oct 2026")
        row = next(
            r
            for (r, c), value in sheet.values.items()
            if c == 2 and value == "Synthetic receipt"
        )
        self.assertEqual(sheet.values[(row, 3)], 12.5)
        self.assertEqual(sheet.values[(row, 4)], "HKD")
        self.assertEqual(sheet.values[(row, 5)], "Reinvested")
        self.assertNotIn("$", sheet.formats[(row, 3)]["numberFormat"]["pattern"])
        self.assertTrue(any(value == "Incomplete" for value in sheet.values.values()))

    def test_refresh_creates_only_main_and_timeline_and_reuses_sheet_ids(self):
        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(
            [sheet.title for sheet in book.sheets],
            ["04 Oct 2026", "net_worth_timeline"],
        )
        ids = [sheet.id for sheet in book.sheets]
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual([sheet.id for sheet in book.sheets], ids)
        self.assertEqual(len(book.worksheet("net_worth_timeline").charts), 1)

    def test_foreign_tab_conflict_has_no_writes_or_extra_tabs(self):
        from src.google_sheets.insights_writer import SheetConflictError

        book = FakeSpreadsheet()
        sheet = book.add_worksheet("net_worth_timeline", cols=6)
        sheet.values[(1, 1)], sheet.values[(1, 2)] = 100, "30 Sep 2026"
        with self.assertRaises(SheetConflictError):
            refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(book.batch_updates, [])
        self.assertEqual(len(book.sheets), 1)

    def test_adoption_preserves_timeline_adjacent_formula_and_user_charts(self):
        from src.google_sheets.insights_writer import preview_adoption

        book = FakeSpreadsheet()
        sheet = book.add_worksheet("net_worth_timeline", cols=6)
        sheet.values[(1, 1)], sheet.values[(1, 2)] = 900, "04 Oct 2026"
        sheet.values[(1, 3)] = "=A1*2"
        sheet.charts.append({"chartId": 99, "spec": {"title": "Deployed Capital"}})
        approval = preview_adoption(sheet, [[0, 1, 0, 2]])
        refresh_insights(
            book, current_snapshot(), config={}, adoptions={sheet.id: approval}
        )
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(sheet.cell(1, 1).value, 900.003)
        self.assertEqual(sheet.cell(1, 3).value, "=A1*2")
        self.assertEqual(len(sheet.charts), 2)
        self.assertEqual(sheet.charts[0]["spec"]["title"], "Deployed Capital")
        self.assertEqual(len(book.sheets), 2)

    def test_growing_main_tab_cannot_overwrite_unowned_formula(self):
        from src.google_sheets.insights_cells import render_blocks
        from src.google_sheets.insights_tables import build_portfolio_tab
        from src.google_sheets.insights_writer import SheetConflictError

        book = FakeSpreadsheet()
        data = current_snapshot()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        old_rows = len(render_blocks(build_portfolio_tab(data).blocks)[0])
        main.values[(old_rows + 1, 1)] = "=123"
        data["IB_DATA"]["Stocks"].update({"NEW" + str(i): 200 for i in range(20)})
        count = len(book.batch_updates)
        with self.assertRaises(SheetConflictError):
            refresh_insights(book, data, config={})
        self.assertEqual(len(book.batch_updates), count)
        self.assertEqual(main.cell(old_rows + 1, 1).value, "=123")

    def test_stale_adoption_and_reserved_marker_conflicts_are_rejected(self):
        from src.google_sheets.insights_writer import (
            preview_adoption,
            SheetConflictError,
            MARKER_COLUMN,
        )

        book = FakeSpreadsheet()
        main = book.add_worksheet("04 Oct 2026")
        main.values[(1, 1)] = "legacy"
        approval = preview_adoption(main, [[0, 1, 0, 1]])
        main.values[(1, 1)] = "user changed it"
        with self.assertRaises(SheetConflictError):
            refresh_insights(
                book, current_snapshot(), config={}, adoptions={main.id: approval}
            )
        self.assertFalse(book.batch_updates)
        main.values[(2, MARKER_COLUMN + 1)] = "private note"
        with self.assertRaises(SheetConflictError):
            preview_adoption(main, [[0, 1, 0, 1]])

    def test_dry_run_and_shrinking_output_keep_ids_groups_and_unrelated_cells(self):
        book = FakeSpreadsheet()
        data = current_snapshot()
        refresh_insights(book, data, config={}, dry_run=True)
        self.assertFalse(book.sheets)
        data["IB_DATA"]["Stocks"].update({"NEW" + str(i): 200 for i in range(30)})
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        old_rows = max(r for r, c in main.values if c == 1)
        main.values[(1, 12)] = "manual note"
        ids = [s.id for s in book.sheets]
        refresh_insights(book, current_snapshot(), config={})
        count = len(main.groups)
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(len(main.groups), count)
        self.assertEqual(main.cell(1, 12).value, "manual note")
        self.assertIn(main.cell(old_rows, 1).value, ("", None))
        self.assertEqual([s.id for s in book.sheets], ids)
        self.assertEqual(main.properties["frozenRowCount"], 8)
        self.assertEqual(main.basic_filter["range"]["startRowIndex"], 7)

    def test_main_uses_wrapping_and_bounded_resize_for_readable_labels(self):
        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        requests = book.batch_updates[0]["requests"]
        self.assertTrue(any("autoResizeDimensions" in request for request in requests))
        self.assertEqual(
            book.worksheet("04 Oct 2026").formats[(4, 1)].get("wrapStrategy"), "WRAP"
        )

    def test_timeline_accepts_saved_iso_timestamp_dates(self):
        from src.google_sheets.insights_writer import preview_adoption

        book = FakeSpreadsheet()
        sheet = book.add_worksheet("net_worth_timeline")
        sheet.values[(1, 1)], sheet.values[(1, 2)] = 750, "2026-06-30T00:00:00.000Z"
        approval = preview_adoption(sheet, [[0, 1, 0, 2]])
        refresh_insights(
            book, current_snapshot(), config={}, adoptions={sheet.id: approval}
        )
        self.assertEqual(len(book.sheets), 2)

    def test_history_chart_uses_hidden_helper_data(self):
        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(
            book.worksheet("net_worth_timeline")
            .charts[0]["spec"]
            .get("hiddenDimensionStrategy"),
            "SHOW_ALL",
        )

    def test_pnl_has_explicit_sign_and_display_rounding_keeps_tiny_values(self):
        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        main = book.worksheet("04 Oct 2026")
        self.assertTrue(main.formats[(9, 6)]["numberFormat"]["pattern"].startswith("+"))
        self.assertEqual(
            main.formats[(9, 4)]["numberFormat"]["pattern"], "+0.00%;-0.00%;0.00%"
        )
        tiny_row = next(
            r for (r, c), value in main.values.items() if c == 1 and value == "TINY"
        )
        self.assertEqual(main.values[(tiny_row, 3)], 0.003)
        self.assertIn(
            "#", main.formats[(tiny_row, 3)]["numberFormat"]["pattern"].split(".")[1]
        )

    def test_explicit_main_adoption_clears_only_reviewed_legacy_regions(self):
        from src.google_sheets.insights_writer import preview_adoption

        book = FakeSpreadsheet()
        main = book.add_worksheet("04 Oct 2026")
        main.values[(3, 8)] = "old total"
        main.values[(3, 12)] = "old income"
        main.values[(1, 13)] = "user note"
        approval = preview_adoption(main, [[0, 150, 0, 12]])
        refresh_insights(
            book, current_snapshot(), config={}, adoptions={main.id: approval}
        )
        self.assertEqual(main.cell(1, 13).value, "user note")
        self.assertIn(main.cell(3, 12).value, ("", None))
        self.assertEqual(main.cell(3, 2).value, 900.003)

    def test_helper_collision_and_duplicate_dates_abort_before_any_write(self):
        from src.google_sheets.insights_writer import (
            preview_adoption,
            SheetConflictError,
        )

        for duplicate in (False, True):
            book = FakeSpreadsheet()
            sheet = book.add_worksheet("net_worth_timeline")
            sheet.values[(1, 1)], sheet.values[(1, 2)] = 750, "30 Jun 2026"
            if duplicate:
                sheet.values[(2, 1)], sheet.values[(2, 2)] = 800, "30 Jun 2026"
            else:
                sheet.values[(1, 5)] = "user formula"
            approval = preview_adoption(sheet, [[0, 2, 0, 2]])
            with self.assertRaises(SheetConflictError):
                refresh_insights(
                    book, current_snapshot(), config={}, adoptions={sheet.id: approval}
                )
            self.assertFalse(book.batch_updates)
            self.assertEqual(len(book.sheets), 1)

    def test_growth_cannot_overwrite_a_blank_cell_with_a_user_note(self):
        from src.google_sheets.insights_cells import render_blocks
        from src.google_sheets.insights_tables import build_portfolio_tab
        from src.google_sheets.insights_writer import SheetConflictError

        book = FakeSpreadsheet()
        data = current_snapshot()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        rows = len(render_blocks(build_portfolio_tab(data).blocks)[0])
        main.annotations[(rows, 0)] = {"note": "User note on an otherwise blank cell"}
        data["IB_DATA"]["Stocks"].update({"NEW" + str(i): 200 for i in range(20)})
        count = len(book.batch_updates)
        with self.assertRaises(SheetConflictError):
            refresh_insights(book, data, config={})
        self.assertEqual(len(book.batch_updates), count)

    def test_typed_unavailable_money_is_written_as_status_without_crashing(self):
        from dataclasses import replace
        from src.google_sheets.insights_cells import CellBlock, CellValue
        from src.google_sheets.insights_tables import build_portfolio_tab
        from src.google_sheets.insights_writer import write_portfolio_snapshot

        tab = build_portfolio_tab(current_snapshot())
        rows = list(tab.blocks[0].rows)
        row = list(rows[2])
        row[1] = CellValue(None, "money")
        rows[2] = tuple(row)
        tab = replace(tab, blocks=(CellBlock("summary", tuple(rows)), *tab.blocks[1:]))
        book = FakeSpreadsheet()
        write_portfolio_snapshot(book, tab, "2026-10-04", 900.003)
        self.assertEqual(book.worksheet("04 Oct 2026").cell(3, 2).value, "Unavailable")

    def test_new_reporting_date_is_created_at_the_front(self):
        book = FakeSpreadsheet()
        data = current_snapshot()
        refresh_insights(book, data, config={})
        data["as_of_date"] = "2026-12-31"
        refresh_insights(book, data, config={})
        self.assertEqual(book.sheets[0].title, "31 Dec 2026")

    def test_invalid_helper_metadata_cannot_clear_adjacent_timeline_cells(self):
        import json
        from src.google_sheets.insights_writer import MARKER_COLUMN, SheetConflictError

        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        timeline = book.worksheet("net_worth_timeline")
        timeline.values[(1, 3)] = "=A1/2"
        metadata = json.loads(timeline.values[(2, MARKER_COLUMN + 1)])
        metadata["helper_ranges"] = [[0, 2, 2, 6]]
        timeline.values[(2, MARKER_COLUMN + 1)] = json.dumps(metadata)
        count = len(book.batch_updates)
        with self.assertRaises(SheetConflictError):
            refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(len(book.batch_updates), count)
        self.assertEqual(timeline.values[(1, 3)], "=A1/2")
