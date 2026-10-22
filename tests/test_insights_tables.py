import unittest
from src.google_sheets.insights_cells import CellValue, render_blocks
from src.google_sheets.insights_tables import (
    build_portfolio_tab,
    LBL_IB_RETURN,
    LBL_UNREALIZED_PNL,
    LBL_ESTIMATED_MONTHLY_INCOME,
)
from tests.fixtures_insights import current_snapshot, previous_snapshot


class InsightsTablesTests(unittest.TestCase):
    def test_fire_summary_uses_the_portfolio_headline_without_a_duplicate_balance(self):
        data = current_snapshot()
        data["FIXED_INCOME_DATA"]["group_weighted_interest"]["Bonds"] = (225, 0.04)
        blocks = {block.name: block for block in build_portfolio_tab(data).blocks}
        summary = blocks["summary"].rows
        self.assertEqual([row[0] for row in summary[:2]], ["FIRE progress", "Target"])
        self.assertNotIn("Eligible assets", [row[0] for row in summary])
        total = blocks["compact_allocation"].rows[0][1].value
        self.assertEqual(summary[0][1].value, total / summary[1][1].value)
        detail = blocks["summary_fire"].rows
        self.assertEqual(detail[2][0], "Portfolio value")
        self.assertEqual(detail[2][1].value, total)
        self.assertNotIn("eligibility", blocks)

    def test_monitor_layout_uses_clear_labels_without_changing_values(self):
        data = current_snapshot()
        tab = build_portfolio_tab(data)
        blocks = {block.name: block for block in tab.blocks}
        self.assertEqual(
            tab.column_widths,
            (190, 120, 100, 190, 110, 150, 150, 160, 100, 28, 220, 115),
        )
        self.assertEqual(blocks["summary"].rows[0][0], "FIRE progress")
        self.assertEqual(blocks["compact_allocation"].rows[0][0], "Portfolio value")
        self.assertEqual(
            blocks["compact_allocation"].rows[0][1].value, data["TOTAL_ASSETS"]
        )
        self.assertEqual(blocks["holdings"].rows[1][1], "Value")
        self.assertEqual(blocks["compact_allocation"].rows[1][1], "Value")
        self.assertEqual(blocks["compact_income"].rows[0][0], "Estimated income")
        self.assertEqual(blocks["compact_income"].rows[-2][0], "Monthly average")
        self.assertEqual(blocks["compact_income"].rows[-1][0], "Annual estimate")
        data["IB_DATA"].pop("Bonds")
        partial = {block.name: block for block in build_portfolio_tab(data).blocks}
        self.assertEqual(
            partial["compact_allocation"].rows[0][0], "Portfolio value (partial)"
        )

    def test_group_totals_do_not_repeat_identical_single_position_labels(self):
        tab = build_portfolio_tab(current_snapshot())
        rows = next(block.rows for block in tab.blocks if block.name == "holdings")
        for category in ("Crypto Lending", "P2P Lending", "Other Bets"):
            self.assertEqual(sum(row[0] == category for row in rows), 1)

    def test_malformed_ib_bucket_retains_the_existing_missing_data_behavior(self):
        data = current_snapshot()
        data["IB_DATA"] = "missing"
        tab = build_portfolio_tab(data)
        self.assertTrue(tab.blocks)

    def test_cached_status_does_not_move_financial_cells(self):
        current = current_snapshot()
        cached = current_snapshot()
        cached["DATA_METADATA"]["source"] = "cached_snapshot"
        live_grid, _, live_ranges = render_blocks(build_portfolio_tab(current).blocks)
        cached_grid, _, cached_ranges = render_blocks(
            build_portfolio_tab(cached).blocks
        )
        numeric = lambda grid: {
            (r, c): value
            for r, row in enumerate(grid)
            for c, value in enumerate(row)
            if isinstance(value, (int, float))
        }
        self.assertEqual(numeric(live_grid), numeric(cached_grid))
        self.assertEqual(live_ranges, cached_ranges)

    def test_default_view_is_a_compact_original_style_portfolio(self):
        tab = build_portfolio_tab(
            current_snapshot(), previous_snapshot=previous_snapshot()
        )
        grid, typed, ranges = render_blocks(tab.blocks)
        self.assertEqual(ranges["holdings"][0], 0)
        self.assertEqual(ranges["holdings"][2:], (3, 6))
        self.assertEqual(ranges["summary"][0], 0)
        self.assertEqual(ranges["summary"][2], 0)
        self.assertEqual(ranges["performance"][2], 0)
        self.assertEqual(ranges["compact_allocation"][:3], (0, 13, 6))
        self.assertEqual(ranges["compact_income"][0], 0)
        self.assertEqual(ranges["compact_income"][2], 10)
        holdings = next(block for block in tab.blocks if block.name == "holdings")
        self.assertEqual(len(holdings.rows[1]), 3)
        labels = [row[0] for row in holdings.rows]
        self.assertLess(labels.index("Bonds"), labels.index("China Stocks"))
        self.assertLess(labels.index("China Stocks"), labels.index("Stocks"))
        self.assertEqual(len(tab.row_groups), 1)
        block, start, end = tab.row_groups[0]
        hidden_start = ranges[block][0] + start
        self.assertLessEqual(hidden_start, 32)
        visible = [str(value) for row in grid[:hidden_start] for value in row]
        for noise in (
            "Unknown",
            "Unavailable",
            "Unconfigured",
            "Attribution status",
            "Definitions and coverage",
            "Manual estimate",
        ):
            self.assertNotIn(noise, visible)
        self.assertEqual(tab.freeze_rows, 2)
        self.assertEqual(tab.freeze_columns, 4)
        bond_row = next(r for r, row in enumerate(grid) if row[3] == "SIM-BOND")
        self.assertEqual(grid[bond_row][4], 200)

    def test_holdings_filter_sits_below_the_summary_panels(self):
        tab = build_portfolio_tab(current_snapshot())
        _, _, ranges = render_blocks(tab.blocks)
        self.assertGreater(
            ranges[tab.filter_block_name][0], ranges["compact_income"][1]
        )

    def test_main_snapshot_contains_all_sections_and_compact_holdings_header(self):
        tab = build_portfolio_tab(current_snapshot(), current_date="2026-10-04")
        grid, typed, ranges = render_blocks(tab.blocks)
        self.assertEqual(tab.title, "04 Oct 2026")
        self.assertEqual(ranges["holdings"][0], 0)
        self.assertEqual(tab.freeze_rows, 2)
        self.assertEqual(tab.freeze_columns, 4)
        self.assertEqual(tab.filter_block_name, "holding_details")
        for section in (
            "allocation",
            "comparison",
            "income",
            "receipts",
            "liquidity",
            "provider",
            "trading_currency",
            "underlying_geography",
        ):
            self.assertIn(section, ranges)
        values = [
            value.value if isinstance(value, CellValue) else value
            for block in tab.blocks
            for row in block.rows
            for value in row
        ]
        for label in (LBL_IB_RETURN, LBL_UNREALIZED_PNL, LBL_ESTIMATED_MONTHLY_INCOME):
            self.assertIn(label, values)
        self.assertNotIn("CRYPTO_DATA", values)
        self.assertTrue(any(cell.kind == "link" for cell in typed.values()))
        self.assertEqual(tab.row_groups[0][0], "details")
        self.assertGreater(ranges["methodology"][0], ranges["details"][0])

    def test_required_labels_are_verbatim(self):
        self.assertEqual(LBL_IB_RETURN, "IB return - YTD - TWR")
        self.assertEqual(LBL_UNREALIZED_PNL, "Unrealized P&L vs cost")
        self.assertEqual(
            LBL_ESTIMATED_MONTHLY_INCOME,
            "Estimated investment income - monthly average",
        )

    def test_missing_date_cannot_generate_a_tab(self):
        with self.assertRaises(ValueError):
            build_portfolio_tab({"TOTAL_ASSETS": 100})

    def test_other_bets_components_do_not_replace_or_duplicate_the_subtotal(self):
        data = current_snapshot()
        data["OTHER_ASSETS"].update({"Equipment": 25.0, "Other Bets": 100.0})
        tab = build_portfolio_tab(data)
        rows = next(block.rows for block in tab.blocks if block.name == "other_bets")
        self.assertEqual(rows[2][0], "Equipment")
        self.assertIn("not added", rows[2][2])
        self.assertEqual(rows[3][1].value, 100)

    def test_allocation_and_fire_have_bars_and_keep_income_principal_separate(self):
        data = current_snapshot()
        data["FIXED_INCOME_DATA"]["group_weighted_interest"]["Bonds"] = (225, 0.04)
        tab = build_portfolio_tab(data)
        allocation = next(block for block in tab.blocks if block.name == "allocation")
        self.assertIn("Allocation bar", allocation.rows[1])
        income = next(block for block in tab.blocks if block.name == "income")
        bonds = next(row for row in income.rows if row[0] == "Bonds")
        self.assertEqual(bonds[1].value, 225)
        fire = next(block for block in tab.blocks if block.name == "summary_fire")
        self.assertTrue(
            any(
                isinstance(value, CellValue) and value.kind == "formula"
                for row in fire.rows
                for value in row
            )
        )

    def test_saved_benchmark_values_and_measurement_dates_remain_visible(self):
        data = current_snapshot()
        data["IB_PERFORMANCE"].update(
            start_date="2026-01-01", end_date="2026-10-04", currency="USD"
        )
        data["INDEX_PERFORMANCE"] = {
            "SP500": {
                "name": "S&P 500",
                "rate_of_return_pct": 12.5,
                "start_date": "2026-01-01",
                "end_date": "2026-10-04",
                "currency": "USD",
            }
        }
        tab = build_portfolio_tab(data)
        blocks = {block.name: block for block in tab.blocks}
        self.assertIn("benchmarks", blocks)
        row = blocks["benchmarks"].rows[2]
        self.assertEqual(row[0], "S&P 500")
        self.assertEqual(row[1].value, 0.125)
        self.assertEqual(row[4], "USD")
        coverage = next(
            row for row in blocks["methodology"].rows if row[0] == "IB return coverage"
        )
        self.assertEqual(str(coverage[2].value), "2026-01-01")
        self.assertEqual(str(coverage[4].value), "2026-10-04")
        self.assertEqual(coverage[6], "USD")
