---
name: quarterly-report
description: Generate or troubleshoot quarterly investment reports from IBKR Flex exports and saved portfolio pipeline data, preserving the established styled HTML for publication and supplementary Markdown tables.
---

# Quarterly portfolio report

Deliver the styled `portfolio_yic_reports/portfolio_report_qN_YYYY.html` as the primary report. `portfolio_report_YYYY_qN.md` is a supplementary table export. Reuse the approved design in `portfolio_yic_reports/quarterly_report_html.py`: paper background, serif headings, navy weight bars, activity badges, colored P/L, and print CSS. Change the design only when requested. If presentation looks wrong, check which artifact was opened before changing CSS.

The user excludes four detailed sections from community reports: `Криптокредитування`, `Earn rewards (volatile)`, `Активні автомобілі`, and `P2P`. Omit them even when their source data is complete; do not restore them unless explicitly requested. Keep the `Криптовалюти` detail table and the corresponding categories in the overall asset-allocation comparison. Enforce this in `build_alternative_asset_tables()` in `generate_quarterly_report.py` and verify their absence in the final artifact. This is a presentation choice; retain the underlying pipeline data.

Style the public crypto table like the IBKR positions, preserving activity badges and weight bars. Use only three columns (`Позиція`, `Зміна кількості монет`, `Вага (криптовалюти)`). Never expose private USD holding values or absolute coin quantities, including hidden markup. Quantity change compares boundary balances; it is not profit or evidence of a buy/sell when transaction coverage is partial. Weight uses the saved total `Crypto Coins` allocation, including dust, not just displayed rows. Keep a short note explaining quantity and weight. Do not show price change, position-value growth, profit columns, empty profit cells, or placeholder notices. Preserve unknown cost basis and profit as null in private `data/crypto_cost_basis_inputs_q3_2026.json` for this report; preserve any later user-provided values and provenance. A populated private field does not authorize publication. For Binance, collect executed trade history including quantity, quote quantity, price and commissions through the existing API credentials, retaining evidence under local-only `data/`. Confirm full acquisition/disposal, rewards and transferred-asset basis coverage before calculating remaining-position cost basis; a partial set of spot pairs or average of purchases is insufficient. Never substitute unit-price change or total-value growth for profit. The report consumes saved pipeline data and must not call Binance itself.

USD1 is a cash equivalent, including Spot and Earn principal, and must not appear in crypto positions, crypto performance, or crypto lending. Use the shared classification in `src/portfolio_ledger/contract.py`; do not add an independent ticker list in the report. For cached historical data use `reclassify_cash_equivalents()` to move its saved value into Cash, preserve net worth and manual corrections, update dependent percentages/history/Sheets, and verify repeat application is a no-op. Keep raw ledger and original snapshot backups. Failed balance sources must preserve cached USD1 cash with partial quality, without counting it twice. Do not recompute historical returns from incomplete flows; mark affected crypto returns unavailable.

## Establish the reporting period and inputs

Use the requested year/quarter, deriving it from context only when unambiguous. Inspect available inputs before fetching or regenerating anything.

- Positions: `data/ib_flex_snapshots/stocks_count_trades_<toDate>_<timestamp>.xml`. Baseline is the previous quarter's last business day; closing positions are the requested quarter's last business day. Inspect XML dates, not filenames alone.
- Trades: `data/ib_flex_snapshots/trades_<toDate>_<timestamp>.xml`, spanning the requested quarter's first through last calendar day. Check `fromDate`, `toDate`, record counts, and presence of sell trades for closed-position exit prices/P/L.
- Combined data: dated `data/snapshots/combined_data_*.json` from `just run`. Validate the envelope's `as_of_date`, populated `ASSET_ALLOCATION`, usable `IB_PERFORMANCE`/`INDEX_PERFORMANCE`, and requested `ACTIVITY_DATA.quarters` key when rendering activity tables.

`load_portfolios()` allows +/-3 days for positions and loose month matching for trades; successful generation does not prove quarter-close inputs. For a final community report, require exact boundaries. An explicitly requested interim report can use nearby exports if the actual dates and limitations are visible. Zero trades can be legitimate; a missing trades export must not be interpreted as no trading.

## Collect only missing inputs

Collection belongs to this project's `.github/workflows/flex-snapshot.yml`. Its scheduled run on the first day of Jan/Apr/Jul/Oct at 06:00 UTC fetches both queries. Verify actual run/job/step status and artifacts; cron configuration or overall success alone is insufficient. Inspect the workflow's current conditions: manual dispatch currently skips quarterly trades. The workflow's Telegram step reports job status, not portfolio-report publication.

- If given a run URL, inspect that exact run and download its named artifact directly: `gh run download "$REPORT_RUN_ID" --name "flex-snapshot-$REPORT_RUN_ID" --dir data/ib_flex_snapshots`, after resolving `REPORT_RUN_ID` from the URL.
- Otherwise use `just fetch-snapshots` to download recent CI artifacts. This recipe suppresses download failures and may create nested artifact folders; inspect downloaded XML and ensure validated exports are in the top-level directory searched by `load_portfolios()`. Preserve earlier exports; compare contents before replacing an existing name.
- For a missing export, use `IBFlexPortfolioFetcher` in `src/brokers/ib_flex_portfolio.py`. Load local credentials with `src.portfolio_sync._load_local_env_file()`; never print credentials or raw request URLs. Positions query: `1188471`, `LastBusinessDay`. Trades query: `1575659`, `LastQuarter`. Prefer configured query IDs, with these documented IDs as a fallback when appropriate.

Example for missing quarterly trades, using the existing collector:

```python
import os
from src.portfolio_sync import _load_local_env_file
from src.brokers.ib_flex_portfolio import IBFlexPortfolioFetcher

_load_local_env_file()
query_id = os.getenv("IB_FLEX_QUERY_ID_QUARTERLY_TRADES") or "1575659"
path = IBFlexPortfolioFetcher(query_id=query_id).fetch_and_save(
    "data/ib_flex_snapshots", filename_prefix="trades"
)
print(path)
```

For missing positions, use the same collector with `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` (documented ID `1188471`) and the default filename prefix. Both query periods roll forward: re-fetching later cannot reconstruct an older close. Recheck returned XML dates. If closing exports are not yet available, prepare the input checklist and report the missing boundary rather than silently substituting an interim export. Create a monitor only when requested.

## Preserve the single source of truth

`just run` writes current `data/final_data.json` and archives dated combined-data snapshots. For historical reports, use matching dated snapshots for both "Було" and "Стало". Do not rerun a live pipeline to recreate an old close or replace missing historical metrics with today's data. The report never re-fetches or recomputes TWR, benchmarks, or income, and never reads the raw ledger.

- "Було" comes from the previous quarter's close. `select_before_snapshot()` skips snapshots without allocations and allows five days of grace; check the selected as-of date rather than accepting it blindly.
- "Стало" comes from the reporting quarter's close. `select_after_snapshot()` prefers a snapshot carrying the requested activity quarter but can fall back. Check allocations and activity quarter explicitly.
- If automatic selection is wrong, pass verified `--before PATH` / `--after PATH`. A documented backfill is acceptable when grounded in real boundary values; never invent missing history.
- Core/Satellite and China/rest splits follow `CORE_SYMBOLS` and `CHINA_EQUITY_SYMBOLS` in `analyze_portfolio_reports.py`; allocation translations follow `CATEGORY_UK` in `generate_quarterly_report.py`.
- Keep ticker sets, FX rates, and hardcoded prices in `analyze_portfolio_reports.py`. Review `HARDCODED_ENTRY_PRICES`, `HKD_TO_USD_RATE`, and any share adjustments; change stale adjustments only with supporting export evidence.
- Disclose partial crypto coverage, missing prices, manual savings inputs, or missing metrics. Preserve coverage markers and unavailable values. IBKR/benchmark KPIs are YTD; position P/L is cost-basis or exit-price based, not a standalone quarterly return. Existing position P/L excludes commissions, dividends, and FX.

## Generate and verify

```bash
just report YEAR QUARTER
```

The HTML generator also accepts `--before`, `--after`, `--output`, and `--open`. `--ibkr-ytd` / `--sp500-ytd` overrides require a verified source, not guessed values. These options belong to `generate_quarterly_report.py`, not the `just report` recipe; regenerate HTML directly if explicit snapshot paths are needed.

Before delivery:

1. Check both output files exist and contain the requested quarter/year. Titles, footer, month range, and activity tables must follow the closing quarter, not the baseline date. For example, a June 30 baseline plus September 30 close is Q3.
2. Compare prices, weights, open/closed positions, exit prices, and P/L in HTML and Markdown with the same analyzer inputs, allowing their documented display rounding. Check allocation and YTD figures against the selected combined-data snapshots. Special-asset weights use the IBKR subset; stock weights use the equity subset.
3. Confirm the HTML remains self-contained: no external resources, scripts, imports, or linked stylesheets. Check that the approved visual elements remain present; unchanged CSS alone does not prove rendering quality.
4. Open the styled HTML in an allowed preview/browser when supported and inspect the rendered tables, badges, bars, P/L colors, overflow, and spacing. For distribution PDF, inspect print output too. If preview is blocked or unavailable, deliver the HTML with visual/print checks marked unverified. Respect browser security policy; do not bypass it or substitute Markdown as proof of the styled result.
5. When generator code changes, reproduce the defect before fixing and run the relevant checks. `just test` covers report behavior; focused files include `tests/test_quarterly_report_html.py` and `tests/test_quarterly_report_period.py` when present. Reusing verified generators does not require rerunning unrelated tests for every report.

## Deliver

Lead with a clickable link to the styled HTML, and PDF if actually produced and checked. Open the styled artifact when the available viewer renders it; retain Markdown as a secondary link or omit it unless useful. Never open only Markdown and present that as the publication result.

State the quarter, actual input dates, validation obtained, and material data-quality or visual-review limits. Keep provenance receipts under local-only `data/` when useful; preserve private inputs and existing report history. Generate locally within the user's request. Publishing or sending the report to Telegram requires explicit authorization.
