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

report:
    venv/bin/python portfolio_yic_reports/analyze_portfolio_reports.py --format markdown
    venv/bin/python portfolio_yic_reports/generate_quarterly_report.py
