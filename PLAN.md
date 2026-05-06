# IB Gateway + Flex Migration Plan

## Final verified high-level plan

Goal:

Fully remove dependency on local Client Portal Gateway:

```text
clientportal.gw/bin/run.sh root/conf.yaml
```

New architecture:

```text
IB Gateway / ib_insync
  -> live positions
  -> cash/account summary
  -> market values
  -> average cost
  -> unrealized/realized P&L

IBKR Flex Web Service
  -> YTD account-level TWR / NAV performance
```

Deprecated:

```text
Client Portal Gateway runtime
/portfolio/{accountId}/positions/0
/portfolio/{accountId}/summary
/pa/performance
```

Runtime requirement:

```text
All normal runtime flow should run automatically in one shot after one-time IB Gateway and Flex setup; the app must not depend on local Client Portal Gateway or manual clientportal.gw/bin/run.sh.
```

## Implementation phases

### Phase 1 - Add adapter boundary

Add:

```text
src/brokers/ib_gateway_portfolio.py
src/brokers/ib_flex_performance.py
src/brokers/ib_models.py
```

Keep `src/brokers/ib.py` as the public orchestrator for now.

### Phase 2 - Gateway positions/cash

Implement:

```text
IBGatewayPortfolioLoader.fetch_positions()
IBGatewayPortfolioLoader.fetch_account_summary()
```

Normalize into the current `ib.py` shape so existing categorization keeps working.

### Phase 3 - Flex YTD performance

Implement:

```text
IBFlexPerformanceFetcher.fetch_ytd_twr()
```

Config:

```text
IB_FLEX_TOKEN
IB_FLEX_QUERY_ID_YTD_PERFORMANCE
IB_ACCOUNT_ID
```

Return:

```python
{
    "period": "YTD",
    "rate_of_return_pct": 12.34,
    "measure": "TWR",
    "source": "ib_flex_activity_statement",
    "error": None,
}
```

### Phase 4 - One-shot runner

Create one command:

```bash
python -m src.portfolio_sync
```

Runtime flow:

```text
1. Check IB Gateway socket availability.
2. Connect through ib_insync.
3. Fetch account summary.
4. Fetch portfolio positions.
5. Fetch Flex YTD TWR.
6. Normalize all data.
7. Run current portfolio categorization/analytics.
8. Output final report.
```

### Phase 5 - Deprecate Client Portal Gateway

Remove or disable:

```text
POSITIONS_API
SUMMARY_API
PERFORMANCE_API
perform_post_request(PERFORMANCE_API, ...)
Client Portal login-required messages
clientportal.gw/bin/run.sh documentation
```

Current `ib.py` still directly calls `PERFORMANCE_API` and parses the result into `performance_ytd`, so this is the exact code path to remove.

## Final acceptance criteria

```text
- Running portfolio sync no longer requires clientportal.gw/bin/run.sh.
- No runtime code calls /portfolio/{accountId}/positions/0.
- No runtime code calls /portfolio/{accountId}/summary.
- No runtime code calls /pa/performance.
- Positions come from IB Gateway / ib_insync.
- Cash/account summary comes from IB Gateway account summary/account values.
- YTD TWR comes from IBKR Flex Web Service.
- Existing portfolio categories still work.
- Existing stock analytics still work.
- Bond fetcher remains compatible or reuses shared Gateway connection.
- If IB Gateway is unavailable, error clearly says IB Gateway is required.
- If Flex token/query fails, error clearly says YTD performance is unavailable.
```

## Final judgment

This plan is technically accurate and implementable with one mandatory scope clarification:

```text
All normal runtime flow should run automatically in one shot after one-time IB Gateway and Flex setup; the app must not depend on local Client Portal Gateway or manual clientportal.gw/bin/run.sh.
```
