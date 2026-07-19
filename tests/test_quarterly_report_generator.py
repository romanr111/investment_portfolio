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

    # extract_metrics tests consolidated in test_auto_data_layer.py


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
        # Header should no longer include "Net worth"
        self.assertNotIn("Net worth", content)
        self.assertIn("## 1. Коротко за квартал", content)
        self.assertIn("## 2. Результати портфеля Interactive Brokers", content)
        self.assertIn("## 3. Зміни в структурі сукупного портфеля", content)
        self.assertIn("## 4. Склад і зміни портфеля IBKR", content)
        self.assertIn("## 5. Дивіденди та процентні доходи сукупного портфеля", content)
        self.assertIn("## 6. Ризик і концентрація", content)
        self.assertNotIn("## 7.", content)
        # No separate appendix section anymore
        self.assertNotIn("## 8. Додаток", content)
        # Header metadata lines removed; only the title remains
        self.assertNotIn("Дата генерації", content)
        self.assertNotIn("Звіт на дату", content)
        # Old section names should not appear
        self.assertNotIn("Зміни в алокації", content)
        self.assertNotIn("Акціонарний портфель", content)
        self.assertNotIn("Доходність та дивіденди", content)
        self.assertNotIn("Ребалансування не потрібне", content)
        self.assertNotIn("Red flag: data quality penalty", content)

    def test_report_contains_dalio(self):
        out = generate_report(self.config, 2026, 1)
        content = out.read_text(encoding="utf-8")
        self.assertIn("## 6. Ризик і концентрація", content)
        # HHI is no longer rendered (moved to appendix/analytics summary);
        # the reader-facing view shows top positions + effective bets.
        self.assertIn("Три найбільші позиції IBKR", content)
        # Effective bets line is shown only when correlation coverage is
        # complete (penalty == 0); the Q1 fixture has penalty 63.9 > 0,
        # so the report must say the estimate is unavailable.
        self.assertIn(
            "Оцінка кількості незалежних ставок недоступна", content
        )
        self.assertNotIn("Індекс концентрації HHI", content)

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
        self.assertNotIn("## 6. Ризик і концентрація", content)

    def test_report_includes_snapshot_dates(self):
        out = generate_report(self.config, 2026, 1)
        content = out.read_text(encoding="utf-8")
        # Header now only has the title; snapshot dates are no longer in the header.
        # The quarter label must appear in the title.
        self.assertIn("1-й квартал 2026 року", content)

    def test_equity_weights_sum_to_100(self):
        """Open equity weights in the section 4.1 equity table must sum to ~100%."""
        import re

        out = generate_report(self.config, 2026, 1)
        content = out.read_text(encoding="utf-8")
        # Section 4.1 open equity table header
        tbl_start = content.find("| Позиція | Остання активність | Вага |")
        self.assertGreater(tbl_start, 0, "section 4.1 equity table must exist")
        tbl_end = content.find("Підсумок", tbl_start)
        table = content[tbl_start:tbl_end]
        total = 0.0
        for r in table.splitlines()[2:]:
            cells = [x.strip() for x in r.split("|")]
            if len(cells) < 4:
                continue
            w = cells[3]
            m = re.match(r"([\d.]+)%", w)
            if m:
                total += float(m.group(1))
        self.assertAlmostEqual(total, 100.0, places=0)

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
        """Closed positions with 0 trades should show '—' as exit price in 4.3."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        # COP is closed but no trades_xml configured -> exit price is '—'.
        closed_start = content.find("### Закриті протягом кварталу позиції")
        self.assertGreater(closed_start, 0, "section 4.3 closed table must exist")
        closed_end = content.find("## 5.", closed_start)
        closed_section = content[closed_start:closed_end]
        cop_lines = [
            line for line in closed_section.splitlines()
            if line.startswith("| COP ") and "|" in line
        ]
        self.assertTrue(len(cop_lines) > 0, "COP must appear in 4.3 closed table")
        # cells: [empty, Позиція, Клас активу, Ціна входу → виходу, Реалізований P/L, Причина, empty]
        cells = [c.strip() for c in cop_lines[0].split("|")]
        price_cell = cells[3]  # "Ціна входу → виходу"
        self.assertNotIn("111.46", price_cell)  # no exit price without trades

    def test_q2_report_e2e(self):
        """Full Q2 report generation from sanitized real snapshots."""
        out = generate_report(self.config, 2026, 2)
        self.assertTrue(out.exists())
        content = out.read_text(encoding="utf-8")
        self.assertIn("Квартальний звіт", content)
        self.assertIn("2-й квартал 2026 року", content)
        self.assertNotIn("Net worth", content)
        self.assertIn("## 1. Коротко за квартал", content)
        self.assertIn("## 2. Результати портфеля Interactive Brokers", content)
        self.assertIn("## 3. Зміни в структурі сукупного портфеля", content)
        self.assertIn("## 4. Склад і зміни портфеля IBKR", content)
        self.assertIn("## 5. Дивіденди та процентні доходи сукупного портфеля", content)
        self.assertIn("## 6. Ризик і концентрація", content)
        self.assertNotIn("## 7.", content)
        self.assertNotIn("## 8. Додаток", content)
        self.assertNotIn("Ребалансування не потрібне", content)
        self.assertNotIn("Red flag: data quality penalty", content)
        # Freedom progress should appear (section 5)
        self.assertIn("32.69% → 31.56%", content)

    def test_q2_section1_note_lists_non_ibkr_assets(self):
        """Section 1 note lists non-IBKR asset classes and their combined % of capital."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        s1_start = content.find("## 1. Коротко за квартал")
        s2_start = content.find("## 2.", s1_start)
        s1 = content[s1_start:s2_start]
        self.assertIn("Не входять у доходність:", s1)
        self.assertIn("Інші активи", s1)
        self.assertIn("Криптокредитування", s1)
        self.assertIn("Криптовалюти", s1)
        self.assertIn("P2P-кредитування", s1)
        # Combined % should be present (e.g. "28.2% капіталу")
        import re
        m = re.search(r"\((\d+\.\d+)% капіталу\)", s1)
        self.assertIsNotNone(m, "note should include '(N.N% капіталу)'")
        self.assertGreater(float(m.group(1)), 0)

    def test_q2_section2_performance_table(self):
        """Section 2 (performance) includes IBKR/S&P 500/NASDAQ rows."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        s2_start = content.find("## 2. Результати портфеля Interactive Brokers")
        s3_start = content.find("## 3.", s2_start)
        s2 = content[s2_start:s3_start]
        self.assertIn("Дохідність IBKR", s2)
        self.assertIn("S&P 500", s2)
        self.assertIn("NASDAQ", s2)

    def test_q2_section6_top_positions_line(self):
        """Section 6 lists top-3 positions by weight (BRK B, GOOG, 9988)."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        s6_start = content.find("## 6. Ризик і концентрація")
        s7_start = content.find("## 7.", s6_start)
        s6 = content[s6_start:s7_start]
        self.assertIn("Три найбільші позиції IBKR: **BRK B, GOOG, 9988**", s6)

    def test_q2_section3_blockquote_uses_genitive(self):
        """Section 3 (allocation) blockquote uses lowercase genitive bucket name."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        s3_start = content.find("## 3. Зміни в структурі сукупного портфеля")
        s4_start = content.find("## 4.", s3_start)
        s3 = content[s3_start:s4_start]
        # Largest change is Stocks (−4.41). Genitive: "акцій IBKR".
        self.assertIn("зменшення частки акцій IBKR", s3)
        # Should NOT use nominative form in the blockquote.
        self.assertNotIn("частки Акції IBKR", s3)

    def test_q2_section4_equity_table_excludes_closed(self):
        """Section 4.1 open equity table excludes closed positions (COP, XLE).
        Closed positions appear only in the dedicated 4.3 subsection."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        s4_start = content.find("### Акції — відкриті позиції")
        s4_end = content.find("### Облігації", s4_start)
        s4_open = content[s4_start:s4_end]
        for line in s4_open.splitlines():
            if line.startswith("| COP ") or line.startswith("| XLE "):
                self.fail(f"Closed position leaked into 4.1 open equity table: {line!r}")

    def test_q2_activity_counts(self):
        """Section 4.1 equity table contains the activity labels (Збільшив, Нова)."""
        out = generate_report(self.config, 2026, 2)
        content = out.read_text(encoding="utf-8")
        # Activity labels now appear in the §4.1 equity table, not in §1.
        s4_start = content.find("### Акції — відкриті позиції")
        s4_end = content.find("### Облігації", s4_start)
        s4 = content[s4_start:s4_end]
        self.assertIn("Збільшив", s4)
        self.assertIn("Нова", s4)

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
        """When a quarterly trades XML is provided, closed positions in the 4.3
        subsection show the actual sell price from trades."""
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
        # COP was sold at 111.46 per the trades XML; appears in 4.3 closed table.
        closed_start = content.find("### Закриті протягом кварталу позиції")
        self.assertGreater(closed_start, 0)
        closed_end = content.find("## 5.", closed_start)
        closed_section = content[closed_start:closed_end]
        cop_lines = [
            line for line in closed_section.splitlines()
            if line.startswith("| COP ") and "|" in line
        ]
        self.assertTrue(len(cop_lines) > 0)
        # cells: [empty, Позиція, Клас активу, Ціна входу → виходу, Реалізований P/L, Причина, empty]
        cells = [c.strip() for c in cop_lines[0].split("|")]
        price_cell = cells[3]
        self.assertIn("111.46", price_cell)

    def test_q2_special_asset_exit_price_from_trades_xml(self):
        """GDX (special asset) sold at 88.36 should appear in the bonds/metals
        table at the end of section 8."""
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
        # Special assets table uses 4 columns: Позиція | Остання активність |
        # Середня ціна входу | Вага (від загальної вартості)
        # cells[3] = Середня ціна входу
        gdx_lines = [
            line for line in content.splitlines() if "GDX" in line and "|" in line
        ]
        self.assertTrue(len(gdx_lines) > 0)
        gdx_price_cell = [c.strip() for c in gdx_lines[0].split("|")][3]
        self.assertIn("88.36", gdx_price_cell)
        self.assertIn("(Exit)", gdx_price_cell)


if __name__ == "__main__":
    unittest.main()