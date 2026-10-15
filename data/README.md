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
- `fire_eligible_categories`: list of categories included in the FIRE asset total.
- `essential_monthly_spending_usd`: positive monthly essential spending amount.
- `liabilities_usd`: known liability total; use `0` only when zero liabilities are confirmed.
- `cash_available_now_usd`, `assets_for_sale_usd`, and `restricted_assets_usd`: explicit liquidity classifications.

Omitted settings remain unavailable or unconfigured. The insight refresh reads
the existing `combined_data` snapshot and does not make additional broker calls.
Do not put credentials, account identifiers, or private position data in this
settings file.

## Main tab, timeline, and saved-data replay

Each valuation date has one portfolio tab (`DD Mon YYYY`). The only shared
supporting tab is `net_worth_timeline`. Same-date reruns update the same sheet
IDs. Allocation, comparison, income, liquidity, FIRE, and exposure are sections
on the main tab. Tiny holdings below USD 100 remain in expandable detail.

`refresh_from_snapshot(spreadsheet, snapshot_path, config_path=None,
snapshot_dir="data/snapshots", *, adoptions=None, dry_run=False)` replays a saved
snapshot without broker access. Its envelope date determines the main tab,
comparison cutoff, and timeline entry. The live updater also accepts an optional
keyword-only `valuation_date`; absent dates stop before any write.

Existing unmarked tabs require explicit adoption. First inspect the exact sheet
ID, source chart ranges, and generated regions. Call
`preview_adoption(worksheet, ranges, history_chart_id=None)` from
`src.google_sheets.insights_writer`; ranges are zero-based
`[start_row, end_row, start_column, end_column]`, with exclusive ends. Review its
occupied cells and ranges, then pass the unchanged receipt as
`adoptions={worksheet.id: receipt}`. A stale receipt or occupied cells outside
the approved regions blocks the whole update. Never include user notes in an
approved range. Optional `history_chart_id` explicitly adopts the reviewed
history chart; other charts, including Deployed Capital, remain untouched.

For a legacy main tab include all reviewed generated cells (normally columns
A:L), not only the new layout. For the legacy timeline approve the existing
date/value region in A:B; E:F must be empty or explicitly reviewed because it
holds sorted chart data. AC1:AC2 are reserved metadata cells. No historical or
thematic tabs are deleted and no suffixed copies are created.

`dry_run=True` validates both destinations and returns the proposed tab/ID
receipt without writes. Validate a synthetic test workbook and review it before
production writeback. Keep adoption receipts, snapshots, credentials, and local
configuration out of Git. Financial replay parity assumes the same snapshot
and configuration; source freshness is correctly labelled Cached on replay.
