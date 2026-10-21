# Local portfolio data

This directory is intentionally local-only.

Keep portfolio positions, generated combined data, snapshots, API keys, credentials, and account-specific configuration out of Git. A full local run expects the private files to be restored here from your own machine or backup.

Only this README is tracked so fresh clones keep the expected directory shape without exposing sensitive data.

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
