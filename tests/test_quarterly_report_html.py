"""Tests for the quarterly HTML report: renderer, collectors, and assembly."""

import json
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "portfolio_yic_reports")
)

from analyze_portfolio_reports import (  # noqa: E402
    Portfolio,
    PortfolioAnalyzer,
    Stock,
    collect_special_asset_rows,
    collect_stock_rows,
)
from generate_quarterly_report import (  # noqa: E402
    _quarter_month_range_uk,
    build_allocation_rows,
    build_alternative_asset_tables,
    build_footnotes,
    build_kpis,
    build_report_data,
    find_main_change,
    read_allocation_values,
    read_allocations,
    read_net_worth,
    select_after_snapshot,
    select_before_snapshot,
    snapshot_date_from_name,
)
from quarterly_report_html import (  # noqa: E402
    AllocationRow,
    DetailTable,
    KpiCard,
    PositionRow,
    ReportData,
    render_report,
)

EXTERNAL_REF_RE = re.compile(r"https?:|<script|<link|@import|src=", re.IGNORECASE)


def _stock(symbol, shares, cost, value, mark, category="STK"):
    return Stock(
        symbol=symbol,
        shares=shares,
        cost_basis=cost,
        position_value=value,
        asset_category=category,
        is_chinese_stock=False,
        mark_price=mark,
    )


def _make_analyzer():
    """Initial: AAA, CCC, COMB. Final: AAA (grown), BBB (new), COMB; CCC sold."""
    initial = Portfolio("20260401")
    initial.add_stock(_stock("AAA", 10, 100.0, 1000.0, 100.0))
    initial.add_stock(_stock("CCC", 5, 50.0, 250.0, 50.0))
    initial.add_stock(_stock("COMB", 20, 25.0, 500.0, 25.0))

    final = Portfolio("20260630")
    final.add_stock(_stock("AAA", 12, 100.0, 1320.0, 110.0))
    final.add_stock(_stock("BBB", 3, 200.0, 630.0, 210.0))
    final.add_stock(_stock("COMB", 20, 25.0, 520.0, 26.0))
    final.add_sell_trade("CCC", 5, 60.0)

    initial.calculate_weights()
    final.calculate_weights()
    return PortfolioAnalyzer(initial, final)


class TestCollectors(unittest.TestCase):
    def test_stock_rows_kinds_and_order(self):
        rows = collect_stock_rows(_make_analyzer())
        symbols = [row["symbol"] for row in rows]
        # Open positions by weight desc (AAA 1320 > BBB 630), closed last.
        self.assertEqual(symbols, ["AAA", "BBB", "CCC"])

        aaa, bbb, ccc = rows
        self.assertEqual(aaa["kind"], "increased")
        self.assertEqual(aaa["activity_text"], "Збільшив (+20%)")
        self.assertAlmostEqual(aaa["weight_pct"], 1320.0 / 1950.0 * 100, places=2)
        self.assertEqual(aaa["price_text"], "100.00$")
        self.assertAlmostEqual(aaa["pl_pct"], 10.0, places=2)

        self.assertEqual(bbb["kind"], "new")
        self.assertEqual(bbb["activity_text"], "Нова позиція")
        self.assertAlmostEqual(bbb["pl_pct"], 5.0, places=2)

        self.assertEqual(ccc["kind"], "closed")
        self.assertEqual(ccc["activity_text"], "Закрита позиція")
        self.assertNotIn("weight_pct", ccc)
        self.assertRegex(ccc["weight_text"], r"^\d+\.\d{2}% → 0%$")
        self.assertEqual(ccc["price_text"], "50.00$ → 60.00$")
        self.assertAlmostEqual(ccc["pl_pct"], 20.0, places=2)


def _snapshot_json(stocks_pct=30.0):
    """Minimal combined_data snapshot payload carrying allocation data."""
    return json.dumps(
        {"data": {"ASSET_ALLOCATION": {"allocations": {"Stocks": {"percentage": stocks_pct}}}}}
    )


class TestSnapshotSelection(unittest.TestCase):
    """
    Snapshots come from main.py's save_combined_data_snapshot_json, which
    every `just run` already writes to data/snapshots/ as
    combined_data_{date}_{timestamp}Z.json plus a dateless combined_data_latest.json.
    """

    def test_picks_newest_within_grace(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in [
                "combined_data_2026-03-31_20260331T235500Z.json",
                "combined_data_2026-04-03_20260403T090000Z.json",
                "combined_data_2026-06-30_20260630T205647Z.json",
                "combined_data_latest.json",
            ]:
                (tmp_path / name).write_text(_snapshot_json())
            selected = select_before_snapshot(tmp_path, datetime(2026, 4, 1))
            self.assertEqual(
                selected.name, "combined_data_2026-04-03_20260403T090000Z.json"
            )


    def test_skips_snapshot_without_allocations(self):
        # The real 2026-04-01 pipeline snapshot predates ASSET_ALLOCATION and is
        # empty; an older-but-populated backfill must win over it.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "combined_data_2026-04-01_20260401T174713Z.json").write_text(
                "{}"
            )
            (tmp_path / "combined_data_2026-03-31_manual.json").write_text(
                _snapshot_json()
            )
            selected = select_before_snapshot(tmp_path, datetime(2026, 4, 1))
            self.assertEqual(selected.name, "combined_data_2026-03-31_manual.json")

    def test_snapshot_date_from_name(self):
        self.assertEqual(
            snapshot_date_from_name("combined_data_2026-04-01_20260401T174713Z.json"),
            datetime(2026, 4, 1).date(),
        )
        self.assertEqual(
            snapshot_date_from_name("combined_data_2026-04-01_manual-backfill.json"),
            datetime(2026, 4, 1).date(),
        )
        # No embedded date (the rolling-latest file) -> None.
        self.assertIsNone(snapshot_date_from_name("combined_data_latest.json"))
        # Well-formed prefix but an impossible calendar date -> None, not a crash.
        self.assertIsNone(
            snapshot_date_from_name("combined_data_2026-13-40_x.json")
        )

    def test_none_when_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "combined_data_2026-06-30_20260630T205647Z.json").write_text(
                _snapshot_json()
            )
            self.assertIsNone(select_before_snapshot(tmp_path, datetime(2026, 4, 1)))

    def test_after_snapshot_prefers_selected_quarter_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "combined_data_2026-06-30_end.json").write_text(
                json.dumps(
                    {
                        "data": {
                            "ASSET_ALLOCATION": {"allocations": {"Stocks": {"percentage": 30}}},
                            "ACTIVITY_DATA": {"quarters": {"2026-Q2": {}}},
                        }
                    }
                )
            )
            (tmp_path / "combined_data_2026-07-03_later.json").write_text(
                _snapshot_json()
            )

            selected = select_after_snapshot(
                tmp_path, datetime(2026, 6, 30), "2026-Q2"
            )

            self.assertEqual(selected.name, "combined_data_2026-06-30_end.json")


class TestDerivations(unittest.TestCase):
    BEFORE = {"Stocks": 38.55, "Cash": 0.80, "Bonds": 21.59}
    AFTER = {"Stocks": 32.20, "Cash": 6.30, "Bonds": 24.00}

    def test_summary_card_tracks_largest_share_change_not_dollar_change(self):
        report = build_report_data(
            _make_analyzer(), "20260930", -5.7, 11.6,
            {"Stocks": 50.0, "Bonds": 20.0},
            {"Stocks": 49.0, "Bonds": 25.0},
        )
        self.assertEqual(report.kpis[3].label, "Частка облігацій")
        self.assertEqual(report.kpis[3].value, "25,0%")
        self.assertEqual(report.kpis[3].caption, "Було 20,0%\nна початку кварталу")
        self.assertEqual(report.kpis[3].tone, "navy")
        html = render_report(report)
        self.assertIn("Підсумки на 30 вересня 2026", html)
        self.assertEqual(html.count('<div class="kpi-purpose">'), 1)
        self.assertIn("Найбільша зміна\nза квартал", html)

    def test_crypto_public_report_hides_private_position_values(self):
        table = build_alternative_asset_tables({
            "ASSET_ALLOCATION": {"allocations": {"Crypto Coins": {"value": 2000}}},
            "ACTIVITY_DATA": {"quarters": {"2026-Q3": {"crypto": [{
                "asset": "BTC", "start_value_usd": 1234, "end_value_usd": 1567,
                "start_quantity": .1, "end_quantity": .11, "coverage": "partial",
            }]}}},
        }, "2026-Q3")[0]
        html = render_report(ReportData(
            period_title="Q3", quarter_label="Q3", year_label="2026",
            kpis=[], footnotes=[], allocation_rows=[], stock_rows=[],
            core_satellite=(0, 100), china_rest=(0, 100),
            alternative_asset_tables=[table],
        ))
        self.assertNotIn("Вартість", table.headers)
        section = html.split("<h3>Криптовалюти</h3>", 1)[1].split("</section>", 1)[0]
        self.assertNotIn("$", section)
        self.assertNotIn("1,234", html)
        self.assertNotIn("1,567", html)
        self.assertEqual(len(table.headers), 3)
        self.assertEqual(len(re.findall(r"<td(?: [^>]*)?>", section)), 3)

    def test_crypto_profit_placeholders_are_never_rendered(self):
        table = build_alternative_asset_tables({
            "ACTIVITY_DATA": {"quarters": {"2026-Q3": {"crypto": [{
                "asset": "BTC", "start_value_usd": 100, "end_value_usd": 240,
                "start_quantity": 1, "end_quantity": 2, "coverage": "partial",
                "average_entry_price_usd": 12345, "profit_pct": 987.65,
            }]}}},
        }, "2026-Q3")[0]
        self.assertEqual(table.headers, ["Позиція", "Зміна кількості монет",
            "Вага (криптовалюти)"])
        self.assertEqual(table.rows[0][1], "+100.0%")
        self.assertIsNone(table.position_rows[0].pl_pct)
        self.assertEqual(len(table.rows[0]), 3)
        html = render_report(ReportData(
            period_title="Q3", quarter_label="Q3", year_label="2026",
            kpis=[], footnotes=[], allocation_rows=[], stock_rows=[],
            core_satellite=(0, 100), china_rest=(0, 100),
            alternative_asset_tables=[table],
        )).split("<h3>Криптовалюти</h3>", 1)[1].split("</section>", 1)[0]
        for private in ("12345", "987.65", "Зміна ціни", "P/L", "placeholder"):
            self.assertNotIn(private, html)
        self.assertNotIn("Фініш / Старт", table.note)


    def test_crypto_table_hides_nonfinite_values(self):
        table = build_alternative_asset_tables({"ACTIVITY_DATA": {"quarters": {
            "2026-Q3": {"crypto": [{"asset": "X", "coverage": "partial",
                "start_value_usd": float("nan"), "end_value_usd": float("inf")}]}
        }}}, "2026-Q3")[0]
        self.assertEqual(table.rows[0][2], "-")


if __name__ == "__main__":
    unittest.main()