"""Tests for the auto quarterly report data layer extensions.

Covers:
- extract_metrics benchmark_ytd_pct (INDEX_PERFORMANCE.SP500) + income keys
- top_positions_by_weight (excludes bonds/BILLs/SPECIAL_ASSET_TICKERS)
- position_contributions (abs-desc sort, zero-skip)
- match_combined_snapshot tie-breaking by filename-embedded timestamp
"""

import json
import unittest
from pathlib import Path

from portfolio_yic_reports.auto.combined_loader import (
    extract_metrics,
    match_combined_snapshot,
)
from portfolio_yic_reports.auto.flex_xml_parser import parse_snapshot
from portfolio_yic_reports.auto.position_analyzer import (
    PositionAnalysis,
    position_contributions,
    top_positions_by_weight,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestExtractMetricsBenchmark(unittest.TestCase):
    def test_benchmark_ytd_pct_present(self):
        data = json.loads(
            (FIXTURES / "combined_data_2026-06-30_full.json").read_text()
        )
        m = extract_metrics(data)
        self.assertAlmostEqual(m["benchmark_ytd_pct"], 9.34, places=2)

    def test_benchmark_ytd_pct_missing_index_performance(self):
        data = json.loads(
            (FIXTURES / "combined_data_2026-06-30.json").read_text()
        )
        m = extract_metrics(data)
        self.assertIsNone(m["benchmark_ytd_pct"])

    def test_benchmark_ytd_pct_missing_sp500_key(self):
        data = {
            "as_of_date": "2026-06-30",
            "data": {"INDEX_PERFORMANCE": {"NASDAQ": {"rate_of_return_pct": 12.8}}},
        }
        m = extract_metrics(data)
        self.assertIsNone(m["benchmark_ytd_pct"])

    def test_benchmark_ytd_pct_none_rate(self):
        data = {
            "as_of_date": "2026-06-30",
            "data": {"INDEX_PERFORMANCE": {"SP500": {"rate_of_return_pct": None}}},
        }
        m = extract_metrics(data)
        self.assertIsNone(m["benchmark_ytd_pct"])

    def test_benchmark_nasdaq_ytd_pct_present(self):
        data = json.loads(
            (FIXTURES / "combined_data_2026-06-30_full.json").read_text()
        )
        m = extract_metrics(data)
        self.assertAlmostEqual(m["benchmark_nasdaq_ytd_pct"], 12.82, places=2)

    def test_benchmark_nasdaq_ytd_pct_missing_index_performance(self):
        data = json.loads(
            (FIXTURES / "combined_data_2026-06-30.json").read_text()
        )
        m = extract_metrics(data)
        self.assertIsNone(m["benchmark_nasdaq_ytd_pct"])

    def test_benchmark_nasdaq_ytd_pct_missing_nasdaq_key(self):
        data = {
            "as_of_date": "2026-06-30",
            "data": {"INDEX_PERFORMANCE": {"SP500": {"rate_of_return_pct": 9.34}}},
        }
        m = extract_metrics(data)
        self.assertIsNone(m["benchmark_nasdaq_ytd_pct"])


class TestExtractMetricsIncomeKeys(unittest.TestCase):
    def test_income_keys_from_full_fixture(self):
        data = json.loads(
            (FIXTURES / "combined_data_2026-06-30_full.json").read_text()
        )
        m = extract_metrics(data)
        self.assertEqual(m["income_total_yearly"], 5689)
        self.assertEqual(m["income_stocks_yearly"], 764)
        self.assertEqual(m["income_fixed_yearly"], 4925)

    def test_dividends_yearly_backcompat(self):
        data = json.loads(
            (FIXTURES / "combined_data_2026-06-30_full.json").read_text()
        )
        m = extract_metrics(data)
        self.assertEqual(m["dividends_yearly"], 5689)
        self.assertEqual(m["dividends_yearly"], m["income_total_yearly"])

    def test_income_keys_none_when_fixed_income_missing(self):
        data = {"as_of_date": "2026-06-30", "data": {}}
        m = extract_metrics(data)
        self.assertIsNone(m["income_total_yearly"])
        self.assertIsNone(m["income_stocks_yearly"])
        self.assertIsNone(m["income_fixed_yearly"])

    def test_existing_keys_unchanged(self):
        data = json.loads(
            (FIXTURES / "combined_data_2026-06-30_full.json").read_text()
        )
        m = extract_metrics(data)
        self.assertEqual(m["as_of_date"], "2026-06-30")
        self.assertEqual(m["twr"], -4.12)
        self.assertEqual(m["freedom_progress"], "31.56%")
        self.assertEqual(m["total_assets"], 157816)


class TestTopPositionsByWeight(unittest.TestCase):
    def setUp(self):
        self.snap = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_end.xml")
        )

    def test_returns_top_three_sorted_desc(self):
        top = top_positions_by_weight(self.snap, 3)
        self.assertEqual(len(top), 3)
        weights = [w for _, w in top]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_excludes_bills(self):
        top = top_positions_by_weight(self.snap, 23)
        symbols = {s for s, _ in top}
        for sym, rec in self.snap.positions.items():
            if rec.asset_category == "BILL":
                self.assertNotIn(sym, symbols)

    def test_excludes_special_asset_tickers(self):
        from portfolio_yic_reports.auto.config import SPECIAL_ASSET_TICKERS

        top = top_positions_by_weight(self.snap, 23)
        symbols = {s for s, _ in top}
        for ticker in SPECIAL_ASSET_TICKERS:
            self.assertNotIn(ticker, symbols)

    def test_excludes_bond_tickers(self):
        from portfolio_yic_reports.auto.config import BOND_TICKERS

        top = top_positions_by_weight(self.snap, 23)
        symbols = {s for s, _ in top}
        for ticker in BOND_TICKERS:
            if ticker in self.snap.positions:
                self.assertNotIn(ticker, symbols)

    def test_weights_sum_consistency(self):
        top = top_positions_by_weight(self.snap, 23)
        got_sum = sum(w for _, w in top)
        self.assertAlmostEqual(got_sum, 100.0, places=1)

    def test_top_is_brk_b(self):
        top = top_positions_by_weight(self.snap, 1)
        self.assertEqual(top[0][0], "BRK B")
        self.assertGreater(top[0][1], 10.0)


class TestPositionContributions(unittest.TestCase):
    def test_sorts_by_absolute_value_desc(self):
        analyses = [
            PositionAnalysis(
                symbol="A",
                activity="",
                avg_entry_price=0.0,
                avg_exit_price=0.0,
                weight=10.0,
                price_change_pct=5.0,
                is_special_asset=False,
                is_china_equity=False,
            ),
            PositionAnalysis(
                symbol="B",
                activity="",
                avg_entry_price=0.0,
                avg_exit_price=0.0,
                weight=20.0,
                price_change_pct=-3.0,
                is_special_asset=False,
                is_china_equity=False,
            ),
            PositionAnalysis(
                symbol="C",
                activity="",
                avg_entry_price=0.0,
                avg_exit_price=0.0,
                weight=5.0,
                price_change_pct=10.0,
                is_special_asset=False,
                is_china_equity=False,
            ),
        ]
        contribs = position_contributions(analyses)
        self.assertEqual([s for s, _ in contribs], ["B", "A", "C"])
        self.assertAlmostEqual(contribs[0][1], -0.6)
        self.assertAlmostEqual(contribs[1][1], 0.5)
        self.assertAlmostEqual(contribs[2][1], 0.5)
        abs_vals = [abs(c) for _, c in contribs]
        self.assertEqual(abs_vals, sorted(abs_vals, reverse=True))

    def test_skips_zero_price_change(self):
        analyses = [
            PositionAnalysis(
                symbol="A",
                activity="",
                avg_entry_price=0.0,
                avg_exit_price=0.0,
                weight=10.0,
                price_change_pct=0.0,
                is_special_asset=False,
                is_china_equity=False,
            ),
            PositionAnalysis(
                symbol="B",
                activity="",
                avg_entry_price=0.0,
                avg_exit_price=0.0,
                weight=20.0,
                price_change_pct=2.0,
                is_special_asset=False,
                is_china_equity=False,
            ),
        ]
        contribs = position_contributions(analyses)
        self.assertEqual([s for s, _ in contribs], ["B"])

    def test_skips_zero_weight(self):
        analyses = [
            PositionAnalysis(
                symbol="A",
                activity="",
                avg_entry_price=0.0,
                avg_exit_price=0.0,
                weight=0.0,
                price_change_pct=10.0,
                is_special_asset=False,
                is_china_equity=False,
            ),
            PositionAnalysis(
                symbol="B",
                activity="",
                avg_entry_price=0.0,
                avg_exit_price=0.0,
                weight=15.0,
                price_change_pct=4.0,
                is_special_asset=False,
                is_china_equity=False,
            ),
        ]
        contribs = position_contributions(analyses)
        self.assertEqual([s for s, _ in contribs], ["B"])

    def test_empty_input(self):
        self.assertEqual(position_contributions([]), [])


class TestIncomeHelpersEdgeCases(unittest.TestCase):
    """Edge cases for _income_change_pct and _income_index_blockquote."""

    def test_income_change_pct_start_zero_returns_none(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_change_pct
        self.assertIsNone(
            _income_change_pct({"income_total_yearly": 0}, {"income_total_yearly": 100})
        )

    def test_income_change_pct_start_missing_returns_none(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_change_pct
        self.assertIsNone(_income_change_pct({}, {"income_total_yearly": 100}))

    def test_income_change_pct_end_missing_returns_none(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_change_pct
        self.assertIsNone(
            _income_change_pct({"income_total_yearly": 100}, {})
        )

    def test_income_change_pct_normal(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_change_pct
        self.assertAlmostEqual(
            _income_change_pct(
                {"income_total_yearly": 100}, {"income_total_yearly": 105}
            ),
            5.0,
        )

    def test_income_index_blockquote_start_zero_returns_none(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_index_blockquote
        self.assertIsNone(
            _income_index_blockquote(
                {"income_total_yearly": 0}, {"income_total_yearly": 105}
            )
        )

    def test_income_index_blockquote_start_missing_returns_none(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_index_blockquote
        self.assertIsNone(
            _income_index_blockquote({}, {"income_total_yearly": 105})
        )

    def test_income_index_blockquote_end_missing_returns_none(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_index_blockquote
        self.assertIsNone(
            _income_index_blockquote({"income_total_yearly": 100}, {})
        )

    def test_income_index_blockquote_normal(self):
        from portfolio_yic_reports.auto.markdown_renderer import _income_index_blockquote
        bq = _income_index_blockquote(
            {"income_total_yearly": 100}, {"income_total_yearly": 105}
        )
        self.assertIn("100 → 105.0", bq)


class TestMatchCombinedSnapshotTieBreak(unittest.TestCase):
    """When multiple snapshots share an embedded date, the one with the
    latest filename-embedded timestamp must win. Files without a timestamp
    suffix sort before timestamped siblings of the same date.
    """

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        # Three snapshots for 2026-06-30 with different timestamps (real
        # filename convention: combined_data_YYYY-MM-DD_YYYYMMDDTHHMMSSZ.json).
        # The earliest has twr=None (incomplete); the latest has twr=-6.84.
        base = {
            "as_of_date": "2026-06-30",
            "data": {
                "IB_PERFORMANCE": {"rate_of_return_pct": None},
                "INDEX_PERFORMANCE": {"SP500": {"rate_of_return_pct": 9.34}},
            },
        }
        for ts, twr in [
            ("20260630T204134Z", None),
            ("20260630T204811Z", None),
            ("20260630T205647Z", -6.84),
        ]:
            d = json.loads(json.dumps(base))
            d["data"]["IB_PERFORMANCE"]["rate_of_return_pct"] = twr
            (self.tmp / f"combined_data_2026-06-30_{ts}.json").write_text(
                json.dumps(d), encoding="utf-8"
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_latest_timestamp_wins(self):
        p = match_combined_snapshot(self.tmp, _date(2026, 6, 30))
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "combined_data_2026-06-30_20260630T205647Z.json")

    def test_no_suffix_file_does_not_shadow_timestamped(self):
        """A no-suffix file (treated as earliest of that date) must not
        be chosen when a later timestamped sibling exists."""
        (self.tmp / "combined_data_2026-06-30.json").write_text(
            json.dumps({"as_of_date": "2026-06-30", "data": {}}), encoding="utf-8"
        )
        p = match_combined_snapshot(self.tmp, _date(2026, 6, 30))
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "combined_data_2026-06-30_20260630T205647Z.json")

    def test_no_suffix_file_chosen_when_only_option(self):
        """If only a no-suffix file exists for the date, it is chosen."""
        import shutil
        # Remove all timestamped files
        for f in self.tmp.glob("combined_data_2026-06-30_*.json"):
            f.unlink()
        (self.tmp / "combined_data_2026-06-30.json").write_text(
            json.dumps({"as_of_date": "2026-06-30", "data": {}}), encoding="utf-8"
        )
        p = match_combined_snapshot(self.tmp, _date(2026, 6, 30))
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "combined_data_2026-06-30.json")

    def test_boundary_before_any_snapshot_returns_none(self):
        p = match_combined_snapshot(self.tmp, _date(2026, 6, 29))
        self.assertIsNone(p)

    def test_earlier_date_boundary_picks_latest_of_that_date(self):
        # Add a 2026-06-29 snapshot to ensure boundary != date still works
        (self.tmp / "combined_data_2026-06-29_20260629T100000Z.json").write_text(
            json.dumps({"as_of_date": "2026-06-29", "data": {}}), encoding="utf-8"
        )
        # Boundary 2026-06-30 should still pick the 2026-06-30_205647Z
        p = match_combined_snapshot(self.tmp, _date(2026, 6, 30))
        self.assertEqual(p.name, "combined_data_2026-06-30_20260630T205647Z.json")


def _date(y, m, d):
    import datetime as dt
    return dt.date(y, m, d)


if __name__ == "__main__":
    unittest.main()