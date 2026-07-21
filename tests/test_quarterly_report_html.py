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
    build_footnotes,
    build_kpis,
    find_main_change,
    read_allocation_values,
    read_allocations,
    read_net_worth,
    select_before_snapshot,
    snapshot_date_from_name,
)
from quarterly_report_html import (  # noqa: E402
    AllocationRow,
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

    def test_special_asset_rows(self):
        rows = collect_special_asset_rows(_make_analyzer())
        self.assertEqual(len(rows), 1)
        comb = rows[0]
        self.assertEqual(comb["symbol"], "COMB")
        self.assertEqual(comb["kind"], "unchanged")
        # Weight base: stocks total (1950) + special assets (520).
        self.assertAlmostEqual(comb["weight_pct"], 520.0 / 2470.0 * 100, places=2)
        # Price and P/L are now separate fields, mirroring collect_stock_rows.
        self.assertEqual(comb["price_text"], "25.00$")
        self.assertAlmostEqual(comb["pl_pct"], 4.0, places=2)


class TestRenderer(unittest.TestCase):
    def _report_data(self):
        return ReportData(
            period_title="2-й квартал 2026 року",
            quarter_label="Q2",
            year_label="2026",
            kpis=[KpiCard(label="IBKR YTD", value="−6.8%", tone="neg")],
            footnotes=["Доходи стосуються лише IBKR."],
            allocation_rows=[
                AllocationRow(name="Акції IBKR", before_pct=38.55, after_pct=32.20),
                AllocationRow(name="Кеш", before_pct=0.80, after_pct=6.30),
            ],
            stock_rows=[
                PositionRow(
                    symbol="AAA",
                    kind="increased",
                    activity_text="Збільшив (+20%)",
                    price_text="100.00$",
                    weight_pct=67.69,
                    pl_pct=10.0,
                ),
                PositionRow(
                    symbol="CCC",
                    kind="closed",
                    activity_text="Закрита позиція",
                    price_text="50.00$ → 60.00$",
                    weight_text="12.82% → 0%",
                    pl_pct=20.0,
                ),
            ],
            core_satellite=(13.78, 86.22),
            china_rest=(21.03, 78.97),
            special_asset_rows=[
                PositionRow(
                    symbol="T Bills",
                    kind="unchanged",
                    activity_text="Без змін",
                    price_text="98.09$",
                    weight_pct=31.42,
                )
            ],
        )

    def test_report_contains_data_and_structure(self):
        html = render_report(self._report_data())
        for expected in [
            "Квартальний звіт",
            "2-й квартал 2026 року",
            "38.55%",
            "32.20%",
            "▼ −6.35%",
            'class="pill pill-add">Збільшив (+20%)',
            'class="pill pill-close">Закрита позиція',
            "12.82% → 0%",
            "50.00$ → 60.00$",
            "13.78% / 86.22%",
            "21.03% / 78.97%",
            "Облігації, золото та товарні активи",
            "98.09$",
            "Підсумок",
            "100.00%",
        ]:
            self.assertIn(expected, html)
        self.assertIn('class="closed-row"', html)

    def test_report_is_self_contained(self):
        html = render_report(self._report_data())
        self.assertIsNone(EXTERNAL_REF_RE.search(html))

    def test_stock_rows_keep_column_count_without_pl(self):
        data = self._report_data()
        data.stock_rows[1].pl_pct = None  # closed position without sell trades
        html = render_report(data)
        ccc_row = re.search(r"<tr[^>]*><td[^>]*>CCC</td>.*?</tr>", html).group(0)
        self.assertEqual(ccc_row.count("<td"), 5)

    def test_no_special_assets_section_when_empty(self):
        data = self._report_data()
        data.special_asset_rows = []
        html = render_report(data)
        self.assertNotIn("Облігації, золото та товарні активи", html)

    def test_special_table_columns_match_stock_table(self):
        # Same column set/order as the stock table: Позиція, Остання
        # активність, Вага, Середня ціна, P/L (weight label differs since the
        # special-assets weight base is documented as the IBKR subset).
        html = render_report(self._report_data())
        self.assertIn(
            "<th>Позиція</th>"
            "<th>Остання активність</th>"
            '<th class="num">Вага (IBKR активи)</th>'
            '<th class="num">Середня ціна</th>'
            '<th class="num">P/L</th>',
            html,
        )

    def test_special_rows_keep_column_count_without_pl(self):
        html = render_report(self._report_data())
        tbills_row = re.search(r"<tr[^>]*><td[^>]*>T Bills</td>.*?</tr>", html).group(0)
        self.assertEqual(tbills_row.count("<td"), 5)


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

    def test_none_when_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "combined_data_2026-06-30_20260630T205647Z.json").write_text(
                _snapshot_json()
            )
            self.assertIsNone(select_before_snapshot(tmp_path, datetime(2026, 4, 1)))

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

    def test_read_allocations_unwraps_snapshot_data_key(self):
        # final_data.json is flat; archived snapshots wrap it under "data".
        flat = {"ASSET_ALLOCATION": {"allocations": {"Stocks": {"percentage": 32.2}}}}
        wrapped = {"as_of_date": "2026-06-30", "data": flat}
        self.assertEqual(read_allocations(flat), {"Stocks": 32.2})
        self.assertEqual(read_allocations(wrapped), {"Stocks": 32.2})

    def test_read_allocation_values_unwraps_snapshot_data_key(self):
        flat = {"ASSET_ALLOCATION": {"allocations": {"Stocks": {"value": 50723.0, "percentage": 32.2}}}}
        wrapped = {"as_of_date": "2026-06-30", "data": flat}
        self.assertEqual(read_allocation_values(flat), {"Stocks": 50723.0})
        self.assertEqual(read_allocation_values(wrapped), {"Stocks": 50723.0})

    def test_read_net_worth_unwraps_snapshot_data_key(self):
        flat = {"ASSET_ALLOCATION": {"net_worth": 157781, "allocations": {}}}
        wrapped = {"as_of_date": "2026-06-30", "data": flat}
        self.assertEqual(read_net_worth(flat), 157781.0)
        self.assertEqual(read_net_worth(wrapped), 157781.0)
        self.assertEqual(read_net_worth({}), 0.0)

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


class TestDerivations(unittest.TestCase):
    BEFORE = {"Stocks": 38.55, "Cash": 0.80, "Bonds": 21.59}
    AFTER = {"Stocks": 32.20, "Cash": 6.30, "Bonds": 24.00}
    # Dollar values consistent with the percentages above on a ~100k base -
    # Stocks has the largest |$delta| here too, same winner as by pp.
    BEFORE_VALUES = {"Stocks": 38550.0, "Cash": 800.0, "Bonds": 21590.0}
    AFTER_VALUES = {"Stocks": 32200.0, "Cash": 6300.0, "Bonds": 24000.0}
    NET_WORTH = 100000.0

    def test_allocation_rows_mapped_and_sorted(self):
        rows = build_allocation_rows(self.BEFORE, self.AFTER)
        self.assertEqual(
            [row.name for row in rows], ["Акції IBKR", "Облігації", "Кеш"]
        )
        self.assertEqual(rows[0].before_pct, 38.55)
        self.assertEqual(rows[0].after_pct, 32.20)

    def test_quarter_month_range(self):
        self.assertEqual(
            _quarter_month_range_uk(datetime(2026, 4, 1)),
            "Квітень – Червень 2026 року",
        )
        self.assertEqual(
            _quarter_month_range_uk(datetime(2026, 1, 15)),
            "Січень – Березень 2026 року",
        )
        self.assertEqual(
            _quarter_month_range_uk(datetime(2026, 12, 31)),
            "Жовтень – Грудень 2026 року",
        )

    def test_find_main_change_picks_largest_abs_delta(self):
        # Stocks has the largest |$delta| (-6350), ahead of Cash (+5500) and
        # Bonds (+2410); the returned figure is still the pp delta (-6.35).
        nominative, genitive, delta = find_main_change(
            self.BEFORE,
            self.AFTER,
            self.BEFORE_VALUES,
            self.AFTER_VALUES,
            self.NET_WORTH,
        )
        self.assertEqual(nominative, "Акції IBKR")
        self.assertEqual(genitive, "акцій IBKR")
        self.assertAlmostEqual(delta, -6.35, places=2)

    def test_find_main_change_prefers_dollar_over_pp_when_they_disagree(self):
        # "Trivial" has the larger pp delta (0.50 vs 0.40) but a tiny dollar
        # move; "Material" has the smaller pp delta but the real money move.
        # This mirrors the live report: Crypto Lending and Crypto Coins both
        # moved ~0.4pp this quarter, but Crypto Lending's actual move was
        # $48 (net worth itself shrank) versus Crypto Coins' real $891 move.
        before_pct = {"Trivial": 5.0, "Material": 10.0}
        after_pct = {"Trivial": 5.5, "Material": 10.4}
        before_value = {"Trivial": 1000.0, "Material": 50000.0}
        after_value = {"Trivial": 1010.0, "Material": 55000.0}
        nominative, _, delta_pct = find_main_change(
            before_pct, after_pct, before_value, after_value, net_worth=100000.0
        )
        self.assertEqual(nominative, "Material")
        self.assertAlmostEqual(delta_pct, 0.4, places=2)

    def test_find_main_change_below_materiality_threshold_returns_none(self):
        # $300 move on a $100,000 portfolio is 0.3% of net worth, below the
        # default 1% materiality threshold - nothing significant happened.
        result = find_main_change(
            {"Cash": 1.0},
            {"Cash": 1.3},
            {"Cash": 1000.0},
            {"Cash": 1300.0},
            net_worth=100000.0,
        )
        self.assertIsNone(result)

    def test_find_main_change_empty(self):
        self.assertIsNone(find_main_change({}, {}, {}, {}, net_worth=0.0))

    def test_find_main_change_breaks_exact_ties_deterministically(self):
        # Bonds and Cash both move by exactly +5000 - without a tie-break,
        # set iteration order (affected by hash randomization) could pick a
        # different "winner" on different runs of the same input.
        before_pct = {"Bonds": 20.0, "Cash": 20.0}
        after_pct = {"Bonds": 20.0, "Cash": 20.0}
        before_value = {"Bonds": 10000.0, "Cash": 20000.0}
        after_value = {"Bonds": 15000.0, "Cash": 25000.0}
        result = find_main_change(
            before_pct, after_pct, before_value, after_value, net_worth=100000.0
        )
        self.assertEqual(result[0], "Кеш")

    def test_kpis_main_change_card(self):
        kpis = build_kpis(-6.8, 9.3, main_change=("Кеш", "кешу", 5.20))
        self.assertEqual(len(kpis), 4)
        self.assertEqual(kpis[3].label, "Головна зміна: частка кешу")
        self.assertEqual(kpis[3].value, "+5,2%")
        self.assertEqual(kpis[3].tone, "pos")

    def test_kpis_spread(self):
        kpis = build_kpis(-6.8433, 9.3445)
        self.assertEqual(len(kpis), 3)  # no main_change -> no 4th card
        self.assertEqual(kpis[0].value, "−6.8%")
        self.assertEqual(kpis[1].value, "+9.3%")
        self.assertEqual(kpis[2].value, "−16,2%")
        self.assertIn("Відставання", kpis[2].label)
        outperform = build_kpis(5.0, 3.0)
        self.assertIn("Випередження", outperform[2].label)
        self.assertEqual(outperform[2].value, "+2,0%")

    def test_footnotes_excluded_share(self):
        after = {
            "Other Bets": 13.8,
            "Crypto Lending": 11.5,
            "Crypto Coins": 2.3,
            "P2P Lending": 1.3,
            "Stocks": 32.2,
        }
        footnotes = build_footnotes(after)
        self.assertEqual(len(footnotes), 2)
        self.assertIn("(~29% капіталу)", footnotes[1])
        self.assertEqual(len(build_footnotes({"Stocks": 100.0})), 1)


if __name__ == "__main__":
    unittest.main()
