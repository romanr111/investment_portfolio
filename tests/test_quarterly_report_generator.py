"""Tests for the auto quarterly report generator."""

import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from portfolio_yic_reports.auto.allocation_diff import compute_allocation_diff
from portfolio_yic_reports.auto.combined_loader import (
    extract_metrics,
    match_combined_snapshot,
)
from portfolio_yic_reports.auto.config import ReportConfig
from portfolio_yic_reports.auto.dalio_loader import extract_dalio_metrics
from portfolio_yic_reports.auto.dates import (
    last_completed_quarter,
    parse_snapshot_filename_date,
    quarter_end_date,
    previous_quarter_end_date,
)
from portfolio_yic_reports.auto.flex_xml_parser import parse_snapshot
from portfolio_yic_reports.auto.markdown_renderer import render_report
from portfolio_yic_reports.auto.position_analyzer import (
    china_ratio,
    core_satellite_ratio,
    equity_total_value,
)
from portfolio_yic_reports.auto.report_generator import generate_report

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestDates(unittest.TestCase):
    def test_last_completed_quarter_mid_year(self):
        # 2026-05-15 -> Q1 2026 (ended 2026-03-31)
        y, q = last_completed_quarter(dt.date(2026, 5, 15))
        self.assertEqual((y, q), (2026, 1))

    def test_last_completed_quarter_january(self):
        # 2026-01-15 -> Q4 2025 (Q1 2026 not yet ended)
        y, q = last_completed_quarter(dt.date(2026, 1, 15))
        self.assertEqual((y, q), (2025, 4))

    def test_last_completed_quarter_right_after_end(self):
        # 2026-04-01 -> Q1 2026 (ended 2026-03-31 yesterday)
        y, q = last_completed_quarter(dt.date(2026, 4, 1))
        self.assertEqual((y, q), (2026, 1))

    def test_quarter_end_date(self):
        self.assertEqual(quarter_end_date(2026, 1), dt.date(2026, 3, 31))
        self.assertEqual(quarter_end_date(2026, 4), dt.date(2026, 12, 31))

    def test_previous_quarter_end(self):
        self.assertEqual(
            previous_quarter_end_date(2026, 1), dt.date(2025, 12, 31)
        )
        self.assertEqual(
            previous_quarter_end_date(2026, 2), dt.date(2026, 3, 31)
        )

    def test_parse_snapshot_filename_date(self):
        d = parse_snapshot_filename_date(
            "stocks_count_trades_20251231_20260103T020000Z.xml"
        )
        self.assertIsNotNone(d)
        self.assertEqual(d, dt.date(2025, 12, 31))


class TestAllocationDiff(unittest.TestCase):
    def test_compute_allocation_diff(self):
        diff = compute_allocation_diff(
            FIXTURES / "portfolio_history_stub.csv", 2026, 1
        )
        self.assertEqual(diff.start_date, dt.date(2025, 12, 31))
        self.assertEqual(diff.end_date, dt.date(2026, 3, 31))
        self.assertGreater(diff.start_total, 0)
        self.assertGreater(diff.end_total, 0)
        buckets = {r.bucket: r for r in diff.rows}
        self.assertIn("Stocks", buckets)
        self.assertIn("Bonds", buckets)
        # Stocks went 56517 -> 65161
        self.assertAlmostEqual(buckets["Stocks"].value_change, 8644.0)


class TestFlexParser(unittest.TestCase):
    def test_parse_q4_2025(self):
        snap = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q4_2025.xml")
        )
        self.assertEqual(snap.to_date, "20251231")
        self.assertEqual(snap.account_id, "U9064529")
        self.assertIn("9988", snap.positions)
        self.assertGreater(equity_total_value(snap), 0)
        # Has BILL position
        self.assertIn("912797PV3", snap.positions)
        self.assertEqual(snap.positions["912797PV3"].asset_category, "BILL")

    def test_parse_q1_2026_has_trades(self):
        snap = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q1_2026.xml")
        )
        self.assertEqual(snap.to_date, "20260331")
        self.assertGreater(len(snap.trades), 0)
        sell_symbols = {t.symbol for t in snap.trades if t.buy_sell == "SELL"}
        self.assertIn("VOO", sell_symbols)


class TestPositionAnalyzer(unittest.TestCase):
    def setUp(self):
        self.start = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q4_2025.xml")
        )
        self.end = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q1_2026.xml")
        )

    def test_core_satellite_ratio(self):
        core, sat = core_satellite_ratio(self.end)
        self.assertGreater(core, 0)
        self.assertGreater(sat, 0)
        self.assertAlmostEqual(core + sat, 100, places=2)

    def test_china_ratio(self):
        china, rest = china_ratio(self.end)
        self.assertGreater(china, 0)
        self.assertGreater(rest, 0)
        self.assertAlmostEqual(china + rest, 100, places=2)


class TestCombinedLoader(unittest.TestCase):
    def test_match_combined_snapshot(self):
        path = match_combined_snapshot(FIXTURES, dt.date(2026, 3, 31))
        self.assertIsNotNone(path)
        self.assertIn("2026-03-18", path.name)

    def test_match_combined_snapshot_start(self):
        path = match_combined_snapshot(FIXTURES, dt.date(2025, 12, 31))
        self.assertIsNotNone(path)
        self.assertIn("2025-12-31", path.name)

    def test_extract_metrics(self):
        import json

        data = json.loads(
            (FIXTURES / "combined_data_2026-03-18.json").read_text()
        )
        m = extract_metrics(data)
        self.assertEqual(m["twr"], -6.84)
        self.assertEqual(m["dividends_yearly"], 5690)
        self.assertEqual(m["freedom_progress"], "31.56%")
        self.assertEqual(m["total_assets"], 157781)


class TestDalioLoader(unittest.TestCase):
    def test_extract_dalio_metrics(self):
        import json

        data = json.loads(
            (FIXTURES / "analytics_summary_stub.json").read_text()
        )
        m = extract_dalio_metrics(data)
        self.assertAlmostEqual(m["hhi"], 0.21, places=2)
        self.assertAlmostEqual(m["effective_bets"], 4.72, places=2)
        self.assertFalse(m["rebalance_due"])
        self.assertEqual(m["next_rebalance_date"], "2026-06-30 00:00:00")
        self.assertGreater(m["data_quality_penalty_pct"], 0)


class TestReportGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.output_dir = Path(self.tmp) / "reports"
        self.snapshots_dir = Path(self.tmp) / "snapshots"
        self.combined_dir = Path(self.tmp) / "combined"
        self.snapshots_dir.mkdir()
        self.combined_dir.mkdir()
        # Copy fixtures into place
        shutil.copy(
            FIXTURES / "flex_portfolio_q4_2025.xml",
            self.snapshots_dir / "stocks_count_trades_20251231_20260103T020000Z.xml",
        )
        shutil.copy(
            FIXTURES / "flex_portfolio_q1_2026.xml",
            self.snapshots_dir / "stocks_count_trades_20260331_20260403T020000Z.xml",
        )
        shutil.copy(
            FIXTURES / "combined_data_2025-12-31.json", self.combined_dir
        )
        shutil.copy(
            FIXTURES / "combined_data_2026-03-18.json", self.combined_dir
        )

        self.config = ReportConfig(
            snapshots_dir=self.snapshots_dir,
            combined_data_dir=self.combined_dir,
            portfolio_history_csv=FIXTURES / "portfolio_history_stub.csv",
            dalio_summary_json=FIXTURES / "analytics_summary_stub.json",
            output_dir=self.output_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generate_report_no_error(self):
        out = generate_report(self.config, 2026, 1)
        self.assertTrue(out.exists())
        content = out.read_text(encoding="utf-8")
        self.assertIn("Квартальний звіт", content)
        self.assertIn("1-й квартал 2026 року", content)
        self.assertIn("Net worth: $157,781", content)
        self.assertIn("Зміни в алокації", content)
        self.assertIn("Акціонарний портфель", content)
        self.assertIn("Доходність та дивіденди", content)
        self.assertIn("YTD TWR: -6.84%", content)
        self.assertIn("Річний дивідендний дохід: $5,690", content)
        self.assertIn("33.84% → 31.56%", content)

    def test_report_contains_dalio(self):
        out = generate_report(self.config, 2026, 1)
        content = out.read_text(encoding="utf-8")
        self.assertIn("Ризик-аналіз Dalio", content)
        self.assertIn("HHI", content)
        self.assertIn("Effective bets", content)

    def test_report_skip_dalio(self):
        config = ReportConfig(
            snapshots_dir=self.snapshots_dir,
            combined_data_dir=self.combined_dir,
            portfolio_history_csv=FIXTURES / "portfolio_history_stub.csv",
            dalio_summary_json=FIXTURES / "analytics_summary_stub.json",
            output_dir=self.output_dir,
            skip_dalio=True,
        )
        out = generate_report(config, 2026, 1)
        content = out.read_text(encoding="utf-8")
        self.assertNotIn("Ризик-аналіз Dalio", content)

    def test_report_includes_snapshot_dates(self):
        out = generate_report(self.config, 2026, 1)
        content = out.read_text(encoding="utf-8")
        # Notification line referencing report date + quarter end date
        self.assertIn("Звіт на дату", content)
        self.assertIn("2026-03-31", content)

    def test_equity_weights_sum_to_100(self):
        """Active equity weights (excluding closed ->0% rows) must sum to ~100%."""
        import re

        out = generate_report(self.config, 2026, 1)
        content = out.read_text(encoding="utf-8")
        tbl_start = content.find("| Позиція | Остання")
        tbl_end = content.find("Примітка:")
        table = content[tbl_start:tbl_end]
        total = 0.0
        for r in table.splitlines()[2:]:
            cells = [x.strip() for x in r.split("|")]
            if len(cells) < 5:
                continue
            w = cells[4]
            if "→ 0%" in w or w in ("-", ""):
                continue
            m = re.match(r"([\d.]+)%", w)
            if m:
                total += float(m.group(1))
        self.assertAlmostEqual(total, 100.0, places=1)

    def test_explicit_snapshot_paths(self):
        config = ReportConfig(
            snapshots_dir=Path("/nonexistent"),
            combined_data_dir=self.combined_dir,
            portfolio_history_csv=FIXTURES / "portfolio_history_stub.csv",
            dalio_summary_json=FIXTURES / "analytics_summary_stub.json",
            output_dir=self.output_dir,
            snapshot_start=str(
                self.snapshots_dir
                / "stocks_count_trades_20251231_20260103T020000Z.xml"
            ),
            snapshot_end=str(
                self.snapshots_dir
                / "stocks_count_trades_20260331_20260403T020000Z.xml"
            ),
        )
        out = generate_report(config, 2026, 1)
        self.assertTrue(out.exists())

    def test_missing_snapshot_raises(self):
        config = ReportConfig(
            snapshots_dir=Path("/nonexistent"),
            combined_data_dir=self.combined_dir,
            portfolio_history_csv=FIXTURES / "portfolio_history_stub.csv",
            dalio_summary_json=FIXTURES / "analytics_summary_stub.json",
            output_dir=self.output_dir,
        )
        with self.assertRaises(ValueError):
            generate_report(config, 2026, 1)

    def test_flex_fetcher_not_called(self):
        """Ensure report generation never triggers a network fetch."""
        with mock.patch(
            "src.brokers.ib_flex_portfolio.IBFlexPortfolioFetcher.fetch_snapshot_xml"
        ) as m:
            generate_report(self.config, 2026, 1)
            m.assert_not_called()


if __name__ == "__main__":
    unittest.main()