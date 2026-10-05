import unittest

from src.google_sheets.insights_finance import (
    category_rows,
    concentration_views,
    fire_progress,
    income_breakdown,
    holdings_table,
    liquidity_ladder,
    source_statuses,
    snapshot_comparison,
    targets_and_deviations,
)
from tests.fixtures_insights import current_snapshot, previous_snapshot


class InsightsFinanceTests(unittest.TestCase):
    def test_category_rows_reconcile_and_use_total_assets_weights(self):
        rows = category_rows(current_snapshot())

        self.assertAlmostEqual(
            sum(row["value"] for row in rows if row["value"] is not None), 900.003
        )
        self.assertEqual(rows[0]["category"], "Stocks")
        self.assertEqual(rows[0]["value"], 200.003)
        self.assertAlmostEqual(rows[0]["weight"], 200.003 / 900.003)

    def test_snapshot_comparison_marks_new_positions_and_sums_balance_changes(self):
        comparison = snapshot_comparison(
            current_snapshot(),
            previous_snapshot(),
            current_date="2026-10-04",
            previous_date="2026-09-30",
        )

        by_category = {row["category"]: row for row in comparison["rows"]}
        self.assertEqual(by_category["Crypto Coins"]["state"], "new")
        self.assertEqual(by_category["Crypto Coins"]["change"], 50.0)
        self.assertAlmostEqual(by_category["Stocks"]["change"], -49.997)
        self.assertAlmostEqual(
            by_category["Stocks"]["change_pp"], -9.224059399885856, places=6
        )
        self.assertAlmostEqual(comparison["change_total"], 105.003)
        self.assertEqual(comparison["current_date"], "2026-10-04")
        self.assertEqual(comparison["previous_date"], "2026-09-30")
        self.assertEqual(comparison["interval_days"], 4)

    def test_snapshot_deltas_do_not_treat_incomplete_activity_or_transfers_as_profit(self):
        current = current_snapshot()
        current["ACTIVITY_DATA"] = {
            "net_external_contributions": 75.0,
            "internal_transfers": 100.0,
            "coverage": "partial",
        }
        comparison = snapshot_comparison(current, previous_snapshot())

        self.assertEqual(comparison["label"], "Balance change - not investment profit")
        self.assertEqual(
            comparison["attribution_state"],
            "Unavailable - complete reconciled activity data not supplied",
        )
        self.assertIsNone(comparison["external_contributions"])

    def test_missing_and_all_zero_category_totals_remain_unavailable(self):
        empty = {
            "TOTAL_ASSETS": 0,
            "IB_DATA": {"Total Stocks Value": 0, "Bonds": {}},
            "CRYPTO_DATA": {"Total_Crypto_Value": 0},
            "FIXED_INCOME_DATA": {"group_weighted_interest": {}},
            "CASH_DATA": {"Total": 0},
            "OTHER_ASSETS": {},
        }
        comparison = snapshot_comparison(empty, empty)

        self.assertIsNone(comparison["previous_total"])
        self.assertIsNone(comparison["current_total"])
        self.assertIsNone(category_rows({})[0]["value"])

    def test_partial_category_comparison_does_not_publish_a_partial_total(self):
        current = current_snapshot()
        current["IB_DATA"].pop("Bonds")

        comparison = snapshot_comparison(current, previous_snapshot())

        self.assertIsNone(comparison["change_total"])
        self.assertEqual(comparison["state"], "Incomplete")
        self.assertEqual(
            next(row for row in comparison["rows"] if row["category"] == "Bonds")["state"],
            "Incomplete",
        )

    def test_other_bets_subtotal_is_not_added_to_its_component_rows(self):
        data = current_snapshot()
        data["OTHER_ASSETS"].update({"Equipment": 25.0, "Other Bets": 100.0})

        values = {row["category"]: row["value"] for row in category_rows(data)}
        holdings = holdings_table(data)
        other_bets = [row for row in holdings["rows"] if row["category"] == "Other Bets"]

        self.assertEqual(values["Other Bets"], 100.0)
        self.assertEqual([row["symbol"] for row in other_bets], ["Other Bets"])

    def test_income_is_a_monthly_estimate_and_receipts_stay_unavailable(self):
        income = income_breakdown(current_snapshot())
        by_source = {row["source"]: row for row in income["items"]}

        self.assertEqual(by_source["Stocks"]["annual_income"], 5.0)
        self.assertEqual(by_source["Stocks"]["annual_rate"], 0.025)
        self.assertAlmostEqual(by_source["Stocks"]["monthly_average"], 5 / 12)
        self.assertEqual(by_source["Bonds"]["annual_income"], 8.0)
        self.assertEqual(by_source["Crypto Lending"]["annual_income"], 8.0)
        self.assertEqual(by_source["P2P Lending"]["annual_income"], 6.0)
        self.assertEqual(income["annual_income"], 27.0)
        self.assertEqual(income["receipts"]["state"], "Unavailable")
        self.assertIn("transaction", income["receipts"]["message"].lower())

    def test_holdings_keep_native_pnl_and_group_tiny_nonzero_values(self):
        holdings = holdings_table(current_snapshot(), tiny_threshold_usd=100)
        by_symbol = {row["symbol"]: row for row in holdings["rows"]}

        self.assertEqual(by_symbol["AAA"]["asset"], "Synthetic Alpha (AAA)")
        self.assertAlmostEqual(by_symbol["AAA"]["pct_total_assets"], 100 / 900.003)
        self.assertAlmostEqual(by_symbol["AAA"]["pct_ib_portfolio"], 100 / 450.003)
        self.assertEqual(by_symbol["AAA"]["unrealized_pnl_amount"], 7.05)
        self.assertEqual(by_symbol["AAA"]["pnl_currency"], "USD")
        self.assertAlmostEqual(by_symbol["AAA"]["pnl_pct"], 0.0705)
        self.assertEqual(by_symbol["BBB"]["pnl_currency"], "HKD")
        self.assertEqual(by_symbol["BBB"]["unrealized_pnl_amount"], 10.0)
        self.assertEqual(by_symbol["TINY"]["value_usd"], 0.003)
        self.assertIn("TINY", {row["symbol"] for row in holdings["tiny_rows"]})
        self.assertAlmostEqual(
            sum(row["value_usd"] for row in holdings["rows"]), 900.003
        )

    def test_liquidity_requires_explicit_classification_and_distinguishes_zero_liabilities(self):
        unknown = liquidity_ladder(current_snapshot(), {})
        self.assertIsNone(unknown["cash_available_now"])
        self.assertIsNone(unknown["runway_months"])
        self.assertEqual(unknown["liabilities_state"], "Unknown")
        self.assertIsNone(unknown["net_worth_after_known_liabilities"])

        configured = liquidity_ladder(
            current_snapshot(),
            {
                "cash_available_now_usd": 0,
                "essential_monthly_spending_usd": 2000,
                "liabilities_usd": 0,
            },
        )
        self.assertEqual(configured["cash_available_now"], 0)
        self.assertEqual(configured["runway_months"], 0)
        self.assertEqual(configured["liabilities_state"], "Confirmed zero")
        self.assertEqual(configured["net_worth_after_known_liabilities"], 900.003)

        invalid_spending = liquidity_ladder(
            current_snapshot(), {"cash_available_now_usd": 1000, "essential_monthly_spending_usd": 0}
        )
        self.assertIsNone(invalid_spending["runway_months"])

    def test_fire_progress_uses_saved_target_and_only_reports_income_coverage_with_spending(self):
        data = current_snapshot()
        progress = fire_progress(data, {})

        self.assertAlmostEqual(progress["eligible_value"], 900.003)
        self.assertEqual(progress["target"], 1000.0)
        self.assertAlmostEqual(progress["progress_fraction"], 0.900003)
        self.assertAlmostEqual(progress["remaining"], 99.997)
        self.assertEqual(
            progress["included_categories"],
            [row["category"] for row in category_rows(data)],
        )
        self.assertIsNone(progress["income_coverage_fraction"])

        with_spending = fire_progress(data, {"essential_monthly_spending_usd": 2000})
        self.assertAlmostEqual(with_spending["income_coverage_fraction"], 2.25 / 2000)

        unconfigured = fire_progress({"TOTAL_ASSETS": 100}, {})
        self.assertIsNone(unconfigured["target"])
        self.assertEqual(unconfigured["state"], "Target not configured")

    def test_fire_income_coverage_is_unavailable_when_any_income_source_is_incomplete(self):
        data = current_snapshot()
        data["FIXED_INCOME_DATA"].pop("stocks_principal_and_interest")
        data["FIXED_INCOME_DATA"].pop("stocks_yearly")

        progress = fire_progress(data, {"essential_monthly_spending_usd": 2000})

        self.assertIsNone(progress["income_coverage_fraction"])
        self.assertEqual(progress["income_coverage_state"], "Unavailable")

    def test_targets_remain_unconfigured_until_supplied_and_report_percentage_points(self):
        unconfigured = targets_and_deviations(current_snapshot(), {})
        self.assertIsNone(unconfigured[0]["target_weight"])
        self.assertIsNone(unconfigured[0]["deviation_pp"])
        self.assertEqual(unconfigured[0]["deviation_pp_basis"], "Target not configured")

        configured = targets_and_deviations(
            current_snapshot(), {"allocation_targets_pct": {"Stocks": 50}}
        )
        stocks = next(row for row in configured if row["category"] == "Stocks")
        self.assertEqual(stocks["target_weight"], 0.5)
        self.assertAlmostEqual(stocks["deviation_pp"], (200.003 / 900.003 - 0.5) * 100)

    def test_concentration_views_reconcile_and_keep_unknown_exposure_explicit(self):
        views = concentration_views(current_snapshot())

        self.assertAlmostEqual(views["total_value"], 900.003)
        for dimension in ("provider", "trading_currency", "underlying_geography"):
            self.assertAlmostEqual(
                sum(row["amount"] for row in views[dimension]), views["total_value"]
            )
            self.assertIn("Unknown", {row["category"] for row in views[dimension]})
            self.assertEqual(
                sum(row["category"] == "Unknown" for row in views[dimension]), 1
            )
        currencies = {row["category"] for row in views["trading_currency"]}
        self.assertIn("HKD", currencies)

    def test_source_status_preserves_machine_state_and_human_cache_age(self):
        live = source_statuses(current_snapshot())
        self.assertEqual(live["overall_key"], "Current")
        self.assertEqual(live["overall"], "Current")

        cached_data = current_snapshot()
        cached_data["DATA_METADATA"]["source"] = "cached_snapshot"
        cached_data["DATA_METADATA"]["age_seconds"] = 900
        cached = source_statuses(cached_data)
        self.assertEqual(cached["overall_key"], "Cached")
        self.assertEqual(cached["overall"], "Cached - data age 900s")
        self.assertEqual(source_statuses({})["overall_key"], "Unknown")


if __name__ == "__main__":
    unittest.main()
