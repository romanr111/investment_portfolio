import unittest
from unittest import mock

from src.google_sheets import insights_tables as insights_tables_module
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

    def test_balance_change_total_row_is_emphasized(self):
        tab = build_portfolio_tab(
            current_snapshot(), previous_snapshot=previous_snapshot()
        )
        allocation = next(
            block for block in tab.blocks if block.name == "compact_allocation"
        )
        offset = next(
            index
            for index, row in enumerate(allocation.rows)
            if row[0].startswith("Balance change")
        )
        self.assertIn(("compact_allocation", offset), tab.emphasis_rows)
        # The label carries the comparison period so the delta reads unambiguous.
        self.assertIn("vs 30 Sep 2026", allocation.rows[offset][0])

    def test_compact_pnl_header_splits_across_two_lines(self):
        tab = build_portfolio_tab(current_snapshot())
        holdings = next(block for block in tab.blocks if block.name == "holdings")
        self.assertEqual(holdings.rows[1][2], "Unrealized P&L\nvs cost")

    def test_single_position_categories_show_their_symbol_rows(self):
        tab = build_portfolio_tab(current_snapshot())
        labels = [
            row[0]
            for row in next(
                block.rows for block in tab.blocks if block.name == "holdings"
            )
        ]
        self.assertIn("Cash", labels)
        self.assertNotIn("Cash total", labels)  # category-name echo is skipped
        self.assertIn("Commodities", labels)
        self.assertNotIn("Commodities total", labels)
        self.assertIn("AAA", labels)
        # The subtotal tint marks groups that render rows inside them only;
        # a lone category row is data and reads plain.
        emphasized = {
            offset for name, offset in tab.emphasis_rows if name == "holdings"
        }
        for index, row in enumerate(next(
            block.rows for block in tab.blocks if block.name == "holdings"
        )):
            with self.subTest(label=row[0]):
                if row[0] in ("Cash", "Commodities", "Crypto Lending", "P2P Lending"):
                    self.assertNotIn(index, emphasized)
                if row[0] == "Stocks":  # detail + tiny rows under the subtotal
                    self.assertIn(index, emphasized)

    def test_build_portfolio_tab_does_not_recompute_derivations(self):
        """build_portfolio_tab passes precomputed results to section builders."""
        calls = {name: 0 for name in (
            "snapshot_comparison",
            "liquidity_ladder",
            "income_breakdown",
            "fire_progress",
            "holdings_table",
            "concentration_views",
        )}
        originals = {
            name: getattr(insights_tables_module, name) for name in calls
        }

        def counting(name, original):
            def wrapper(*args, **kwargs):
                calls[name] += 1
                return original(*args, **kwargs)
            return wrapper

        with mock.patch.multiple(
            insights_tables_module,
            **{name: counting(name, original) for name, original in originals.items()},
        ):
            # The tab must still render with real content.
            tab = build_portfolio_tab(
                current_snapshot(), previous_snapshot=previous_snapshot()
            )
        self.assertTrue(tab.blocks)
        # Each O(data) derivation runs exactly once, inside build_portfolio_tab;
        # section builders reuse the results instead of recomputing.
        for name, count in calls.items():
            with self.subTest(derivation=name):
                self.assertEqual(count, 1, f"{name} ran {count} times, expected 1")


