# Local portfolio data

This directory is intentionally local-only.

Keep portfolio positions, generated combined data, snapshots, API keys, credentials, and account-specific configuration out of Git. A full local run expects the private files to be restored here from your own machine or backup.

Only this README is tracked so fresh clones keep the expected directory shape without exposing sensitive data.

## Portfolio insights settings

The dated Google Sheets portfolio tab can use optional local settings from
`data/insights_config.json`. That default file is ignored by Git. Set
`PORTFOLIO_INSIGHTS_CONFIG` to use a different local JSON file, and keep that
file outside tracked source.

Supported keys:

- `allocation_targets_pct`: category target weights as percentages from 0 to 100.
- `fire_target_usd`: positive FIRE target in the pipeline base currency.
- `essential_monthly_spending_usd`: positive monthly essential spending amount.
- `liabilities_usd`: known liability total; use `0` only when zero liabilities are confirmed.
- `cash_available_now_usd`, `assets_for_sale_usd`, and `restricted_assets_usd`: explicit liquidity classifications.

Omitted settings remain unavailable or unconfigured. The insight refresh reads
the existing `combined_data` snapshot and does not make additional broker calls.
Do not put credentials, account identifiers, or private position data in this
settings file.

FIRE progress uses the saved `TOTAL_ASSETS` portfolio value divided by the target.
There is no separate eligible balance or category filter. Legacy
`fire_eligible_categories` settings are ignored. Income estimates still use their
saved income principal, which may differ from market valuation.

## Main tab, timeline, and saved-data replay

Each valuation date has one portfolio tab (`DD Mon YYYY`). The only shared
supporting tab is `net_worth_timeline`. Same-date reruns update the same sheet
IDs. The tab is compact-only: allocation, balance changes, receipts, liquidity,
FIRE detail, exposure views, full holdings, benchmarks, and methodology
sections are no longer generated.

The view keeps the original four zones: FIRE and performance on the left,
holdings grouped by asset category in the middle, and portfolio
totals/allocation plus estimated income on the right. Holdings show asset,
USD value and unrealized P&L percentage. Neutral grey headers replace blue;
numeric P&L cells use the original red/white/green conditional gradient
(-30%, 0%, +50%). Headers are in row 2; columns through the asset names are
frozen. No Details section, row group, or basic filter is written; a tab that
carries one from an earlier generator frame has it removed on the next
refresh. Asset values and allocation weights omit redundant plus signs;
balance changes and returns keep explicit signs.

`refresh_from_snapshot(spreadsheet, snapshot_path, config_path=None,
snapshot_dir="data/snapshots", *, adoptions=None, dry_run=False)` replays a saved
snapshot without broker access. Its envelope date determines the main tab,
comparison cutoff, and timeline entry. The live updater also accepts an optional
keyword-only `valuation_date`; absent dates stop before any write.

Existing unmarked main tabs require explicit adoption. First inspect the exact
sheet ID and generated regions. Call
`preview_adoption(worksheet, ranges)` from
`src.google_sheets.insights_writer`; ranges are zero-based
`[start_row, end_row, start_column, end_column]`, with exclusive ends. Review its
occupied cells and ranges, then pass the unchanged receipt as
`adoptions={worksheet.id: receipt}`. A stale receipt or occupied cells outside
the approved regions blocks the whole update. Never include user notes in an
approved range.

For a legacy main tab include all reviewed generated cells (normally columns
A:L), not only the new layout. AC1:AC2 are reserved metadata cells on the main
tab. The existing `net_worth_timeline` keeps its legacy configuration: A is value,
B is date. Same-date updates change only A; new dates append an A:B entry using
the snapshot date. No adoption, ownership metadata, helper columns, chart edits
or formatting changes apply to that tab. If missing, it is created with the
legacy two-column layout. Existing helper data/charts from earlier previews
are left intact; any cleanup is separate. No historical or thematic tabs are
deleted and no suffixed copies are created.

`dry_run=True` validates both destinations and returns the proposed tab/ID
receipt without writes. The CLI defaults to dry-run: live writeback requires the
explicit `--write` flag (`--write` and `--dry-run` are mutually exclusive).
Validate a synthetic test workbook and review it before production writeback.
`just adoption-apply` performs a dry run; `just adoption-apply-live` writes.
Keep adoption receipts, snapshots, credentials, and local configuration out of
Git. Financial replay parity assumes the same snapshot and configuration;
source freshness is correctly labelled Cached on replay.

## Portfolio ledger

`just run` incrementally imports available exchange activity. An explicit range can be synced with:

```bash
just crypto-sync from=2026-04-01 to=2026-06-30 --source binance --dry-run
```

Private files live under `data/portfolio_ledger/`:

- `crypto/imported_events.jsonl` - API events, deduplicated by `source + account + remote_id`.
- `crypto/manual_events.csv` - manual Telegram, cold-storage, transfer, and correction events with a stable `event_id`.
- `crypto/import_state.json` - incremental API cursors.
- `crypto/sources.json` - optional API import configuration, for example `{"binance":{"symbols":["BTCUSDT","ETHUSDT"]}}`.
- `other_assets/assets.csv` - `asset_id,name,status,purchase_date,legacy_carrying_value_usd`.
- `other_assets/events.csv` - `event_id,asset_id,occurred_at,event_type,amount,currency,fx_rate_to_usd,amount_usd`.
- `other_assets/valuations.csv` - `asset_id,as_of_date,value_usd`.
- `p2p/positions.csv` - `account,balance_usd,as_of_date,status,closed_at`.

Manual crypto columns are `event_id,occurred_at,source,account,event_type,asset,quantity,quote_asset,quote_quantity,usd_value,amount_usd,fee_asset,fee_quantity,fee_usd,from_location,to_location,remote_id,fx_rate_to_usd`. Raw ledger files remain ignored and must not be copied to Sheets or generated HTML.
