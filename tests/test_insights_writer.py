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

    def test_row_sizes_preserve_adjacent_data_and_automatic_warning_height(self):
        from src.google_sheets.insights_cells import render_blocks
        from src.google_sheets.insights_tables import build_portfolio_tab

        data = current_snapshot()
        data["DATA_METADATA"].update(source="cached_snapshot", age_seconds=900)
        grid, typed, ranges = render_blocks(build_portfolio_tab(data).blocks)
        book = FakeSpreadsheet()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        sizes = {}
        for request in book.batch_updates[-1]["requests"]:
            p = request.get("updateDimensionProperties", {})
            r = p.get("range", {})
            if (
                r.get("sheetId") == main.id
                and r.get("dimension") == "ROWS"
                and "pixelSize" in p.get("properties", {})
            ):
                for row in range(r["startIndex"], r["endIndex"]):
                    sizes[row] = p["properties"]["pixelSize"]
        self.assertEqual(sizes.get(0), 42)
        self.assertEqual(sizes.get(1), 36)
        bond_row = next(r for r, row in enumerate(grid) if row[3] == "SIM-BOND")
        self.assertEqual(sizes.get(bond_row), 24)
        warning = next(
            r
            for (r, c), v in typed.items()
            if v.kind == "status" and r < ranges["details"][0]
        )
        self.assertNotIn(warning, sizes)
        for row in range(2, ranges["details"][0]):
            empty = all(v in ("", None) for v in grid[row][:12])
            if empty:
                self.assertEqual(sizes.get(row), 12)
            elif sizes.get(row) == 12:
                self.fail("A separator shrank a row containing adjacent panel data")
        self.assertEqual(main.formats[(2, 5)]["horizontalAlignment"], "RIGHT")
        self.assertEqual(main.formats[(2, 9)]["horizontalAlignment"], "RIGHT")

    def test_compact_formats_preserve_numbers_and_leave_details_precise(self):
        from copy import deepcopy

        data = current_snapshot()
        data["TOTAL_ASSETS"] = 12345.678
        original = deepcopy(data)
        book = FakeSpreadsheet()
        refresh_insights(book, data, config={})
        main = book.worksheet("04 Oct 2026")
        self.assertEqual(data, original)
        self.assertEqual(main.values[(1, 8)], 12345.678)
        self.assertEqual(
            main.formats[(1, 8)]["numberFormat"]["pattern"], '"$"#,##0;-"$"#,##0;"$"0'
        )
        self.assertEqual(
            main.formats[(1, 2)]["numberFormat"]["pattern"], "0.0%;-0.0%;0.0%"
        )
        aaa_row = next(r for (r, c), v in main.values.items() if c == 4 and v == "AAA")
        self.assertEqual(main.values[(aaa_row, 6)], 0.0705)
        self.assertEqual(
            main.formats[(aaa_row, 6)]["numberFormat"]["pattern"], "+0.0%;-0.0%;0.0%"
        )
        date_row = next(
            r for (r, c), v in main.values.items() if c == 1 and v == "As of"
        )
        self.assertEqual(
            main.formats[(date_row, 2)]["numberFormat"]["pattern"], "dd mmm yyyy"
        )
        detail_row = next(
            r
            for (r, c), v in main.values.items()
            if c == 1 and v == "Synthetic Alpha (AAA)"
        )
        self.assertEqual(
            main.formats[(detail_row, 8)]["numberFormat"]["pattern"],
            "+0.00%;-0.00%;0.00%",
        )

    def test_summary_hierarchy_survives_refresh_with_large_portfolio_values(self):
        book = FakeSpreadsheet()
        data = current_snapshot()
        data["TOTAL_ASSETS"] = 12345678.90
        config = {"fire_target_usd": 1000}
        for _ in range(2):
            refresh_insights(book, data, config=config)
            main = book.worksheet("04 Oct 2026")
            self.assertEqual(main.values[(1, 8)], 12345678.90)
            self.assertEqual(main.formats[(1, 8)]["textFormat"]["fontSize"], 20)
            self.assertTrue(main.formats[(1, 8)]["textFormat"]["bold"])
            self.assertEqual(main.formats[(1, 2)]["textFormat"]["fontSize"], 16)
            for coord in ((1, 4), (1, 7), (1, 11)):
                self.assertEqual(main.formats[coord]["textFormat"]["fontSize"], 12)
            for coord in ((2, 4), (2, 7), (2, 11)):
                self.assertEqual(main.formats[coord]["horizontalAlignment"], "LEFT")
            for label, size, bold in (
                ("Monthly average", 14, True),
                ("Annual estimate", 11, False),
            ):
                row = next(
                    r
                    for (r, c), v in main.values.items()
                    if c == 11 and str(v).startswith(label)
                )
                self.assertEqual(main.formats[(row, 12)]["textFormat"]["bold"], bold)
                self.assertEqual(
                    main.formats[(row, 12)]["textFormat"]["fontSize"], size
                )
            for coord in ((1, 8), (1, 2), (2, 4), (3, 4), (4, 4)):
                self.assertEqual(
                    main.formats[coord]["textFormat"].get("fontFamily"), "Arial"
                )
            requests = book.batch_updates[-1]["requests"]
            row_sizes = [
                v["updateDimensionProperties"]
                for v in requests
                if "updateDimensionProperties" in v
                and v["updateDimensionProperties"]["range"].get("dimension") == "ROWS"
                and "pixelSize" in v["updateDimensionProperties"]["properties"]
            ]
            self.assertTrue(
                any(
                    v["range"]["startIndex"] == 0
                    and v["range"]["endIndex"] == 1
                    and v["properties"]["pixelSize"] == 42
                    for v in row_sizes
                )
            )
            self.assertEqual(len(main.conditional_formats), 1)

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

    def test_no_empty_return_gradient_ranges_for_empty_holdings(self):
        book = FakeSpreadsheet()
        refresh_insights(
            book, {"TOTAL_ASSETS": 0, "as_of_date": "2026-10-04"}, config={}
        )
        main = book.worksheet("04 Oct 2026")
        for rule in main.conditional_formats:
            for r in rule["ranges"]:
                self.assertLess(r["startRowIndex"], r["endRowIndex"])

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

    def test_compact_view_formats_levels_quietly_and_limits_filter_to_holdings(self):
        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        main = book.worksheet("04 Oct 2026")
        self.assertNotIn("+", main.formats[(1, 8)]["numberFormat"]["pattern"])
        self.assertNotIn("+", main.formats[(3, 9)]["numberFormat"]["pattern"])
        bond_row = next(
            r for (r, c), value in main.values.items() if c == 4 and value == "SIM-BOND"
        )
        self.assertNotIn(".", main.formats[(bond_row, 5)]["numberFormat"]["pattern"])
        self.assertEqual(main.basic_filter["range"]["endColumnIndex"], 8)
        self.assertGreater(main.basic_filter["range"]["startRowIndex"], 25)
        self.assertEqual(main.properties["frozenRowCount"], 2)
        self.assertEqual(len(main.groups), 1)
        self.assertTrue(
            any(
                request.get("repeatCell", {}).get("range", {}).get("startColumnIndex")
                == 6
                for request in book.batch_updates[-1]["requests"]
            )
        )

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

    def test_main_uses_wrapping_and_bounded_resize_for_readable_labels(self):
        book = FakeSpreadsheet()
        refresh_insights(book, current_snapshot(), config={})
        requests = book.batch_updates[0]["requests"]
        self.assertTrue(any("autoResizeDimensions" in request for request in requests))
        detail_value_width = next(
            request["updateDimensionProperties"]["properties"]["pixelSize"]
            for request in requests
            if request.get("updateDimensionProperties", {})
            .get("range", {})
            .get("dimension")
            == "COLUMNS"
            and request["updateDimensionProperties"]["range"]["startIndex"] == 2
        )
        self.assertGreaterEqual(detail_value_width, 100)
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
        full_row = next(
            r
            for (r, c), value in main.values.items()
            if c == 1 and value == "Synthetic Alpha (AAA)"
        )
        self.assertTrue(
            main.formats[(full_row, 6)]["numberFormat"]["pattern"].startswith("+")
        )
        self.assertEqual(
            main.formats[(full_row, 4)]["numberFormat"]["pattern"],
            "+0.00%;-0.00%;0.00%",
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
        main.values[(20, 12)] = "old income"
        main.values[(1, 13)] = "user note"
        approval = preview_adoption(main, [[0, 150, 0, 12]])
        refresh_insights(
            book, current_snapshot(), config={}, adoptions={main.id: approval}
        )
        self.assertEqual(main.cell(1, 13).value, "user note")
        self.assertIn(main.cell(20, 12).value, ("", None))
        self.assertEqual(main.cell(1, 8).value, 900.003)

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
