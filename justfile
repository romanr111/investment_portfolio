set shell := ["bash", "-o", "pipefail", "-eu", "-c"]

graph-bootstrap:
    Scripts/codegraph-bootstrap.sh

graph-init: graph-bootstrap

graph-sync: graph-bootstrap
    codegraph sync

graph-reindex: graph-bootstrap
    codegraph index --force

graph-status: graph-bootstrap
    codegraph status

test:
    venv/bin/python -m unittest discover -s tests

# Run tests in parallel (3 workers) for faster execution.
test-parallel:
    venv/bin/python tests/parallel_runner.py

run:
    venv/bin/python -m src.portfolio_sync

# Generate the quarterly YIC portfolio report (last completed quarter).
# Optional flags: year, quarter, snapshot-start, snapshot-end, skip-dalio, output-dir.
report *args='':
    venv/bin/python -m portfolio_yic_reports.auto.cli {{args}}

# Fetch a fresh IB Flex portfolio snapshot (query 1188471) and save it.
fetch-snapshot:
    venv/bin/python -c "from src.brokers.ib_flex_portfolio import IBFlexPortfolioFetcher; print(IBFlexPortfolioFetcher().fetch_and_save())"

# Fetch quarterly trades XML (query Period=LastQuarter) for exit prices.
fetch-trades:
    venv/bin/python -c "from src.brokers.ib_flex_portfolio import IBFlexPortfolioFetcher; import os; print(IBFlexPortfolioFetcher(query_id=os.getenv('IB_FLEX_QUERY_ID_QUARTERLY_TRADES')).fetch_and_save('data/ib_flex_snapshots'))"
