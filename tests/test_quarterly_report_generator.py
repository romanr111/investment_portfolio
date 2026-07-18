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

    def test_closed_position_uses_start_denominator(self):
        """Closed position weight should use start-period equity total."""
        from portfolio_yic_reports.auto.position_analyzer import (
            analyze_position,
            equity_total_value,
        )

        start_eq = equity_total_value(self.start)
        end_eq = equity_total_value(self.end)
        # VOO is closed (exists in start, not in end)
        a = analyze_position("VOO", self.start, self.end, end_eq, start_eq)
        self.assertIsNotNone(a)
        self.assertIn("Закрита", a.activity)
        # Weight should be start_value / start_equity_total, not / end_equity_total
        voo_start_val = self.start.positions["VOO"].position_value
        expected_weight = (voo_start_val / start_eq) * 100
        self.assertAlmostEqual(a.weight, expected_weight, places=2)
        # Verify it differs from end-period denom
        end_denom_weight = (voo_start_val / end_eq) * 100
        self.assertNotAlmostEqual(a.weight, end_denom_weight, places=2)

    def test_special_assets_value_includes_bills(self):
        """special_assets_value must include BILL positions (CUSIPs)."""
        from portfolio_yic_reports.auto.position_analyzer import (
            special_assets_value,
        )

        val = special_assets_value(self.end)
        # End snapshot has a BILL position (912797PV3) worth 32762.02
        self.assertGreater(val, 32762)

    def test_lazy_init_no_filters_constants(self):
        """portfolio_yic_reports.__init__ must not import data.filters_constants."""
        import sys

        # Block the module to simulate a clean checkout
        original = sys.modules.pop("data.filters_constants", None)
        sys.modules["data.filters_constants"] = None
        try:
            # Force re-import of the package
            for mod in list(sys.modules.keys()):
                if mod.startswith("portfolio_yic_reports."):
                    del sys.modules[mod]
            if "portfolio_yic_reports" in sys.modules:
                del sys.modules["portfolio_yic_reports"]
            import portfolio_yic_reports

            # Accessing auto subpackage should work
            from portfolio_yic_reports.auto import cli

            self.assertTrue(True)
        finally:
            if original is not None:
                sys.modules["data.filters_constants"] = original
            else:
                del sys.modules["data.filters_constants"]


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


class TestQ2ReportGeneration(unittest.TestCase):
    """Tests using sanitized real Q2 2026 snapshots (LastBusinessDay, 0 trades)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.output_dir = Path(self.tmp) / "reports"
        self.snapshots_dir = Path(self.tmp) / "snapshots"
        self.combined_dir = Path(self.tmp) / "combined"
        self.snapshots_dir.mkdir()
        self.combined_dir.mkdir()
        shutil.copy(
            FIXTURES / "flex_portfolio_q2_2026_start.xml",
            self.snapshots_dir / "stocks_count_trades_20260401_20260717T015740Z.xml",
        )
        shutil.copy(
            FIXTURES / "flex_portfolio_q2_2026_end.xml",
            self.snapshots_dir / "stocks_count_trades_20260630_20260717T025037Z.xml",
        )
        shutil.copy(
            FIXTURES / "combined_data_2026-04-01.json", self.combined_dir
        )
        shutil.copy(
            FIXTURES / "combined_data_2026-06-30.json", self.combined_dir
        )
        self.config = ReportConfig(
            snapshots_dir=self.snapshots_dir,
            combined_data_dir=self.combined_dir,
            portfolio_history_csv=FIXTURES / "portfolio_history_q2_stub.csv",
            dalio_summary_json=FIXTURES / "analytics_summary_stub.json",
            output_dir=self.output_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_q2_start(self):
        snap = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_start.xml")
        )
        self.assertEqual(snap.to_date, "20260401")
        self.assertEqual(snap.account_id, "TEST123456")
        self.assertEqual(len(snap.positions), 23)
        self.assertEqual(len(snap.trades), 0)

    def test_parse_q2_end(self):
        snap = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_end.xml")
        )
        self.assertEqual(snap.to_date, "20260630")
        self.assertEqual(snap.account_id, "TEST123456")
        self.assertEqual(len(snap.positions), 23)
        self.assertEqual(len(snap.trades), 0)

    def test_q2_closed_positions_detected(self):
        """COP, GDX, XLE present in start but absent in end -> closed."""
        start = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_start.xml")
        )
        end = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_end.xml")
        )
        start_syms = set(start.positions.keys())
        end_syms = set(end.positions.keys())
        closed = start_syms - end_syms
        self.assertIn("COP", closed)
        self.assertIn("GDX", closed)
        self.assertIn("XLE", closed)

    def test_q2_new_positions_detected(self):
        """MCO, SPGI, TLT absent in start but present in end -> new."""
        start = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_start.xml")
        )
        end = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_end.xml")
        )
        new = set(end.positions.keys()) - set(start.positions.keys())
        self.assertIn("MCO", new)
        self.assertIn("SPGI", new)
        self.assertIn("TLT", new)

    def test_q2_increased_positions(self):
        """CPRT, IAU, UBER share counts increased."""
        start = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_start.xml")
        )
        end = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_end.xml")
        )
        for sym in ["CPRT", "IAU", "UBER"]:
            self.assertGreater(
                end.positions[sym].shares,
                start.positions[sym].shares,
                f"{sym} should have increased shares",
            )

    def test_q2_bill_rollover(self):
        """BILL CUSIP changes: 912797TD9 (start) -> 912797TC1 (end)."""
        start = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_start.xml")
        )
        end = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_end.xml")
        )
        self.assertIn("912797TD9", start.positions)
        self.assertEqual(
            start.positions["912797TD9"].asset_category, "BILL"
        )
        self.assertIn("912797TC1", end.positions)
        self.assertEqual(
            end.positions["912797TC1"].asset_category, "BILL"
        )

    def test_q2_closed_without_trades_no_exit_price(self):
        """Closed positions with 0 trades should not show exit price in price column."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        # COP is closed but trades=0 -> no exit arrow in price column
        cop_lines = [
            line for line in content.splitlines() if "COP" in line and "|" in line
        ]
        self.assertTrue(len(cop_lines) > 0)
        for line in cop_lines:
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 4:
                price_cell = cells[3]
                self.assertNotIn("→", price_cell)

    def test_q2_report_e2e(self):
        """Full Q2 report generation from sanitized real snapshots."""
        out = generate_report(self.config, 2026, 2)
        self.assertTrue(out.exists())
        content = out.read_text(encoding="utf-8")
        self.assertIn("Квартальний звіт", content)
        self.assertIn("2-й квартал 2026 року", content)
        self.assertIn("Net worth: $157,816", content)
        self.assertIn("Зміни в алокації", content)
        self.assertIn("Акціонарний портфель", content)
        self.assertIn("Доходність та дивіденди", content)
        self.assertIn("YTD TWR: -4.12%", content)
        self.assertIn("Річний дивідендний дохід: $5,710", content)
        self.assertIn("32.69% → 31.56%", content)

    def test_q2_activity_counts(self):
        """Activity summary: 2 increased, 0 decreased, ~13 unchanged, 2 new, 2 closed."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        # Find the summary line with arrows
        for line in content.splitlines():
            if "Підсумок" in line:
                self.assertIn("↑2", line)
                self.assertIn("↓0", line)
                self.assertIn("+2", line)
                self.assertIn("-2", line)
                break

    def test_q2_new_positions_in_report(self):
        """MCO and SPGI should appear as new positions in the report."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        self.assertIn("MCO", content)
        self.assertIn("SPGI", content)
        self.assertIn("Нова", content)

    def test_q2_allocation_diff(self):
        """Allocation diff uses Q2 portfolio_history stub (Mar 31 -> Jun 30)."""
        diff = compute_allocation_diff(
            FIXTURES / "portfolio_history_q2_stub.csv", 2026, 2
        )
        self.assertEqual(diff.start_date, dt.date(2026, 3, 31))
        self.assertEqual(diff.end_date, dt.date(2026, 6, 30))
        buckets = {r.bucket: r for r in diff.rows}
        self.assertIn("Stocks", buckets)
        # Stocks went 65161 -> 57852
        self.assertAlmostEqual(buckets["Stocks"].value_change, -7309.0)

    def test_q2_core_satellite_ratio(self):
        end = parse_snapshot(
            str(FIXTURES / "flex_portfolio_q2_2026_end.xml")
        )
        core, sat = core_satellite_ratio(end)
        self.assertGreater(core, 0)
        self.assertGreater(sat, 0)
        self.assertAlmostEqual(core + sat, 100, places=2)

    def test_q2_flex_fetcher_not_called(self):
        """Ensure Q2 report generation never triggers a network fetch."""
        with mock.patch(
            "src.brokers.ib_flex_portfolio.IBFlexPortfolioFetcher.fetch_snapshot_xml"
        ) as m:
            generate_report(self.config, 2026, 2)
            m.assert_not_called()

    def test_q2_closed_positions_show_actual_exit_price_with_trades_xml(self):
        """When a quarterly trades XML is provided, closed positions show
        the actual sell price from trades, not an approximation."""
        config = ReportConfig(
            snapshots_dir=self.snapshots_dir,
            combined_data_dir=self.combined_dir,
            portfolio_history_csv=FIXTURES / "portfolio_history_q2_stub.csv",
            dalio_summary_json=FIXTURES / "analytics_summary_stub.json",
            output_dir=self.output_dir,
            trades_xml=str(FIXTURES / "flex_trades_q2_2026.xml"),
        )
        out = generate_report(config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        # COP was sold at 111.46 per the trades XML
        cop_lines = [
            line for line in content.splitlines() if "COP" in line and "|" in line
        ]
        self.assertTrue(len(cop_lines) > 0)
        cop_price_cell = [c.strip() for c in cop_lines[0].split("|")][3]
        self.assertIn("111.46", cop_price_cell)
        self.assertIn("(Exit)", cop_price_cell)

    def test_q2_special_asset_exit_price_from_trades_xml(self):
        """GDX (special asset) sold at 88.36 should show in bonds/metals table."""
        config = ReportConfig(
            snapshots_dir=self.snapshots_dir,
            combined_data_dir=self.combined_dir,
            portfolio_history_csv=FIXTURES / "portfolio_history_q2_stub.csv",
            dalio_summary_json=FIXTURES / "analytics_summary_stub.json",
            output_dir=self.output_dir,
            trades_xml=str(FIXTURES / "flex_trades_q2_2026.xml"),
        )
        out = generate_report(config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        gdx_lines = [
            line for line in content.splitlines() if "GDX" in line and "|" in line
        ]
        self.assertTrue(len(gdx_lines) > 0)
        gdx_price_cell = [c.strip() for c in gdx_lines[0].split("|")][3]
        self.assertIn("88.36", gdx_price_cell)
        self.assertIn("(Exit)", gdx_price_cell)


if __name__ == "__main__":
    unittest.main()