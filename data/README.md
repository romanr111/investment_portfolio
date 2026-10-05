# Local portfolio data

This directory is intentionally local-only.

Keep portfolio positions, generated combined data, snapshots, API keys, credentials, and account-specific configuration out of Git. A full local run expects the private files to be restored here from your own machine or backup.

Only this README is tracked so fresh clones keep the expected directory shape without exposing sensitive data.

## Portfolio insights settings

The generated Google Sheets insight tabs can use optional local settings from
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
