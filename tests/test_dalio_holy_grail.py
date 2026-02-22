import math
import unittest

import pandas as pd

from analytics.dalio_holy_grail import DalioHolyGrailAnalyzer


def build_synthetic_history() -> pd.DataFrame:
    dates = pd.date_range("2021-01-31", periods=60, freq="ME")
    initial_values = {
        "Stocks": 67921.0,
        "Bonds": 35546.0,
        "Other Bets": 27615.0,
        "Crypto Lending": 18270.0,
        "Precious Metals": 9825.0,
        "Crypto Coins": 4481.0,
        "Commodities": 3447.0,
        "Cash": 2585.0,
        "P2P Lending": 2413.0,
    }

    values = dict(initial_values)
    rows = []
    for idx, date in enumerate(dates):
        growth_cycle = 0.008 + 0.015 * math.sin(idx / 3.0)
        inflation_cycle = 0.004 + 0.012 * math.cos(idx / 5.0)
        crypto_cycle = 0.015 + 0.060 * math.sin(idx / 4.0)

        returns = {
            "Stocks": growth_cycle + 0.003 * math.sin(idx / 11.0),
            "Bonds": -0.45 * growth_cycle + 0.006 * math.cos(idx / 7.0),
            "Other Bets": 1.15 * growth_cycle + 0.004 * math.cos(idx / 8.0),
            "Crypto Lending": 0.45 * crypto_cycle + 0.005 * math.cos(idx / 6.0),
            "Precious Metals": inflation_cycle + 0.003 * math.sin(idx / 9.0),
            "Crypto Coins": crypto_cycle + 0.012 * math.sin(idx / 2.0),
            "Commodities": 1.20 * inflation_cycle + 0.003 * math.cos(idx / 4.0),
            "Cash": 0.001 + 0.0002 * math.sin(idx / 10.0),
            "P2P Lending": 0.004 + 0.25 * growth_cycle,
        }

        for bucket, bucket_return in returns.items():
            values[bucket] = values[bucket] * (1.0 + bucket_return)
            rows.append(
                {
                    "date": date,
                    "asset_bucket": bucket,
                    "market_value": values[bucket],
                    "currency": "USD",
                }
            )

    return pd.DataFrame(rows)


class DalioHolyGrailAnalyzerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.history = build_synthetic_history()
        self.analyzer = DalioHolyGrailAnalyzer(self.history)

    def test_data_quality_checks_pass_for_clean_monthly_dataset(self) -> None:
        result = self.analyzer.run_analysis()
        checks = result.quality_checks.set_index("check")["passed"].to_dict()

        self.assertTrue(checks["no_missing_monthly_dates"])
        self.assertTrue(checks["consistent_frequency"])
        self.assertTrue(checks["weights_sum_to_100"])
        self.assertTrue(checks["minimum_history_window"])

    def test_correlation_matrix_is_symmetric_with_unity_diagonal(self) -> None:
        result = self.analyzer.run_analysis()
        corr = result.correlation_matrix

        symmetry_gap = (corr - corr.T).abs().max().max()
        self.assertLess(symmetry_gap, 1e-12)
        for bucket in corr.columns:
            self.assertAlmostEqual(float(corr.loc[bucket, bucket]), 1.0, places=10)

    def test_risk_contributions_sum_to_portfolio_volatility(self) -> None:
        result = self.analyzer.run_analysis()
        rc = result.risk_contribution_by_bucket
        portfolio_volatility = float(rc["portfolio_volatility"].iloc[0])

        self.assertAlmostEqual(
            float(rc["risk_contribution"].sum()), portfolio_volatility, places=10
        )

    def test_increasing_crypto_weight_raises_risk_contribution_faster_than_weight(self) -> None:
        baseline_result = self.analyzer.run_analysis()
        baseline_rc = baseline_result.risk_contribution_by_bucket.set_index("asset_bucket")

        adjusted_history = self.history.copy()
        adjusted_history.loc[
            adjusted_history["asset_bucket"] == "Crypto Coins", "market_value"
        ] *= 3.0
        adjusted_result = DalioHolyGrailAnalyzer(adjusted_history).run_analysis()
        adjusted_rc = adjusted_result.risk_contribution_by_bucket.set_index("asset_bucket")

        base_weight = float(baseline_rc.loc["Crypto Coins", "weight"])
        base_risk_pct = float(baseline_rc.loc["Crypto Coins", "risk_contribution_pct"])
        adjusted_weight = float(adjusted_rc.loc["Crypto Coins", "weight"])
        adjusted_risk_pct = float(adjusted_rc.loc["Crypto Coins", "risk_contribution_pct"])

        self.assertGreater(adjusted_weight, base_weight)
        self.assertGreater(adjusted_risk_pct, base_risk_pct)
        self.assertGreater(
            adjusted_risk_pct - base_risk_pct,
            adjusted_weight - base_weight,
        )

    def test_stress_scenarios_have_expected_economic_direction(self) -> None:
        result = self.analyzer.run_analysis()
        stress = result.stress_test_results.set_index("scenario")

        self.assertLess(float(stress.loc["credit_spread_recession", "portfolio_return_pct"]), 0.0)
        self.assertGreater(float(stress.loc["inflation_shock", "precious_metals_shock_pct"]), 0.0)
        self.assertGreater(float(stress.loc["inflation_shock", "commodities_shock_pct"]), 0.0)
        self.assertLess(float(stress.loc["inflation_shock", "bonds_shock_pct"]), 0.0)
        self.assertLess(
            float(stress.loc["crypto_drawdown", "portfolio_return_pct"]),
            float(stress.loc["rate_hike", "portfolio_return_pct"]),
        )

    def test_duplicate_rows_use_value_weighted_bucket_returns(self) -> None:
        duplicate_rows = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Stocks",
                    "market_value": 100,
                    "return_pct": 0.10,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Stocks",
                    "market_value": 900,
                    "return_pct": 0.00,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Stocks",
                    "market_value": 1010,
                    "return_pct": 0.01,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Bonds",
                    "market_value": 1000,
                    "return_pct": 0.01,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Bonds",
                    "market_value": 1010,
                    "return_pct": 0.01,
                    "currency": "USD",
                },
            ]
        )

        analyzer = DalioHolyGrailAnalyzer(duplicate_rows, min_history_months=1)
        normalized = analyzer._normalize_history()
        returns = analyzer._build_returns_matrix(normalized)

        self.assertAlmostEqual(float(returns.loc["2025-01-31", "Stocks"]), 0.01, places=10)

    def test_decimal_return_unit_rejects_percent_like_values(self) -> None:
        mixed_units = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Stocks",
                    "market_value": 1000,
                    "return_pct": 2.0,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Stocks",
                    "market_value": 1020,
                    "return_pct": 0.02,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Bonds",
                    "market_value": 1000,
                    "return_pct": 1.0,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Bonds",
                    "market_value": 1010,
                    "return_pct": 0.01,
                    "currency": "USD",
                },
            ]
        )

        with self.assertRaises(ValueError):
            DalioHolyGrailAnalyzer(
                mixed_units, min_history_months=1, return_unit="decimal"
            ).run_analysis()

    def test_missing_covariance_data_is_not_silently_zero_filled(self) -> None:
        sparse = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Stocks",
                    "market_value": 1000,
                    "return_pct": 0.02,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Stocks",
                    "market_value": 1010,
                    "return_pct": 0.01,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Bonds",
                    "market_value": 1000,
                    "return_pct": 0.01,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Bonds",
                    "market_value": 1002,
                    "return_pct": 0.002,
                    "currency": "USD",
                },
            ]
        )

        analyzer = DalioHolyGrailAnalyzer(
            sparse,
            min_history_months=1,
            min_covariance_observations=12,
        )
        result = analyzer.run_analysis()
        self.assertFalse(result.risk_contribution_by_bucket.empty)
        self.assertFalse(result.management_rules["risk_contribution_data_complete"])
        self.assertIsNone(result.management_rules["risk_contribution_breach_count"])

    def test_fx_history_is_date_aware(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Stocks",
                    "market_value": 1000,
                    "currency": "EUR",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Stocks",
                    "market_value": 1000,
                    "currency": "EUR",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Bonds",
                    "market_value": 1000,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Bonds",
                    "market_value": 1000,
                    "currency": "USD",
                },
            ]
        )
        fx_history = pd.DataFrame(
            [
                {"date": "2025-01-31", "currency": "EUR", "fx_rate_to_base": 1.10},
                {"date": "2025-02-28", "currency": "EUR", "fx_rate_to_base": 1.30},
            ]
        )

        analyzer = DalioHolyGrailAnalyzer(
            history,
            fx_history=fx_history,
            min_history_months=1,
        )
        normalized = analyzer._normalize_history()
        stocks_rows = normalized.loc[normalized["asset_bucket"] == "Stocks"].set_index("date")
        self.assertAlmostEqual(float(stocks_rows.loc["2025-01-31", "market_value_base"]), 1100.0)
        self.assertAlmostEqual(float(stocks_rows.loc["2025-02-28", "market_value_base"]), 1300.0)

    def test_stress_scenarios_require_full_bucket_coverage_by_default(self) -> None:
        custom_shocks = {
            "broken_scenario": {
                "Stocks": -0.1,
                "Bonds": 0.01,
            }
        }
        analyzer = DalioHolyGrailAnalyzer(
            self.history,
            scenario_shocks=custom_shocks,
        )

        with self.assertRaises(ValueError):
            analyzer.run_analysis()

    def test_unmapped_factor_buckets_raise_by_default(self) -> None:
        data = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Unknown Bucket",
                    "market_value": 1000,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Unknown Bucket",
                    "market_value": 1010,
                    "currency": "USD",
                },
            ]
        )
        analyzer = DalioHolyGrailAnalyzer(
            data,
            min_history_months=1,
            scenario_shocks={"s": {"Unknown Bucket": 0.0}},
        )
        with self.assertRaises(ValueError):
            analyzer.run_analysis()

    def test_tail_risk_metrics_are_present_and_ordered(self) -> None:
        result = self.analyzer.run_analysis()
        tail = result.tail_risk_metrics.iloc[0]

        self.assertLessEqual(float(tail["cvar_95_pct"]), float(tail["var_95_pct"]))
        self.assertLessEqual(float(tail["max_drawdown_pct"]), 0.0)
        self.assertGreater(int(tail["portfolio_return_observations"]), 0)

    def test_tail_risk_uses_lagged_weights(self) -> None:
        two_period = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "A",
                    "market_value": 100,
                    "return_pct": 0.0,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "B",
                    "market_value": 100,
                    "return_pct": 0.0,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "A",
                    "market_value": 200,
                    "return_pct": 1.0,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "B",
                    "market_value": 100,
                    "return_pct": 0.0,
                    "currency": "USD",
                },
            ]
        )
        analyzer = DalioHolyGrailAnalyzer(
            two_period,
            min_history_months=1,
            min_covariance_observations=1,
            scenario_shocks={"s": {"A": 0.0, "B": 0.0}},
            factor_map={"A": "Growth/Risk-On", "B": "Deflation/Risk-Off"},
        )
        result = analyzer.run_analysis()
        tail = result.tail_risk_metrics.iloc[0]

        self.assertEqual(int(tail["portfolio_return_observations"]), 1)
        self.assertAlmostEqual(float(tail["var_95_pct"]), 50.0, places=8)

    def test_confidence_flags_and_penalty_are_exposed(self) -> None:
        analyzer = DalioHolyGrailAnalyzer(self.history, min_pair_overlap=100)
        result = analyzer.run_analysis()

        self.assertTrue((result.pairwise_confidence["confidence_flag"] == "LOW").all())
        self.assertEqual(float(result.management_rules["data_quality_penalty_pct"]), 100.0)

    def test_ewma_covariance_method_is_supported(self) -> None:
        ewma_result = DalioHolyGrailAnalyzer(
            self.history,
            covariance_method="ewma",
            ewma_alpha=0.1,
        ).run_analysis()
        sample_result = DalioHolyGrailAnalyzer(
            self.history,
            covariance_method="sample",
        ).run_analysis()

        self.assertFalse(ewma_result.covariance_matrix.equals(sample_result.covariance_matrix))

    def test_risk_contribution_incomplete_data_is_flagged(self) -> None:
        dates = pd.date_range("2021-01-31", periods=36, freq="ME")
        rows = []
        old_value = 100.0
        cash_value = 200.0
        for date in dates:
            old_value *= 1.01
            cash_value *= 1.0001
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "Old",
                    "market_value": old_value,
                    "currency": "USD",
                }
            )
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "Cash",
                    "market_value": cash_value,
                    "currency": "USD",
                }
            )

        new_value = 1000.0
        for date in dates[-6:]:
            new_value *= 1.05
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "NewHuge",
                    "market_value": new_value,
                    "currency": "USD",
                }
            )

        analyzer = DalioHolyGrailAnalyzer(
            pd.DataFrame(rows),
            min_history_months=1,
            min_covariance_observations=12,
            scenario_shocks={"s": {"Old": 0.0, "Cash": 0.0, "NewHuge": 0.0}},
            factor_map={"Old": "Growth/Risk-On", "NewHuge": "Growth/Risk-On"},
        )
        result = analyzer.run_analysis()

        self.assertFalse(result.management_rules["risk_contribution_data_complete"])
        self.assertIsNone(result.management_rules["risk_contribution_breach_count"])
        self.assertGreater(float(result.management_rules["rc_excluded_weight_pct"]), 50.0)

    def test_short_and_netting_checks_fail_when_shorts_not_allowed(self) -> None:
        data = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Stocks",
                    "market_value": 100,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Short Hedge",
                    "market_value": -80,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Stocks",
                    "market_value": 105,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Short Hedge",
                    "market_value": -84,
                    "currency": "USD",
                },
            ]
        )
        analyzer = DalioHolyGrailAnalyzer(
            data,
            min_history_months=1,
            factor_map={"Short Hedge": "Growth/Risk-On"},
            scenario_shocks={"s": {"Stocks": 0.0, "Short Hedge": 0.0}},
            min_covariance_observations=1,
        )
        result = analyzer.run_analysis()
        checks = result.quality_checks.set_index("check")["passed"].to_dict()
        self.assertFalse(checks["short_exposure_policy"])
        self.assertFalse(checks["gross_leverage_limit"])
        self.assertFalse(checks["netting_risk_limit"])

    def test_factor_exposure_is_not_zero_filled_for_missing_rc_assets(self) -> None:
        dates = pd.date_range("2021-01-31", periods=36, freq="ME")
        rows = []
        old_value = 100.0
        cash_value = 200.0
        for date in dates:
            old_value *= 1.01
            cash_value *= 1.0001
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "Old",
                    "market_value": old_value,
                    "currency": "USD",
                }
            )
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "Cash",
                    "market_value": cash_value,
                    "currency": "USD",
                }
            )

        new_value = 1000.0
        for date in dates[-6:]:
            new_value *= 1.05
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "NewHuge",
                    "market_value": new_value,
                    "currency": "USD",
                }
            )

        analyzer = DalioHolyGrailAnalyzer(
            pd.DataFrame(rows),
            min_history_months=1,
            min_covariance_observations=12,
            scenario_shocks={"s": {"Old": 0.0, "Cash": 0.0, "NewHuge": 0.0}},
            factor_map={"Old": "Growth/Risk-On", "NewHuge": "Growth/Risk-On"},
        )
        result = analyzer.run_analysis()
        growth_factor = result.factor_exposure.set_index("factor").loc["Growth/Risk-On"]

        self.assertFalse(bool(growth_factor["risk_contribution_complete"]))
        self.assertGreater(float(growth_factor["unknown_rc_weight_pct"]), 0.0)
        self.assertTrue(pd.isna(growth_factor["risk_contribution_pct"]))

    def test_tail_risk_ignores_partial_asset_rows(self) -> None:
        data = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "A",
                    "market_value": 100,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "B",
                    "market_value": 100,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "A",
                    "market_value": 110,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "B",
                    "market_value": 100,
                    "currency": "USD",
                },
                {
                    "date": "2025-03-31",
                    "asset_bucket": "A",
                    "market_value": 121,
                    "currency": "USD",
                },
            ]
        )
        analyzer = DalioHolyGrailAnalyzer(
            data,
            min_history_months=1,
            min_covariance_observations=1,
            scenario_shocks={"s": {"A": 0.0, "B": 0.0}},
            factor_map={"A": "Growth/Risk-On", "B": "Deflation/Risk-Off"},
        )
        result = analyzer.run_analysis()
        tail = result.tail_risk_metrics.iloc[0]

        self.assertEqual(int(tail["portfolio_return_observations"]), 1)
        self.assertAlmostEqual(float(tail["tail_data_coverage_pct"]), 33.3333333, places=5)


if __name__ == "__main__":
    unittest.main()
