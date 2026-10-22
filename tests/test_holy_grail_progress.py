"""Observable contracts for the portfolio's Holy Grail progress estimate."""
import importlib
import importlib.util
import unittest
import json
from copy import deepcopy

import numpy as np
import pandas as pd


def independent_history(count=15, months=60):
    rng = np.random.default_rng(731)
    blocks = []
    for length in ([months - 36, 36] if months > 36 else [months]):
        values = rng.normal(size=(length, count))
        values -= values.mean(axis=0)
        orthogonal, _ = np.linalg.qr(values)
        blocks.append(orthogonal * np.sqrt(length - 1) * 0.01)
    return pd.DataFrame(
        np.vstack(blocks),
        index=pd.date_range(end="2026-09-30", periods=months, freq="ME"),
        columns=[f"asset_{i}" for i in range(count)],
    )


def exposures(count=15, reviewed=True):
    return [
        {
            "id": f"asset_{i}", "series": f"asset_{i}", "value_usd": 100.0,
            "category": "Stocks", "kind": "direct", "weak_proxy": False,
            "qualification": {
                "status": "reviewed" if reviewed else "draft",
                "rationale": "Diversified productive investment after costs",
                "costs": "Fund and transaction fees included in the thesis",
                "principal_risks": "Market losses and permanent impairment",
                "reviewer": "Synthetic reviewer", "reviewed_at": "2026-09-30",
            },
        }
        for i in range(count)
    ]


class HolyGrailProgressTests(unittest.TestCase):
    def calculate(self, positions, history, **kwargs):
        self.assertIsNotNone(
            importlib.util.find_spec("analytics.holy_grail"),
            "The shared Holy Grail progress calculation is not implemented",
        )
        calculate = importlib.import_module("analytics.holy_grail").calculate_progress
        return calculate(
            positions, history, as_of_date="2026-09-30",
            total_assets=sum(row["value_usd"] for row in positions), **kwargs,
        )

    def test_fifteen_independent_reviewed_streams_reach_model_target(self):
        result = self.calculate(exposures(), independent_history())
        self.assertAlmostEqual(result["effective_streams"], 15.0)
        self.assertAlmostEqual(result["estimated_progress_pct"], 100.0)
        self.assertTrue(result["target_achieved"])
        self.assertEqual(result["as_of_date"], "2026-09-30")
        self.assertEqual(result["coverage"]["direct_pct"], 100.0)

    def test_twenty_independent_streams_keep_the_actual_count(self):
        result = self.calculate(exposures(20), independent_history(20))
        self.assertAlmostEqual(result["effective_streams"], 20)
        self.assertEqual(result["estimated_progress_pct"], 100)
        self.assertTrue(result["target_achieved"])

    def test_account_splitting_does_not_change_progress(self):
        positions = exposures(2)
        positions[0]["value_usd"] = 900
        history = independent_history(2)
        expected = self.calculate(positions, history)
        split = [dict(positions[0], id=f"account_{i}", value_usd=9) for i in range(100)] + [positions[1]]
        actual = self.calculate(split, history)
        self.assertAlmostEqual(actual["effective_streams"], expected["effective_streams"])
        self.assertLess(actual["effective_streams"], 1.1)

    def test_unreviewed_and_weak_proxy_cannot_confirm_target(self):
        for change, reason in [
            ({"qualification": {"status": "draft"}}, "qualification_pending"),
            ({"kind": "proxy", "weak_proxy": True}, "weak_proxy"),
        ]:
            with self.subTest(reason=reason):
                positions = exposures()
                positions[0].update(change)
                result = self.calculate(positions, independent_history())
                self.assertFalse(result["target_achieved"])
                self.assertIn(reason, result["constraints"])
                self.assertAlmostEqual(result["effective_streams"], 15)

    def test_missing_position_remains_in_portfolio_coverage(self):
        result = self.calculate(exposures(), independent_history().drop(columns="asset_0"))
        self.assertAlmostEqual(result["coverage"]["uncovered_pct"], 100 / 15)
        self.assertEqual(result["scope"], "covered_subset")
        self.assertFalse(result["target_achieved"])

    def test_short_history_is_provisional_or_unavailable(self):
        for months in (24, 36, 59):
            with self.subTest(months=months):
                result = self.calculate(exposures(2), independent_history(2, months))
                self.assertFalse(result["target_achieved"])
                self.assertIsNone(result["estimated_progress_pct"]) if months < 36 else self.assertIsNotNone(result["estimated_progress_pct"])

    def test_post_period_observations_do_not_change_the_result(self):
        history = independent_history()
        future = pd.DataFrame(100, index=[pd.Timestamp("2026-10-31")], columns=history.columns)
        a = self.calculate(exposures(), history)
        b = self.calculate(exposures(), pd.concat([history, future]))
        self.assertEqual(a["effective_streams"], b["effective_streams"])
        self.assertEqual(b["return_window_end"], "2026-09-30")

    def test_perfect_hedge_is_unavailable_and_json_safe(self):
        history = independent_history(2)
        history["asset_1"] = -history["asset_0"]
        result = self.calculate(exposures(2), history)
        self.assertIsNone(result["effective_streams"])
        self.assertIn("degenerate_covariance", result["constraints"])
        json.dumps(result, allow_nan=False)

    def test_empty_and_all_cash_do_not_report_diversification(self):
        from analytics.holy_grail import calculate_progress
        result = calculate_progress([], pd.DataFrame(), as_of_date="2026-09-30", total_assets=100, cash_value=100)
        self.assertEqual(result["effective_streams"], 0)
        self.assertEqual(result["estimated_progress_pct"], 0)
        self.assertFalse(result["target_achieved"])

    def test_leap_february_window_is_exactly_sixty_months(self):
        from analytics.holy_grail import calculate_progress
        history = independent_history(2)
        history.index = pd.date_range(end="2025-02-28", periods=60, freq="ME")
        earlier = history.iloc[[0]].copy()
        earlier.index = pd.to_datetime(["2020-02-29"])
        result = calculate_progress(exposures(2), pd.concat([earlier, history]), as_of_date="2025-02-28", total_assets=200)
        self.assertEqual(result["observation_count"], 60)
        self.assertEqual(result["return_window_start"], "2020-03-31")

    def test_nonfinite_exposure_returns_a_json_safe_unavailable_result(self):
        from analytics.holy_grail import calculate_progress
        position = exposures(1)
        position[0]["value_usd"] = float("nan")
        result = calculate_progress(position, independent_history(1), as_of_date="2026-09-30", total_assets=100)
        self.assertIsNone(result["effective_streams"])
        json.dumps(result, allow_nan=False)

    def test_borrowed_cash_cannot_confirm_an_unmodeled_leveraged_target(self):
        from analytics.holy_grail import calculate_progress
        result = calculate_progress(exposures(), independent_history(), as_of_date="2026-09-30",
                                    total_assets=750, cash_value=-750)
        self.assertFalse(result["target_achieved"])
        self.assertIsNone(result["effective_streams"])

    def test_recent_correlation_collapse_blocks_statistical_hundred_percent(self):
        history = independent_history(20)
        history.iloc[:24] *= 20
        common = history.iloc[-36:, 0].to_numpy()
        history.iloc[-36:] = common[:, None] + history.iloc[-36:].to_numpy() * 0.01
        result = self.calculate(exposures(20), history)
        self.assertGreaterEqual(result["effective_streams"], 15)
        self.assertEqual(result["estimated_progress_pct"], 100)
        self.assertLess(result["stability"]["ratio"], .75)
        self.assertIn("unstable_diversification", result["constraints"])
        self.assertFalse(result["target_achieved"])

    def test_shared_lending_proxy_counts_as_one_stream(self):
        positions = exposures(2)
        for index, position in enumerate(positions):
            position.update(id=f"lending_platform_{index}", series="asset_0", kind="proxy")
        result = self.calculate(positions, independent_history(2))
        self.assertAlmostEqual(result["effective_streams"], 1)
        self.assertAlmostEqual(result["coverage"]["proxy_pct"], 100)


if __name__ == "__main__":
    unittest.main()
