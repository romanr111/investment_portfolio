import unittest
from tests.fake_sheets import FakeSpreadsheet
from tests.fixtures_insights import current_snapshot
from src.google_sheets.insights_refresh import refresh_insights


class InsightsWriterTests(unittest.TestCase):
    def test_compact_small_values_and_unavailable_cells_keep_their_meaning(self):
        for amount, decimals in ((0, 0), (0.004, 3), (-0.004, 3), (0.42, 2), (1.01, 0)):
            with self.subTest(amount=amount):
                data = current_snapshot()
                data["TOTAL_ASSETS"] = amount
                data["ENHANCED_STOCKS"]["Stocks"]["AAA"][
                    "unrealized_pnl_percentage"
                ] = 0.0001
                book = FakeSpreadsheet()
                refresh_insights(book, data, config={})
                main = book.worksheet("04 Oct 2026")
                self.assertEqual(main.values[(1, 8)], amount)
                pattern = main.formats[(1, 8)]["numberFormat"]["pattern"].split(";")[0]
                self.assertEqual(len(pattern.partition(".")[2]), decimals)
                aaa_row = next(
                    r for (r, c), v in main.values.items() if c == 4 and v == "AAA"
                )
                self.assertAlmostEqual(main.values[(aaa_row, 6)], 0.000001)
                self.assertTrue(
                    main.formats[(aaa_row, 6)]["numberFormat"]["pattern"].startswith(
                        "+0.0000%"
                    )
                )
        data = current_snapshot()
        data["IB_PERFORMANCE"]["rate_of_return_pct"] = None
        data.pop("FINANCIAL_FREEDOM_GOAL_TARGET")
        data["FIXED_INCOME_DATA"]["group_weighted_interest"].pop("Bonds")
        book = FakeSpreadsheet()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        unavailable_row = next(
            r
            for (r, c), v in main.values.items()
            if c == 1 and v == "IB return - YTD - TWR"
        )
        self.assertEqual(main.values[(unavailable_row, 2)], "Unavailable")
        self.assertNotIn("numberFormat", main.formats[(unavailable_row, 2)])
        self.assertTrue(
            any(v == "Monthly average (partial)" for v in main.values.values())
        )

    def test_return_gradient_updates_without_duplicates_or_removing_user_rules(self):
        from copy import deepcopy

        book = FakeSpreadsheet()
        data = current_snapshot()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        custom = {
            "ranges": [
                {
                    "sheetId": main.id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 15,
                    "endColumnIndex": 16,
                }
            ],
            "booleanRule": {
                "condition": {
                    "type": "NUMBER_GREATER",
                    "values": [{"userEnteredValue": "10"}],
                },
                "format": {"textFormat": {"bold": True}},
            },
        }
        main.conditional_formats.insert(0, deepcopy(custom))
        # Sheets readback rounds RGB channels and may expose colorStyle as well.
        for point in main.conditional_formats[1]["gradientRule"].values():
            point["color"] = {k: round(v, 7) for k, v in point["color"].items()}
            point["colorStyle"] = {"rgbColor": dict(point["color"])}
        data["IB_DATA"]["Stocks"]["NEW"] = 300
        refresh_insights(book, data, config={})
        refresh_insights(book, data, config={})
        self.assertEqual(len(main.conditional_formats), 2)
        self.assertIn(custom, main.conditional_formats)
        del data["IB_DATA"]["Stocks"]["NEW"]
        refresh_insights(book, data, config={})
        self.assertEqual(len(main.conditional_formats), 2)
        self.assertIn(custom, main.conditional_formats)


    def test_headers_are_neutral_and_position_returns_have_the_original_gradient(self):
        from src.google_sheets.insights_cells import render_blocks
        from src.google_sheets.insights_tables import build_portfolio_tab

        data = current_snapshot()
        book = FakeSpreadsheet()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        _, _, ranges = render_blocks(build_portfolio_tab(data).blocks)
        for block, (r0, r1, c0, c1) in ranges.items():
            color = main.formats[(r0 + 1, c0 + 1)]["backgroundColor"]
            self.assertEqual(
                color, {"red": 241 / 255, "green": 240 / 255, "blue": 236 / 255}, block
            )
        self.assertEqual(len(main.conditional_formats), 1)
        rule = main.conditional_formats[0]
        points = rule["gradientRule"]
        self.assertEqual(float(points["minpoint"]["value"]), -0.30)
        self.assertEqual(float(points["midpoint"]["value"]), 0)
        self.assertEqual(float(points["maxpoint"]["value"]), 0.50)
        self.assertEqual(points["midpoint"]["color"], {"red": 1, "green": 1, "blue": 1})
        self.assertGreater(
            points["minpoint"]["color"]["red"], points["minpoint"]["color"]["green"]
        )
        self.assertGreater(
            points["maxpoint"]["color"]["green"], points["maxpoint"]["color"]["red"]
        )
        self.assertEqual([r["startColumnIndex"] for r in rule["ranges"]], [5, 7])
        aaa_row = next(
            r for (r, c), value in main.values.items() if c == 4 and value == "AAA"
        )
        self.assertAlmostEqual(main.values[(aaa_row, 6)], 0.0705)

    def test_moving_details_unhides_previously_generated_rows(self):
        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        main = book.worksheet("04 Oct 2026")
        old_start = next(iter(main.groups))[0]
        self.assertIn(old_start, main.hidden_rows)
        data = current_snapshot()
        data["IB_DATA"]["Stocks"].update({f"NEW{i}": 200 for i in range(40)})
        refresh_insights(book, data, config={})
        self.assertNotIn(old_start, main.hidden_rows)


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
        timeline = book.worksheet("net_worth_timeline")
        self.assertEqual(timeline.col_count, 2)
        self.assertEqual(timeline.charts, [])

    def test_foreign_tab_conflict_has_no_writes_or_extra_tabs(self):
        from src.google_sheets.insights_writer import SheetConflictError

        book = FakeSpreadsheet()
        sheet = book.add_worksheet("04 Oct 2026", cols=12)
        sheet.values[(1, 1)] = "user data"
        with self.assertRaises(SheetConflictError):
            refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(book.batch_updates, [])
        self.assertEqual(len(book.sheets), 1)

    def test_legacy_timeline_preserves_adjacent_formula_and_user_charts(self):
        book = FakeSpreadsheet()
        sheet = book.add_worksheet("net_worth_timeline", cols=6)
        sheet.values[(1, 1)], sheet.values[(1, 2)] = 900, "04 Oct 2026"
        sheet.values[(1, 3)] = "=A1*2"
        sheet.charts.append({"chartId": 99, "spec": {"title": "Deployed Capital"}})
        refresh_insights(book, current_snapshot(), config={})
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(sheet.cell(1, 1).value, 900.003)
        self.assertEqual(sheet.cell(1, 3).value, "=A1*2")
        self.assertEqual(len(sheet.charts), 1)
        self.assertEqual(sheet.cell(1, 2).value, "04 Oct 2026")
        self.assertEqual(sheet.charts[0]["spec"]["title"], "Deployed Capital")
        self.assertEqual(len(book.sheets), 2)

    def test_timeline_stops_at_first_gap_and_leaves_foreign_series_untouched(self):
        book = FakeSpreadsheet()
        sheet = book.add_worksheet("net_worth_timeline", cols=6)
        sheet.values[(1, 1)], sheet.values[(1, 2)] = 900.003, "30 Sep 2026"
        # Unrelated helper rows below the series gap are never ours to touch.
        sheet.values[(4, 2)] = "legacy note"
        sheet.values[(5, 1)], sheet.values[(5, 2)] = 77.0, "31/12/2025"
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(sheet.cell(2, 1).value, 900.003)
        self.assertEqual(sheet.cell(2, 2).value, "04 Oct 2026")
        self.assertEqual(sheet.cell(4, 2).value, "legacy note")
        self.assertEqual(sheet.cell(5, 1).value, 77.0)

    def test_timeline_append_rejects_an_occupied_date_cell_right_after_the_series(self):
        from src.google_sheets.insights_writer import SheetConflictError

        book = FakeSpreadsheet()
        sheet = book.add_worksheet("net_worth_timeline", cols=6)
        sheet.values[(1, 1)], sheet.values[(1, 2)] = 900.003, "30 Sep 2026"
        sheet.values[(2, 2)] = "05 Oct 2026"
        with self.assertRaises(SheetConflictError):
            refresh_insights(book, current_snapshot(), config={})
        self.assertFalse(book.batch_updates)

    def test_stale_recorded_row_group_is_not_deleted_by_the_next_write(self):
        book = FakeSpreadsheet()
        data = current_snapshot()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        self.assertTrue(main.groups)
        # Recorded groups still live on the tab are pruned by their own range.
        refresh_insights(book, data, config={})
        self.assertIn(
            "deleteDimensionGroup",
            [next(iter(r)) for r in book.batch_updates[-1]["requests"]],
        )
        # Groups that vanished outside the generator are never deleted blindly.
        main.groups.clear()
        refresh_insights(book, data, config={})
        self.assertNotIn(
            "deleteDimensionGroup",
            [next(iter(r)) for r in book.batch_updates[-1]["requests"]],
        )
        # The current frame's groups are still established.
        self.assertTrue(main.groups)

    def test_live_row_group_metadata_parses_the_nested_api_shape(self):
        from src.google_sheets.insights_writer import _sheet_row_groups

        nested = {
            "rowGroups": [
                {
                    "range": {
                        "sheetId": 1,
                        "dimension": "ROWS",
                        "startIndex": 10,
                        "endIndex": 40,
                    },
                    "depth": 1,
                },
                {
                    "range": {
                        "sheetId": 1,
                        "dimension": "ROWS",
                        "startIndex": 10,
                        "endIndex": 40,
                    },
                    "depth": 2,
                },
            ]
        }
        self.assertEqual(_sheet_row_groups(nested), {(10, 40): 2})
        self.assertEqual(
            _sheet_row_groups({"rowGroups": [{"startRowIndex": 1, "endRowIndex": 5}]}),
            {(1, 5): 1},
        )
        self.assertIsNone(_sheet_row_groups({"properties": {}}))

    def test_same_date_rewrite_prunes_stacked_duplicate_groups(self):
        book = FakeSpreadsheet()
        data = current_snapshot()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        # The API nests another addDimensionGroup over the live span as depth 2.
        (start, end), _count = next(iter(main.groups.items()))
        main.groups[(start, end)] = 2
        refresh_insights(book, data, config={})
        deletions = [
            req["deleteDimensionGroup"]["range"]
            for req in book.batch_updates[-1]["requests"]
            if "deleteDimensionGroup" in req
        ]
        self.assertEqual(
            sorted((req["startIndex"], req["endIndex"]) for req in deletions),
            [(start, end), (start, end)],
        )
        self.assertEqual(main.groups[(start, end)], 1)

    def test_grid_shrink_moves_the_row_group_off_the_previous_span(self):
        book = FakeSpreadsheet()
        grown = current_snapshot()
        grown["IB_DATA"]["Precious Metals"].update({"SIM-SILVER": 60.0})
        refresh_insights(book, grown, config={})
        main = book.worksheet("04 Oct 2026")
        (old_start, old_end), _count = next(iter(main.groups.items()))
        refresh_insights(book, current_snapshot(), config={})
        remaining = dict(main.groups)
        self.assertEqual(len(remaining), 1)
        (new_start, new_end), count = next(iter(remaining.items()))
        self.assertEqual(count, 1)
        self.assertLess(new_end, old_end)
        # Rows the deleted group hid beyond the shorter span stay visible.
        self.assertNotIn(old_end - 1, main.hidden_rows)

    def test_adopted_replacement_removes_a_legacy_single_column_pnl_gradient(self):
        from src.google_sheets.insights_writer import preview_adoption

        book = FakeSpreadsheet()
        main = book.add_worksheet("04 Oct 2026")
        main.values[(1, 1)] = "legacy"
        main.conditional_formats.append(
            {
                "ranges": [
                    {
                        "sheetId": main.id,
                        "startRowIndex": 3,
                        "endRowIndex": 40,
                        "startColumnIndex": 5,
                        "endColumnIndex": 6,
                    }
                ],
                "gradientRule": {
                    "minpoint": {
                        "type": "NUMBER",
                        "value": "-0.3",
                        "color": {"red": 245 / 255, "green": 69 / 255, "blue": 69 / 255},
                    },
                    "midpoint": {
                        "type": "NUMBER",
                        "value": "0",
                        "color": {"red": 1, "green": 1, "blue": 1},
                    },
                    "maxpoint": {
                        "type": "NUMBER",
                        "value": "0.5",
                        "color": {"red": 46 / 255, "green": 204 / 255, "blue": 113 / 255},
                    },
                },
            }
        )
        approval = preview_adoption(main, [[0, main.row_count, 0, 12]])
        refresh_insights(
            book, current_snapshot(), config={}, adoptions={main.id: approval}
        )
        gradients = [r for r in main.conditional_formats if r.get("gradientRule")]
        self.assertEqual(len(gradients), 1)
        # The managed replacement spans both P&L columns, not one.
        self.assertGreater(len(gradients[0]["ranges"]), 1)

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
        main.values[(1, 16)] = "manual note"
        ids = [s.id for s in book.sheets]
        refresh_insights(book, current_snapshot(), config={})
        count = len(main.groups)
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(len(main.groups), count)
        self.assertEqual(main.cell(1, 16).value, "manual note")
        self.assertIn(main.cell(old_rows, 1).value, ("", None))
        self.assertEqual([s.id for s in book.sheets], ids)
        self.assertEqual(main.properties["frozenRowCount"], 2)
        self.assertGreater(main.basic_filter["range"]["startRowIndex"], 25)

    def test_legacy_timeline_dry_run_and_appending_past_the_last_grid_row(self):
        from copy import deepcopy

        book = FakeSpreadsheet()
        timeline = book.add_worksheet("net_worth_timeline", rows=1, cols=2)
        timeline.values.update({(1, 1): 750, (1, 2): "30 Sep 2026"})
        before = deepcopy(timeline.values)
        refresh_insights(book, current_snapshot(), config={}, dry_run=True)
        self.assertEqual(timeline.values, before)
        self.assertEqual(book.batch_updates, [])
        self.assertEqual(len(book.sheets), 1)
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual((timeline.row_count, timeline.col_count), (2, 2))
        self.assertEqual(timeline.values[(2, 2)], "04 Oct 2026")
        self.assertEqual(timeline.values[(1, 2)], "30 Sep 2026")

    def test_explicit_main_adoption_clears_only_reviewed_legacy_regions(self):
        from src.google_sheets.insights_writer import preview_adoption

        book = FakeSpreadsheet()
        main = book.add_worksheet("04 Oct 2026")
        main.values[(3, 8)] = "old total"
        main.values[(20, 12)] = "old income"
        main.values[(1, 13)] = "user note"
        approval = preview_adoption(main, [[0, 150, 0, 12]])
        refresh_insights(
            book, current_snapshot(), config={}, adoptions={main.id: approval}
        )
        self.assertEqual(main.cell(1, 13).value, "user note")
        self.assertIn(main.cell(20, 12).value, ("", None))
        self.assertEqual(main.cell(1, 8).value, 900.003)

    def test_legacy_timeline_preserves_other_columns_and_rejects_duplicate_dates(self):
        from src.google_sheets.insights_writer import SheetConflictError

        for duplicate in (False, True):
            book = FakeSpreadsheet()
            sheet = book.add_worksheet("net_worth_timeline")
            sheet.values[(1, 1)], sheet.values[(1, 2)] = 750, "30 Jun 2026"
            if duplicate:
                sheet.values[(2, 1)], sheet.values[(2, 2)] = 800, "30 Jun 2026"
            else:
                sheet.values[(1, 5)] = "user formula"
            if duplicate:
                with self.assertRaises(SheetConflictError):
                    refresh_insights(book, current_snapshot(), config={})
                self.assertFalse(book.batch_updates)
                self.assertEqual(len(book.sheets), 1)
            else:
                refresh_insights(book, current_snapshot(), config={})
                self.assertEqual(sheet.values[(1, 5)], "user formula")

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
        summary = next(block for block in tab.blocks if block.name == "summary")
        rows = list(summary.rows)
        row = list(rows[1])
        row[1] = CellValue(None, "money")
        rows[1] = tuple(row)
        tab = replace(
            tab,
            blocks=tuple(
                replace(block, rows=tuple(rows)) if block is summary else block
                for block in tab.blocks
            ),
        )
        book = FakeSpreadsheet()
        write_portfolio_snapshot(book, tab, "2026-10-04", 900.003)
        self.assertEqual(book.worksheet("04 Oct 2026").cell(2, 2).value, "Unavailable")


    def test_legacy_timeline_ignores_old_helper_metadata_without_clearing_it(self):
        import json
        from src.google_sheets.insights_writer import MARKER_COLUMN, OWNERSHIP_MARKER

        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        timeline = book.worksheet("net_worth_timeline")
        timeline.values[(1, 3)] = "=A1/2"
        timeline.col_count = 29
        timeline.values[(1, MARKER_COLUMN + 1)] = OWNERSHIP_MARKER
        metadata = json.dumps({"role": "timeline", "helper_ranges": [[0, 2, 2, 6]]})
        timeline.values[(2, MARKER_COLUMN + 1)] = metadata
        refresh_insights(book, current_snapshot(), config={})
        self.assertEqual(timeline.values[(2, MARKER_COLUMN + 1)], metadata)
        self.assertEqual(timeline.values[(1, 3)], "=A1/2")

    def test_multiline_rows_get_the_twoline_header_height(self):
        from datetime import date

        from src.google_sheets.insights_tables import build_portfolio_tab
        from src.google_sheets.insights_writer import write_portfolio_snapshot
        from tests.fixtures_insights import previous_snapshot

        tab = build_portfolio_tab(
            current_snapshot(),
            previous_snapshot=previous_snapshot(),
            current_date=date(2026, 10, 4),
        )
        book = FakeSpreadsheet()
        write_portfolio_snapshot(
            book, tab, "2026-10-04", current_snapshot()["TOTAL_ASSETS"]
        )
        main = book.worksheet("04 Oct 2026")
        balance_row = next(
            row
            for (row, column), value in main.values.items()
            if column == 7
            and isinstance(value, str)
            and value.startswith("Balance change")
        )
        heights = {}
        for body in book.batch_updates:
            for request in body["requests"]:
                if "updateDimensionProperties" not in request:
                    continue
                req = request["updateDimensionProperties"]
                rng, props = req.get("range", {}), req.get("properties", {})
                if rng.get("dimension", "ROWS") != "ROWS":
                    continue
                if rng.get("sheetId") != main.id or "pixelSize" not in props:
                    continue
                for row in range(rng["startIndex"], rng["endIndex"]):
                    heights[row] = props["pixelSize"]
        # The two-line label is explicit 36, same as the two-line header above.
        self.assertEqual(heights.get(balance_row - 1), 36)
        self.assertEqual(heights.get(0), 42)
        self.assertEqual(heights.get(1), 36)
