#!/usr/bin/env python3

"""
Institutional-style HTML renderer for the quarterly portfolio report.

Pure presentation layer: takes structured ReportData and returns a complete,
self-contained HTML document (inline CSS, no JS, no external resources).
The visual design follows the approved "hedge fund letter" style: paper
background, serif headings, hairline rules, navy accent, KPI cards, inline
weight bars, badge pills, and print-ready CSS.
"""

import html
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MINUS = "−"  # typographic minus used throughout the report


@dataclass
class KpiCard:
    label: str
    value: str
    tone: str  # "pos" | "neg" | "navy"
    caption: str = ""
    purpose: str = ""


@dataclass
class AllocationRow:
    name: str
    before_pct: float
    after_pct: float


@dataclass
class PositionRow:
    symbol: str
    kind: str  # "new" | "increased" | "decreased" | "unchanged" | "closed"
    activity_text: str
    price_text: str
    weight_pct: Optional[float] = None  # open positions: numeric weight (bar)
    weight_text: Optional[str] = None  # closed positions: e.g. "4.81% → 0%"
    pl_pct: Optional[float] = None  # None hides the P/L cell


@dataclass
class DetailTable:
    title: str
    headers: List[str]
    rows: List[List[str]]
    note: Optional[str] = None
    position_rows: List[PositionRow] = field(default_factory=list)
    show_price_column: bool = True
    show_pl_column: bool = True


@dataclass
class ReportData:
    period_title: str  # e.g. "2-й квартал 2026 року"
    quarter_label: str  # e.g. "Q2"
    year_label: str  # e.g. "2026"
    kpis: List[KpiCard]
    footnotes: List[str]
    allocation_rows: List[AllocationRow]
    stock_rows: List[PositionRow]
    core_satellite: Tuple[float, float]
    china_rest: Tuple[float, float]
    special_asset_rows: List[PositionRow] = field(default_factory=list)
    alternative_asset_tables: List[DetailTable] = field(default_factory=list)
    summary_title: str = "Коротко за квартал"
    holy_grail: Optional[dict] = None
    diversification: Optional[dict] = None


CSS = """
:root {
  --paper: #FBFAF7;
  --card: #FFFFFF;
  --ink: #1A2532;
  --navy: #1F3A5F;
  --navy-soft: #B9C4D1;
  --muted: #64707D;
  --hairline: #E4E1D8;
  --track: #ECE9E0;
  --green: #1A7A4E;
  --red: #B03A2E;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--paper);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}
.page { max-width: 920px; margin: 0 auto; padding: 56px 40px 64px; }

/* ---------- Masthead ---------- */
.masthead {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 24px;
  padding-bottom: 22px;
  border-bottom: 1px solid var(--ink);
  position: relative;
}
.masthead::after {
  content: "";
  position: absolute;
  left: 0; right: 0; bottom: -4px;
  border-bottom: 1px solid var(--hairline);
}
h1 {
  font-family: "Iowan Old Style", "Palatino", Georgia, "Times New Roman", serif;
  font-size: 40px;
  line-height: 1.1;
  font-weight: 600;
  margin: 0 0 6px;
  letter-spacing: 0.005em;
}
.subtitle { font-size: 14px; color: var(--muted); }
.period {
  text-align: right;
  font-family: "Iowan Old Style", "Palatino", Georgia, serif;
  color: var(--navy);
  flex: none;
}
.period .q { font-size: 34px; font-weight: 600; line-height: 1; display: block; }
.period .y { font-size: 15px; letter-spacing: 0.12em; }

/* ---------- Sections ---------- */
section { margin-top: 48px; }
.sec-label {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 6px;
}
.sec-num {
  font-family: "Iowan Old Style", "Palatino", Georgia, serif;
  font-size: 14px;
  color: var(--navy);
  letter-spacing: 0.06em;
}
.sec-title {
  font-family: "Iowan Old Style", "Palatino", Georgia, serif;
  font-size: 23px;
  font-weight: 600;
  margin: 0;
}
.sec-rule { flex: 1; border-bottom: 1px solid var(--hairline); transform: translateY(-6px); }
h3 {
  font-family: "Iowan Old Style", "Palatino", Georgia, serif;
  font-size: 18px;
  font-weight: 600;
  margin: 30px 0 4px;
}

/* ---------- KPI cards ---------- */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}
.kpi-card {
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--hairline);
  border-top: 3px solid var(--navy);
  border-radius: 3px;
  padding: 17px 14px 15px;
  min-width: 0;
}
.kpi-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
  margin-bottom: 12px;
  line-height: 1.45;
}
.kpi-purpose {
  font-size: 11px;
  font-weight: 500;
  color: var(--navy);
  line-height: 1.4;
  min-height: 2.8em;
  margin-bottom: 7px;
  white-space: pre-line;
}
.kpi-value {
  margin-top: auto;
  font-family: "Iowan Old Style", "Palatino", Georgia, serif;
  font-size: 32px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.kpi-caption {
  margin-top: 12px;
  min-height: 4.5em;
  font-size: 12px;
  line-height: 1.5;
  color: var(--muted);
  white-space: pre-line;
}
.pos { color: var(--green); }
.neg { color: var(--red); }
.navy { color: var(--navy); }
.footnote { font-size: 12.5px; color: var(--muted); margin-top: 14px; font-style: italic; }

/* ---------- Tables ---------- */
.table-scroll { overflow-x: auto; margin-top: 14px; }
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 13.5px;
}
th {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--ink);
  white-space: nowrap;
}
td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--hairline);
  vertical-align: middle;
}
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
th.num { text-align: right; }
.ticker { font-weight: 600; white-space: nowrap; }
tr.total td {
  border-top: 1.5px solid var(--ink);
  border-bottom: none;
  font-weight: 600;
  padding-top: 10px;
}
tr.closed-row td { color: var(--muted); }
tr.closed-row td.ticker, tr.closed-row .ticker { color: var(--muted); }
.sub { color: var(--muted); font-size: 12px; }

/* ---------- Badges ---------- */
.pill {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  padding: 2px 9px;
  border-radius: 999px;
  white-space: nowrap;
}
.pill-new { color: var(--navy); background: rgba(31, 58, 95, 0.08); border: 1px solid rgba(31, 58, 95, 0.28); }
.pill-add { color: var(--green); background: rgba(26, 122, 78, 0.08); border: 1px solid rgba(26, 122, 78, 0.28); }
.pill-cut { color: var(--red); background: rgba(176, 58, 46, 0.05); border: 1px solid rgba(176, 58, 46, 0.2); }
.pill-close { color: var(--red); background: rgba(176, 58, 46, 0.07); border: 1px solid rgba(176, 58, 46, 0.26); }
.hold { color: var(--muted); font-size: 12.5px; }

/* ---------- Inline weight bars ---------- */
.wcell { display: flex; align-items: center; justify-content: flex-end; gap: 9px; }
.wbar {
  width: 72px; height: 5px;
  background: var(--track);
  border-radius: 2px;
  overflow: hidden;
  flex: none;
}
.wbar i { display: block; height: 100%; background: var(--navy); border-radius: 2px; }
.wval { min-width: 52px; text-align: right; font-variant-numeric: tabular-nums; }

/* ---------- Allocation paired bars ---------- */
td.bars { width: 170px; }
.bar {
  display: block;
  height: 4px;
  background: var(--track);
  border-radius: 2px;
  margin: 3px 0;
  min-width: 150px;
}
.bar i { display: block; height: 100%; border-radius: 2px; }
.bar.was i { background: var(--navy-soft); }
.bar.now i { background: var(--navy); }
.chip { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }

/* ---------- Split bars ---------- */
.split { margin-top: 18px; }
.split-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 13px;
  margin-bottom: 6px;
}
.split-head .v { font-weight: 600; font-variant-numeric: tabular-nums; }
.split-bar { display: flex; height: 8px; border-radius: 2px; overflow: hidden; background: var(--track); }
.split-bar .a { background: var(--navy); }
.split-bar .b { background: var(--navy-soft); }

/* ---------- Callouts ---------- */
/* ---------- Footer ---------- */
footer {
  margin-top: 56px;
  padding-top: 14px;
  border-top: 1px solid var(--hairline);
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

/* ---------- Responsive ---------- */
@media (max-width: 720px) {
  .page { padding: 32px 18px 48px; }
  h1 { font-size: 30px; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .masthead { flex-direction: column; align-items: flex-start; }
  .period { text-align: left; }
}

/* ---------- Print ---------- */
@page { margin: 16mm 14mm; }
@media print {
  body { background: #fff; }
  .page { max-width: none; padding: 0; }
  .kpi-card, .table-scroll, .split { break-inside: avoid; }
  section { margin-top: 32px; }
}
"""

_PILL_CLASS = {
    "new": "pill pill-new",
    "increased": "pill pill-add",
    "decreased": "pill pill-cut",
    "closed": "pill pill-close",
}


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _fmt_pct2(value: float) -> str:
    return f"{value:.2f}%"


def _fmt_signed_pct1(value: float) -> str:
    sign = "+" if value > 0 else (MINUS if value < 0 else "")
    return f"{sign}{abs(value):.1f}%"


def _fmt_signed_pct2(value: float) -> str:
    sign = "+" if value > 0 else (MINUS if value < 0 else "")
    return f"{sign}{abs(value):.2f}%"


def _bar_width(value: float, max_value: float) -> str:
    if max_value <= 0 or value <= 0:
        return "0%"
    return f"{value / max_value * 100:.1f}%"


def _activity_cell(row: PositionRow) -> str:
    if row.kind == "unchanged":
        return f'<span class="hold">{_esc(row.activity_text)}</span>'
    pill_class = _PILL_CLASS[row.kind]
    return f'<span class="{pill_class}">{_esc(row.activity_text)}</span>'


def _weight_cell(row: PositionRow, max_weight: float) -> str:
    if row.weight_pct is not None:
        width = _bar_width(row.weight_pct, max_weight)
        return (
            '<span class="wcell">'
            f'<span class="wbar"><i style="width:{width}"></i></span>'
            f'<span class="wval">{_fmt_pct2(row.weight_pct)}</span>'
            "</span>"
        )
    return _esc(row.weight_text or "-")


def _pl_cell(pl_pct: Optional[float], precision: int = 1) -> str:
    if pl_pct is None:
        return "<td></td>"
    tone = "pos" if pl_pct > 0 else ("neg" if pl_pct < 0 else "")
    tone_class = f" {tone}" if tone else ""
    value = _fmt_signed_pct2(pl_pct) if precision == 2 else _fmt_signed_pct1(pl_pct)
    return f'<td class="num{tone_class}">{value}</td>'


def _render_kpis(kpis: List[KpiCard]) -> str:
    cards = []
    for kpi in kpis:
        purpose = (
            f'<div class="kpi-purpose">{_esc(kpi.purpose)}</div>'
            if kpi.purpose else ""
        )
        caption = (
            f'<div class="kpi-caption">{_esc(kpi.caption)}</div>'
            if kpi.caption else ""
        )
        cards.append(
            '<div class="kpi-card">'
            f"{purpose}"
            f'<div class="kpi-label">{_esc(kpi.label)}</div>'
            f'<div class="kpi-value {kpi.tone}">{_esc(kpi.value)}</div>'
            f"{caption}"
            "</div>"
        )
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


def _render_allocation_table(rows: List[AllocationRow]) -> str:
    max_pct = max(
        (max(row.before_pct, row.after_pct) for row in rows), default=0.0
    )
    body = []
    for row in rows:
        delta = row.after_pct - row.before_pct
        arrow = "▲" if delta > 0 else "▼"
        chip_tone = "pos" if delta > 0 else "neg"
        chip = (
            f'<span class="chip {chip_tone}">{arrow} {_fmt_signed_pct2(delta)}</span>'
            if abs(delta) >= 0.005
            else '<span class="chip">-</span>'
        )
        body.append(
            "<tr>"
            f"<td>{_esc(row.name)}</td>"
            f'<td class="num">{_fmt_pct2(row.before_pct)}</td>'
            f'<td class="num">{_fmt_pct2(row.after_pct)}</td>'
            '<td class="bars">'
            f'<span class="bar was"><i style="width:{_bar_width(row.before_pct, max_pct)}"></i></span>'
            f'<span class="bar now"><i style="width:{_bar_width(row.after_pct, max_pct)}"></i></span>'
            "</td>"
            f'<td class="num">{chip}</td>'
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Клас активів</th>"
        '<th class="num">Було</th>'
        '<th class="num">Стало</th>'
        "<th>Було → Стало</th>"
        '<th class="num">Зміна, %</th>'
        f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def _render_stock_table(rows: List[PositionRow]) -> str:
    max_weight = max(
        (row.weight_pct for row in rows if row.weight_pct is not None), default=0.0
    )
    body = []
    for row in rows:
        row_class = ' class="closed-row"' if row.kind == "closed" else ""
        body.append(
            f"<tr{row_class}>"
            f'<td class="ticker">{_esc(row.symbol)}</td>'
            f"<td>{_activity_cell(row)}</td>"
            f'<td class="num">{_weight_cell(row, max_weight)}</td>'
            f'<td class="num">{_esc(row.price_text)}</td>'
            f"{_pl_cell(row.pl_pct)}"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Позиція</th>"
        "<th>Остання активність</th>"
        '<th class="num">Вага</th>'
        '<th class="num">Середня ціна</th>'
        '<th class="num">P/L</th>'
        f'</tr></thead><tbody>{"".join(body)}'
        '<tr class="total"><td>Підсумок</td><td></td>'
        '<td class="num">100.00%</td><td></td><td></td></tr>'
        "</tbody></table></div>"
    )


def _render_special_table(rows: List[PositionRow]) -> str:
    max_weight = max(
        (row.weight_pct for row in rows if row.weight_pct is not None), default=0.0
    )
    body = []
    for row in rows:
        row_class = ' class="closed-row"' if row.kind == "closed" else ""
        body.append(
            f"<tr{row_class}>"
            f'<td class="ticker">{_esc(row.symbol)}</td>'
            f"<td>{_activity_cell(row)}</td>"
            f'<td class="num">{_weight_cell(row, max_weight)}</td>'
            f'<td class="num">{_esc(row.price_text)}</td>'
            f"{_pl_cell(row.pl_pct)}"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table><thead><tr>'
        "<th>Позиція</th>"
        "<th>Остання активність</th>"
        '<th class="num">Вага (IBKR активи)</th>'
        '<th class="num">Середня ціна</th>'
        '<th class="num">P/L</th>'
        f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def _render_detail_table(table: DetailTable) -> str:
    headers = "".join(
        ('<th class="num">' if table.position_rows and index >= 2 else "<th>")
        + _esc(header) + "</th>" for index, header in enumerate(table.headers)
    )
    if table.position_rows:
        max_weight = max((row.weight_pct or 0 for row in table.position_rows), default=0)
        rows = "".join(
            '<tr' + (' class="closed-row"' if row.kind == "closed" else '') + '>'
            + f'<td class="ticker">{_esc(row.symbol)}</td>'
            + f"<td>{_activity_cell(row)}</td>"
            + f'<td class="num">{_weight_cell(row, max_weight)}</td>'
            + (f'<td class="num">{_esc(row.price_text)}</td>' if table.show_price_column else "")
            + ((_pl_cell(row.pl_pct, precision=2) if row.pl_pct is not None
                else '<td class="num">-</td>') if table.show_pl_column else "") + "</tr>"
            for row in table.position_rows
        )
    else:
        rows = "".join(
            "<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in row) + "</tr>"
            for row in table.rows
        )
    return (
        f"<h3>{_esc(table.title)}</h3>"
        '<div class="table-scroll"><table><thead><tr>'
        f"{headers}</tr></thead><tbody>{rows}</tbody></table></div>"
        + (f'<p class="footnote">{_esc(table.note)}</p>' if table.note else "")
    )


def _render_split(label: str, a_pct: float, b_pct: float) -> str:
    return (
        '<div class="split">'
        f'<div class="split-head"><span>{_esc(label)}</span>'
        f'<span class="v">{a_pct:.2f}% / {b_pct:.2f}%</span></div>'
        f'<div class="split-bar"><i class="a" style="width:{a_pct:.2f}%"></i>'
        f'<i class="b" style="width:{b_pct:.2f}%"></i></div>'
        "</div>"
    )


def _render_holy_grail(view: Optional[dict]) -> str:
    if view is None:
        return ""
    rows = "".join(f"<tr><td>{_esc(label)}</td><td>{_esc(value)}</td></tr>" for label, value in view["rows"])
    if view.get("allocation"):
        drivers = "".join(f"<li>{_esc(text)}</li>" for text in view['drivers'])
        risks = "".join(f"<li>{_esc(text)}</li>" for text in view.get('risk_facts', []))
        return f"""
<section id="holy-grail">
  <div class="sec-label"><span class="sec-num">05</span><h2 class="sec-title">{_esc(view.get('title') or 'Диверсифікація інвестованої частини')}</h2><span class="sec-rule"></span></div>
  <p class="hg-value">{_esc(view['headline'])}</p>
  <p><strong>{_esc(view['status'])}</strong></p>
  <p>{_esc(view.get('model_status', 'Модельна оцінка'))} станом на {_esc(view['as_of'])}. {_esc(view['coverage_summary'])}</p>
  <ul>{drivers}</ul>
  <ul>{risks}</ul>
  <details open><summary>Як отримано оцінку</summary>
    <table class="hg-table"><tbody>{rows}</tbody></table>
  </details>
</section>
"""
    if view.get("indicator"):
        return f"""
<section id="holy-grail">
  <div class="sec-label"><span class="sec-num">05</span><h2 class="sec-title">Диверсифікація: Holy Grail</h2><span class="sec-rule"></span></div>
  <p class="hg-value">{_esc(view['headline'])}</p>
  <p>Еквівалента джерел ризику / орієнтир 15–20.</p>
  <p>{_esc(view['status'])} станом на {_esc(view['as_of'])}.</p>
  <p class="footnote">{_esc(view['coverage_summary'])}<br>{_esc(view['principal_constraint'])}</p>
  <table class="hg-table"><tbody>{rows}</tbody></table>
</section>
"""

    return f"""
<section id="holy-grail">
  <div class="sec-label">
    <span class="sec-num">05</span>
    <h2 class="sec-title">Диверсифікація: Holy Grail</h2>
    <span class="sec-rule"></span>
  </div>
  <p class="hg-value">{_esc(view['headline'])}</p>
  <p>{_esc(view.get('count_note', 'Попередній метод'))}. Впевненість у вхідних даних: {_esc(view.get('confidence_label', '-'))}.</p>
  <p class="footnote">{_esc(view.get('critical_text', ''))}<br>{_esc(view.get('principal_constraint', ''))}<br>{_esc(view.get('headline_warning', ''))}</p>
  <p><strong>{_esc(view['effective'])}</strong> ефективних джерел дохідності / ціль 15-20</p>
  <p class="footnote">Станом на {_esc(view['as_of'])}. {_esc(view['status'])}.<br>
  Власна модель статистичної диверсифікації. Минулі кореляції не гарантують майбутньої незалежності.</p>
  <table class="hg-table"><tbody>{rows}</tbody></table>
</section>
"""


def render_report(data: ReportData) -> str:
    footnotes = "<br>\n  ".join(_esc(line) for line in data.footnotes)
    footnote_html = f'<p class="footnote">{footnotes}</p>' if data.footnotes else ""
    core_pct, satellite_pct = data.core_satellite
    china_pct, rest_pct = data.china_rest

    special_section = ""
    if data.special_asset_rows:
        special_section = (
            "\n  <h3>Облігації, золото та товарні активи</h3>\n  "
            + _render_special_table(data.special_asset_rows)
        )
    alternative_section = ""
    if data.alternative_asset_tables:
        detail_tables = "\n".join(
            _render_detail_table(table) for table in data.alternative_asset_tables
        )
        alternative_section = f"""
<section>
  <div class="sec-label">
    <span class="sec-num">04</span>
    <h2 class="sec-title">Альтернативні активи</h2>
    <span class="sec-rule"></span>
  </div>
  {detail_tables}
</section>
"""

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Квартальний звіт · {_esc(data.quarter_label)} {_esc(data.year_label)}</title>
<style>{CSS}
.hg-value {{ font-size: clamp(24px, 4vw, 38px); font-weight: 600; color: var(--navy); margin: 0 0 12px; overflow-wrap: anywhere; }}
.hg-table {{ width: 100%; table-layout: fixed; }}
.hg-table td {{ white-space: normal; overflow-wrap: anywhere; vertical-align: top; }}
.hg-table td:first-child {{ width: 43%; }}
@media print {{
  #holy-grail {{ break-before: page; }}
  .hg-table tr {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<div class="page">

<header class="masthead">
  <div>
    <h1>Квартальний звіт</h1>
    <div class="subtitle">{_esc(data.period_title)}</div>
  </div>
  <div class="period"><span class="q">{_esc(data.quarter_label)}</span><span class="y">{_esc(data.year_label)}</span></div>
</header>

<section>
  <div class="sec-label">
    <span class="sec-num">01</span>
    <h2 class="sec-title">{_esc(data.summary_title)}</h2>
    <span class="sec-rule"></span>
  </div>
  {_render_kpis(data.kpis)}
  {footnote_html}
</section>

<section>
  <div class="sec-label">
    <span class="sec-num">02</span>
    <h2 class="sec-title">Зміни в структурі сукупного портфеля</h2>
    <span class="sec-rule"></span>
  </div>
  {_render_allocation_table(data.allocation_rows)}
</section>

<section>
  <div class="sec-label">
    <span class="sec-num">03</span>
    <h2 class="sec-title">Склад і зміни портфеля IBKR</h2>
    <span class="sec-rule"></span>
  </div>

  <h3>Акції</h3>
  {_render_stock_table(data.stock_rows)}

  {_render_split("Співвідношення Core/Satellite", core_pct, satellite_pct)}
  {_render_split("Співвідношення Китай/Інші", china_pct, rest_pct)}
{special_section}
</section>

{alternative_section}

{_render_holy_grail(data.diversification or data.holy_grail)}

<footer>
  <span>Квартальний звіт · {_esc(data.quarter_label)} {_esc(data.year_label)}</span>
</footer>

</div>
</body>
</html>
"""
