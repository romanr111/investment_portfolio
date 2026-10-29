import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from analytics.dalio_holy_grail import DalioHolyGrailAnalyzer, format_holy_grail_cli_lines


def build_synthetic_history() -> pd.DataFrame:
    dates = pd.date_range("2021-01-31", periods=60, freq=pd.offsets.MonthEnd())
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


def build_canonical_factor_returns(
    start: str = "2021-01-31", periods: int = 60
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq=pd.offsets.MonthEnd())
    rows = []
    for idx, date in enumerate(dates):
        rows.append(
            {
                "date": date,
                "growth": 0.01 * math.sin(idx / 4.0) + 0.003 * math.cos(idx / 7.0),
                "inflation": 0.008 * math.cos(idx / 5.0) + 0.002 * math.sin(idx / 9.0),
                "real_rates": -0.006 * math.sin(idx / 6.0) + 0.002 * math.cos(idx / 3.0),
                "credit_liquidity": 0.009 * math.sin(idx / 8.0 + 0.2),
            }
        )
    return pd.DataFrame(rows)


def build_factor_linear_history(periods: int = 60) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    factor_df = build_canonical_factor_returns(periods=periods)
    dates = pd.to_datetime(factor_df["date"])
    factor_cols = ["growth", "inflation", "real_rates", "credit_liquidity"]

    specs = {
        "A": {
            "alpha": 0.0010,
            "beta": np.array([0.9, 0.2, -0.1, 0.3], dtype=float),
            "noise": 0.0003,
        },
        "B": {
            "alpha": 0.0005,
            "beta": np.array([0.2, 0.8, 0.1, -0.2], dtype=float),
            "noise": 0.0004,
        },
        "C": {
            "alpha": -0.0002,
            "beta": np.array([-0.1, 0.3, 0.9, 0.4], dtype=float),
            "noise": 0.0005,
        },
    }
    values = {asset: 1000.0 for asset in specs}
    rows = []
    for idx, date in enumerate(dates):
        factor_vec = factor_df.loc[idx, factor_cols].values.astype(float)
        for asset, params in specs.items():
            deterministic = params["alpha"] + float(params["beta"] @ factor_vec)
            noise = params["noise"] * math.sin((idx + 1) * (len(asset) + 1))
            asset_return = deterministic + noise
            values[asset] = values[asset] * (1.0 + asset_return)
            rows.append(
                {
                    "date": date,
                    "asset_bucket": asset,
                    "market_value": values[asset],
                    "return_pct": asset_return,
                    "currency": "USD",
                }
            )
    return pd.DataFrame(rows), factor_df, specs


def build_daily_history(start: str = "2024-01-01", periods: int = 320) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    values = {"Stocks": 1000.0, "Bonds": 1000.0, "Cash": 1000.0}
    rows = []
    for idx, date in enumerate(dates):
        returns = {
            "Stocks": 0.0006 + 0.004 * math.sin(idx / 9.0),
            "Bonds": 0.0002 + 0.0015 * math.cos(idx / 13.0),
            "Cash": 0.00005,
        }
        for bucket, bucket_return in returns.items():
            values[bucket] = values[bucket] * (1.0 + bucket_return)
            rows.append(
                {
                    "date": date,
                    "asset_bucket": bucket,
                    "market_value": values[bucket],
                    "return_pct": bucket_return,
                    "currency": "USD",
                }
            )
    return pd.DataFrame(rows)


class DalioHolyGrailAnalyzerTest(unittest.TestCase):
    # Cache the default-config run_analysis result across tests so the
    # ~2s analysis runs once per test session instead of once per test.
    _cached_history = None
    _cached_analyzer = None
    _cached_result = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._cached_history = build_synthetic_history()
        cls._cached_analyzer = DalioHolyGrailAnalyzer(cls._cached_history)
        cls._cached_result = cls._cached_analyzer.run_analysis()

    def setUp(self) -> None:
        self.history = self._cached_history
        self.analyzer = self._cached_analyzer

    def _run(self):
        """Return the cached default-config analysis result."""
        return self._cached_result

    def test_risk_contributions_sum_to_portfolio_volatility(self) -> None:
        result = self._run()
        rc = result.risk_contribution_by_bucket
        portfolio_volatility = float(rc["portfolio_volatility"].iloc[0])

        self.assertAlmostEqual(
            float(rc["risk_contribution"].sum()), portfolio_volatility, places=10
        )

    def test_increasing_crypto_weight_raises_risk_contribution_faster_than_weight(self) -> None:
        baseline_result = self._run()
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
        result = self._run()
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

    def test_layer_b_rolling_ols_recovers_known_betas(self) -> None:
        history, factor_df, specs = build_factor_linear_history(periods=72)
        analyzer = DalioHolyGrailAnalyzer(
            history,
            factor_returns=factor_df,
            min_history_months=1,
            min_covariance_observations=12,
            scenario_shocks={"s": {"A": 0.0, "B": 0.0, "C": 0.0}},
            factor_map={
                "A": "Growth/Risk-On",
                "B": "Inflation Hedge",
                "C": "Deflation/Risk-Off",
            },
        )
        result = analyzer.run_analysis()
        latest = result.factor_betas_by_bucket_rolling.sort_values("date").iloc[-3:]
        beta_a = latest.loc[latest["asset_bucket"] == "A"].iloc[0]

        self.assertAlmostEqual(float(beta_a["beta_growth"]), float(specs["A"]["beta"][0]), delta=0.15)
        self.assertAlmostEqual(
            float(beta_a["beta_inflation"]), float(specs["A"]["beta"][1]), delta=0.15
        )
        self.assertAlmostEqual(
            float(beta_a["beta_real_rates"]), float(specs["A"]["beta"][2]), delta=0.15
        )
        self.assertAlmostEqual(
            float(beta_a["beta_credit_liquidity"]), float(specs["A"]["beta"][3]), delta=0.15
        )

    def test_holy_grail_corr_collapse_flag_triggers_for_stress_windows(self) -> None:
        dates = pd.date_range("2018-01-31", periods=72, freq=pd.offsets.MonthEnd())
        assets = ["A", "B", "C", "D"]
        values = {asset: 100.0 for asset in assets}
        rows = []
        for idx, date in enumerate(dates):
            if idx < 60:
                base_returns = {
                    "A": 0.010 * math.sin(idx / 2.3),
                    "B": 0.009 * math.cos(idx / 3.7 + 0.4),
                    "C": 0.011 * math.sin(idx / 4.1 + 0.7),
                    "D": 0.008 * math.cos(idx / 5.3 + 0.2),
                }
            else:
                common = 0.09 * math.sin(idx / 1.5)
                base_returns = {
                    "A": common + 0.001 * math.sin(idx),
                    "B": common + 0.001 * math.cos(idx),
                    "C": common + 0.001 * math.sin(idx / 2.0),
                    "D": common + 0.001 * math.cos(idx / 2.0),
                }

            for asset in assets:
                asset_return = base_returns[asset]
                values[asset] = values[asset] * (1.0 + asset_return)
                rows.append(
                    {
                        "date": date,
                        "asset_bucket": asset,
                        "market_value": values[asset],
                        "return_pct": asset_return,
                        "currency": "USD",
                    }
                )

        dataset = pd.DataFrame(rows)
        analyzer = DalioHolyGrailAnalyzer(
            dataset,
            min_history_months=1,
            min_covariance_observations=12,
            factor_map={asset: "Growth/Risk-On" for asset in assets},
            scenario_shocks={"s": {asset: 0.0 for asset in assets}},
        )
        result = analyzer.run_analysis()

        self.assertIn("CORR_COLLAPSE_IN_STRESS", result.holy_grail_red_flags["code"].tolist())

    def test_data_quality_checks_pass_for_clean_monthly_dataset(self) -> None:
        result = self._run()
        checks = result.quality_checks.set_index("check")["passed"].to_dict()

        self.assertTrue(checks["no_missing_monthly_dates"])
        self.assertTrue(checks["consistent_frequency"])
        self.assertTrue(checks["weights_sum_to_100"])
        self.assertTrue(checks["minimum_history_window"])

    def test_correlation_matrix_is_symmetric_with_unity_diagonal(self) -> None:
        result = self._run()
        corr = result.correlation_matrix

        symmetry_gap = (corr - corr.T).abs().max().max()
        self.assertLess(symmetry_gap, 1e-12)
        for bucket in corr.columns:
            self.assertAlmostEqual(float(corr.loc[bucket, bucket]), 1.0, places=10)

    def test_covariance_window_uses_trailing_rows_for_sample_method(self) -> None:
        dates = pd.date_range("2025-01-01", periods=10, freq="D")
        returns_a = [0.01, 0.01, 0.02, 0.01, 0.0, -0.02, -0.01, -0.03, -0.01, -0.02]
        returns_b = [0.00, 0.01, 0.01, 0.02, 0.01, 0.03, 0.02, 0.04, 0.01, 0.02]
        values_a = 100.0
        values_b = 100.0
        rows = []
        for idx, date in enumerate(dates):
            values_a *= 1.0 + returns_a[idx]
            values_b *= 1.0 + returns_b[idx]
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "A",
                    "market_value": values_a,
                    "return_pct": returns_a[idx],
                    "currency": "USD",
                }
            )
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "B",
                    "market_value": values_b,
                    "return_pct": returns_b[idx],
                    "currency": "USD",
                }
            )

        result = DalioHolyGrailAnalyzer(
            pd.DataFrame(rows),
            min_history_months=1,
            min_covariance_observations=1,
            covariance_method="sample",
            covariance_window=5,
            scenario_shocks={"s": {"A": 0.0, "B": 0.0}},
            factor_map={"A": "Growth/Risk-On", "B": "Deflation/Risk-Off"},
        ).run_analysis()
        expected = pd.DataFrame({"A": returns_a[-5:], "B": returns_b[-5:]}).cov()
        self.assertAlmostEqual(
            float(result.covariance_matrix.loc["A", "B"]),
            float(expected.loc["A", "B"]),
            places=12,
        )
        self.assertEqual(int(result.management_rules["covariance_window_effective"]), 5)

    def test_low_coverage_assets_are_excluded_from_covariance(self) -> None:
        dates = pd.date_range("2024-01-31", periods=10, freq=pd.offsets.MonthEnd())
        rows = []
        value_a = 100.0
        value_b = 100.0
        for idx, date in enumerate(dates):
            value_a *= 1.0 + 0.01
            rows.append(
                {
                    "date": date,
                    "asset_bucket": "A",
                    "market_value": value_a,
                    "currency": "USD",
                }
            )
            if idx < 5:
                value_b *= 1.0 + 0.01
                rows.append(
                    {
                        "date": date,
                        "asset_bucket": "B",
                        "market_value": value_b,
                        "currency": "USD",
                    }
                )

        result = DalioHolyGrailAnalyzer(
            pd.DataFrame(rows),
            min_history_months=1,
            min_covariance_observations=1,
            covariance_method="sample",
            min_asset_coverage_pct=80.0,
            scenario_shocks={"s": {"A": 0.0, "B": 0.0}},
            factor_map={"A": "Growth/Risk-On", "B": "Deflation/Risk-Off"},
        ).run_analysis()
        coverage = result.asset_coverage.set_index("asset_bucket")
        self.assertFalse(bool(coverage.loc["B", "included_for_covariance"]))
        self.assertIn("B", result.management_rules["assets_excluded_low_coverage"])
        rc = result.risk_contribution_by_bucket.set_index("asset_bucket")
        self.assertNotIn("B", rc.index)

    def test_tail_risk_metrics_are_present_and_ordered(self) -> None:
        result = self._run()
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

    def test_risk_contribution_incomplete_data_is_flagged(self) -> None:
        dates = pd.date_range("2021-01-31", periods=36, freq=pd.offsets.MonthEnd())
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

    def test_log_return_type_transforms_simple_returns(self) -> None:
        data = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Stocks",
                    "market_value": 1000,
                    "return_pct": 0.10,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Stocks",
                    "market_value": 1100,
                    "return_pct": 0.05,
                    "currency": "USD",
                },
                {
                    "date": "2025-01-31",
                    "asset_bucket": "Bonds",
                    "market_value": 1000,
                    "return_pct": 0.02,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "Bonds",
                    "market_value": 1020,
                    "return_pct": 0.01,
                    "currency": "USD",
                },
            ]
        )
        analyzer = DalioHolyGrailAnalyzer(
            data,
            min_history_months=1,
            min_covariance_observations=1,
            return_type="log",
            scenario_shocks={"s": {"Stocks": 0.0, "Bonds": 0.0}},
        )
        normalized = analyzer._normalize_history()
        stocks_first = normalized.loc[
            (normalized["asset_bucket"] == "Stocks")
            & (normalized["date"] == pd.Timestamp("2025-01-31")),
            "return_pct",
        ].iloc[0]
        self.assertAlmostEqual(float(stocks_first), float(np.log1p(0.10)), places=12)

    def test_log_return_type_rejects_minus_one_simple_return(self) -> None:
        bad = pd.DataFrame(
            [
                {
                    "date": "2025-01-31",
                    "asset_bucket": "A",
                    "market_value": 100,
                    "return_pct": -1.0,
                    "currency": "USD",
                },
                {
                    "date": "2025-02-28",
                    "asset_bucket": "A",
                    "market_value": 100,
                    "return_pct": 0.01,
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
                    "asset_bucket": "B",
                    "market_value": 100,
                    "return_pct": 0.0,
                    "currency": "USD",
                },
            ]
        )
        with self.assertRaises(ValueError):
            DalioHolyGrailAnalyzer(
                bad,
                min_history_months=1,
                min_covariance_observations=1,
                return_type="log",
                scenario_shocks={"s": {"A": 0.0, "B": 0.0}},
                factor_map={"A": "Growth/Risk-On", "B": "Deflation/Risk-Off"},
            ).run_analysis()


if __name__ == "__main__":
    unittest.main()