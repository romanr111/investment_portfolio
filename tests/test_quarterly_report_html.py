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
            alternative_asset_tables=[
                DetailTable(
                    title="Криптовалюти",
                    headers=["Актив", "Фініш", "Coverage"],
                    rows=[["BTC", "$1,300", "complete"]],
                )
            ],
        )

    def test_report_contains_data_and_structure(self):
        html = render_report(self._report_data())
        self.assertNotIn("Portfolio Review", html)
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

    def test_report_renders_aggregated_alternative_asset_tables(self):
        html = render_report(self._report_data())

        self.assertIn("Альтернативні активи", html)
        self.assertIn("Криптовалюти", html)
        self.assertIn("$1,300", html)

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

    def test_find_main_change_picks_largest_abs_share_delta(self):
        nominative, genitive, before, after = find_main_change(self.BEFORE, self.AFTER)
        self.assertEqual(nominative, "Акції IBKR")
        self.assertEqual(genitive, "акцій IBKR")
        self.assertEqual((before, after), (38.55, 32.20))

    def test_find_main_change_tracks_new_and_removed_categories(self):
        result = find_main_change({"Cash": 20.0}, {"Bonds": 10.0})
        self.assertEqual(result, ("Кеш", "кешу", 20.0, 0.0))
        result = find_main_change({}, {"Bonds": 10.0})
        self.assertEqual(result, ("Облігації", "облігацій", 0.0, 10.0))

    def test_find_main_change_unchanged_returns_none(self):
        self.assertIsNone(find_main_change({"Cash": 20.0}, {"Cash": 20.0}))

    def test_find_main_change_empty(self):
        self.assertIsNone(find_main_change({}, {}))

    def test_find_main_change_breaks_exact_ties_deterministically(self):
        self.assertEqual(
            find_main_change({"Bonds": 20.0, "Cash": 20.0},
                             {"Bonds": 25.0, "Cash": 15.0}),
            ("Кеш", "кешу", 20.0, 15.0),
        )

    def test_kpis_main_change_card(self):
        kpis = build_kpis(
            -6.8,
            9.3,
            main_change=(
                "Інші активи (Car Resale)",
                "інших активів (Car Resale)",
                13.8, 17.9,
            ),
        )
        self.assertEqual(len(kpis), 4)
        self.assertEqual(
            kpis[3].label,
            "Частка Car Resale",
        )
        self.assertEqual(kpis[3].value, "17,9%")
        self.assertEqual(kpis[3].caption, "Було 13,8%\nна початку кварталу")
        self.assertEqual(kpis[3].tone, "navy")

    def test_kpis_spread(self):
        kpis = build_kpis(-6.8433, 9.3445)
        self.assertEqual(len(kpis), 3)  # no main_change -> no 4th card
        self.assertEqual(kpis[0].value, "−6,8%")
        self.assertEqual(kpis[1].value, "+9,3%")
        self.assertEqual(kpis[2].value, "16,2")
        self.assertEqual(kpis[2].caption, "відсоткового пункту\nз початку року")
        self.assertIn("Відставання", kpis[2].label)
        outperform = build_kpis(5.0, 3.0)
        self.assertIn("Випередження", outperform[2].label)
        self.assertEqual(outperform[2].value, "2,0")

    def test_footnotes_excluded_share(self):
        after = {
            "Other Bets": 13.8,
            "Crypto Lending": 11.5,
            "Crypto Coins": 2.3,
            "P2P Lending": 1.3,
            "Stocks": 32.2,
        }
        footnotes = build_footnotes(after)
        self.assertEqual(footnotes, [
            "Дохідність портфеля стосується лише активів на рахунку IBKR."
        ])
        self.assertEqual(len(build_footnotes({"Stocks": 100.0})), 1)

    def test_other_bets_category_explains_car_resale(self):
        rows = build_allocation_rows({}, {"Other Bets": 17.9})
        self.assertEqual(rows[0].name, "Інші активи (Car Resale)")

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

    def test_crypto_quantity_percent_and_invalid_balances(self):
        cases = [
            (1, 1.07, "+7.0%"), (2, 1, "-50.0%"),
            (1, 1, "Без змін"), (0, 1, "Нова позиція"),
            (1, 0, "Закрита позиція"), (None, 1, "Немає даних"),
            (1, None, "Немає даних"), (float("nan"), 1, "Немає даних"),
            (1, float("inf"), "Немає даних"), (-1, 1, "Немає даних"),
        ]
        for start, end, expected in cases:
            with self.subTest(start=start, end=end):
                table = build_alternative_asset_tables({"ACTIVITY_DATA": {"quarters": {
                    "2026-Q3": {"crypto": [{"asset": "X", "coverage": "partial",
                        "start_quantity": start, "end_quantity": end}]}
                }}}, "2026-Q3")[0]
                self.assertEqual(table.rows[0][1], expected)
                self.assertEqual(len(table.rows[0]), 3)
                self.assertIsNone(table.position_rows[0].pl_pct)

    def test_crypto_table_hides_nonfinite_values(self):
        table = build_alternative_asset_tables({"ACTIVITY_DATA": {"quarters": {
            "2026-Q3": {"crypto": [{"asset": "X", "coverage": "partial",
                "start_value_usd": float("nan"), "end_value_usd": float("inf")}]}
        }}}, "2026-Q3")[0]
        self.assertEqual(table.rows[0][2], "-")

    def test_crypto_activity_uses_exact_valid_quantity_boundaries(self):
        cases = [
            (0, float("inf"), "Немає даних", "unchanged"),
            (1, 1e-20, "-100.0%", "decreased"),
            (1, 0, "Закрита позиція", "closed"),
            (0, 1, "Нова позиція", "new"),
        ]
        for start, end, activity, kind in cases:
            with self.subTest(start=start, end=end):
                table = build_alternative_asset_tables({"ACTIVITY_DATA": {"quarters": {
                    "2026-Q3": {"crypto": [{"asset": "X", "coverage": "partial",
                        "start_quantity": start, "end_quantity": end,
                        "start_value_usd": 0, "end_value_usd": 100}]}
                }}}, "2026-Q3")[0]
                self.assertEqual(table.rows[0][1], activity)
                self.assertEqual(table.position_rows[0].kind, kind)

    def test_crypto_positions_use_ibkr_table_style(self):
        payload = {
            "ASSET_ALLOCATION": {"allocations": {"Crypto Coins": {"value": 1000}}},
            "ACTIVITY_DATA": {"quarters": {"2026-Q3": {"crypto": [
                {"asset": "BTC", "start_value_usd": 300, "end_value_usd": 600,
                 "start_quantity": 1, "end_quantity": 2, "coverage": "partial"},
                {"asset": "ETH", "start_value_usd": 500, "end_value_usd": 350,
                 "start_quantity": 2, "end_quantity": 1, "coverage": "complete"},
                {"asset": "NEW", "start_value_usd": 0, "end_value_usd": 50,
                 "start_quantity": 0, "end_quantity": 1, "coverage": "partial"},
            ]}}},
        }
        table = build_alternative_asset_tables(payload, "2026-Q3")[0]
        self.assertEqual(table.headers, ["Позиція", "Зміна кількості монет",
            "Вага (криптовалюти)"])
        self.assertEqual([row[2] for row in table.rows], ["60.00%", "35.00%", "5.00%"])
        data = ReportData(
            period_title="Q3", quarter_label="Q3", year_label="2026",
            kpis=[], footnotes=[], allocation_rows=[], stock_rows=[],
            core_satellite=(0, 100), china_rest=(0, 100),
            alternative_asset_tables=[table],
        )
        html = render_report(data)
        self.assertIn('class="wbar"', html)
        self.assertIn('class="pill pill-add">+100.0%', html)
        self.assertIn('class="pill pill-cut">-50.0%', html)
        self.assertIn('class="pill pill-new">Нова позиція', html)
        self.assertIsNone(table.position_rows[0].pl_pct)
        self.assertIn("Неповна історія операцій: BTC, NEW", html)

    def test_alternative_asset_tables_omit_unrequested_sections(self):
        after_data = {
            "POSITION_DATA": {
                "crypto_lending": [
                    {
                        "asset": "USDT",
                        "principal_usd": 1000,
                        "expected_apy": 0.05,
                    }
                ],
                "other_assets": [
                    {
                        "name": "Ioniq 5",
                        "status": "active",
                        "carrying_value_usd": 22000,
                        "capitalized_cost_usd": 22000,
                        "coverage": "complete",
                    }
                ],
                "p2p": [
                    {
                        "account": "EstateGuru",
                        "balance_usd": 0,
                        "status": "closed",
                        "as_of_date": "2026-06-30",
                    }
                ],
            },
            "ACTIVITY_DATA": {
                "quarters": {
                    "2026-Q2": {
                        "crypto": [
                            {
                                "asset": "BTC",
                                "start_value_usd": 1000,
                                "buys_usd": 200,
                                "sells_usd": 0,
                                "rewards_usd": 10,
                                "net_change_quantity": 0.01,
                                "end_value_usd": 1300,
                                "status": "increased",
                                "coverage": "complete",
                            },
                            {
                                "asset": "ETH",
                                "start_value_usd": 500,
                                "buys_usd": None,
                                "sells_usd": None,
                                "rewards_usd": None,
                                "net_change_quantity": 0.2,
                                "end_value_usd": 700,
                                "status": "increased",
                                "coverage": "partial",
                            },
                        ],
                        "crypto_lending": {
                            "end_principal_usd": 1000,
                            "deposits_usd": 100,
                            "withdrawals_usd": 0,
                            "income_usd": 20,
                            "return_pct": 2.0,
                            "coverage": "complete",
                            "volatile_rewards": [
                                {
                                    "asset": "BTC",
                                    "quantity": 0.001,
                                    "usd_value": 60,
                                    "coverage": "complete",
                                }
                            ],
                        },
                        "sold_cars": [],
                    }
                }
            },
        }

        tables = build_alternative_asset_tables(after_data, "2026-Q2")

        crypto = next(table for table in tables if table.title == "Криптовалюти")
        self.assertEqual([table.title for table in tables], ["Криптовалюти"])
        self.assertEqual(len(crypto.rows[0]), 3)
        self.assertIn("Неповна історія операцій: ETH", crypto.note)
        self.assertNotIn("Купівлі", crypto.headers)


if __name__ == "__main__":
    unittest.main()
