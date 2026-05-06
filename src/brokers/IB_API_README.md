# Interactive Brokers Data Sources

The portfolio runtime uses two Interactive Brokers data sources:

- IB Gateway / TWS API through `ib_insync` for live account state.
- IBKR Flex Web Service for account-level YTD TWR / NAV performance.

The local Client Portal Gateway is deprecated for this project. Runtime code should not call:

```text
/portfolio/{accountId}/positions/0
/portfolio/{accountId}/summary
/pa/performance
```

## Runtime Command

Use the one-shot runner:

```bash
python -m src.portfolio_sync
```

The runner automatically creates/uses the local `.venv`, installs `requirements.txt` when needed, loads `data/ib_flex_env.sh` when present, and re-executes the portfolio pipeline inside the venv.

This delegates to the existing portfolio pipeline after the IB adapters fetch:

1. Account summary from IB Gateway.
2. Positions from IB Gateway.
3. YTD TWR from the IBKR Flex Web Service.

By default this command updates the live portfolio and Google Sheets, while skipping retrospective history sync and Dalio analysis. Use `--run-history-sync` and `--run-dalio-analysis` to enable those slower secondary steps.

## IB Gateway Setup

IB Gateway or TWS must already be running and API access must be enabled.

Default connection:

```text
IB_GATEWAY_HOST=127.0.0.1
IB_GATEWAY_PORT=4001
IB_GATEWAY_CLIENT_ID=1101
```

If the Gateway socket is unavailable, the app fails with a clear message that IB Gateway is required and Client Portal Gateway is no longer supported.

## Flex Web Service Setup

Create an Activity Flex Query configured for Year to Date XML output with the Change in NAV section and TWR field enabled.

Required environment:

```text
IB_FLEX_TOKEN
IB_FLEX_QUERY_ID_YTD_PERFORMANCE
IB_ACCOUNT_ID
```

The Flex fetcher performs the normal two-step flow:

1. `SendRequest` to start report generation.
2. Poll `GetStatement` until the XML statement is ready.
3. Parse Change in NAV / TWR into the existing normalized shape.

Expected result:

```python
{
    "period": "YTD",
    "rate_of_return_pct": 12.34,
    "measure": "TWR",
    "source": "ib_flex_activity_statement",
    "error": None,
}
```

If Flex credentials are missing or the report is unavailable, the portfolio run continues with `rate_of_return_pct=None` and an explicit error in `IB_PERFORMANCE`.

## Key Files

- `src/brokers/ib.py` - public IB portfolio orchestrator.
- `src/brokers/ib_gateway_portfolio.py` - positions and account summary via IB Gateway.
- `src/brokers/ib_flex_performance.py` - YTD TWR via Flex Web Service.
- `src/brokers/ib_models.py` - normalized internal result shapes.
- `src/portfolio_sync.py` - one-shot module entry point.

## Notes

- `ib.portfolio()` is the preferred position source because it includes market value, average cost, market price, and P&L.
- `reqPositions()` / `positions()` are fallback sources only because they may not include market value or P&L.
- Bond contracts are normalized as `IBCID{conId}` so the existing categorizer remains compatible.
- The bond data fetcher can keep its current Gateway connection behavior; future cleanup can share a common Gateway connection pool.
