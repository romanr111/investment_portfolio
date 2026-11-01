set shell := ["bash", "-o", "pipefail", "-eu", "-c"]

test:
    venv/bin/python -m unittest discover -s tests

# Run tests in parallel (3 workers) for faster execution.
test-parallel:
    venv/bin/python tests/parallel_runner.py

run:
    venv/bin/python -m src.portfolio_sync

# Preview adopting existing hand-made worksheet tabs; prints the adoptions JSON.
# Usage: just adoption-preview "04 Oct 2026,net_worth_timeline"
adoption-preview titles:
    venv/bin/python main.py --adoption-preview {{titles}}

# Dry-apply a reviewed adoptions JSON: validates the sheet update without writing.
# Requires --adoption-preview output reviewed first.
# Usage: just adoption-apply data/adoptions.json
adoption-apply file:
    venv/bin/python -m src.portfolio_sync --adoptions-file {{file}}

# LIVE variant: actually applies the reviewed adoptions to Google Sheets.
# Usage: just adoption-apply-live data/adoptions.json
adoption-apply-live file:
    venv/bin/python -m src.portfolio_sync --adoptions-file {{file}} --write

crypto-sync *args:
    venv/bin/python -m src.portfolio_ledger.cli {{args}}

# Add risk analytics to a derived copy of a dated combined-data snapshot.
holy-grail *args:
    venv/bin/python -m analytics.holy_grail_cli {{args}}

# Update only the saved indicator in an existing dated worksheet.
holy-grail-sheet *args:
    venv/bin/python -m analytics.holy_grail_sheet {{args}}

# Car business vs a listed used-vehicle industry proxy (offline, retrospective).
car-proxy *args:
    venv/bin/python -m analytics.car_industry_proxy {{args}}

# Car-category tracker (method v3): `build` freezes the index block, `report` prints per-group correlations and scores.
car-category *args:
    venv/bin/python -m analytics.car_category {{args}}

# Used-vehicle price index vs portfolio groups in crises (H1-H3); --fetch-manheim-url downloads raw data first.
car-crisis *args:
    venv/bin/python -m analytics.car_crisis_test {{args}}

# Download Flex snapshot artifacts from last 4 CI runs.
fetch-snapshots:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p data/ib_flex_snapshots
    run_ids=$(gh run list --repo romanr111/investment_portfolio \
        --workflow flex-snapshot.yml --limit 4 \
        --json databaseId --jq '.[].databaseId')
    for run_id in $run_ids; do
        echo "Downloading artifacts from run $run_id..."
        gh run download "$run_id" --repo romanr111/investment_portfolio \
            --dir data/ib_flex_snapshots 2>/dev/null || true
    done
    echo "Snapshots in data/ib_flex_snapshots/:"
    ls -1 data/ib_flex_snapshots/*.xml 2>/dev/null || echo "  (none found)"

# Generate quarterly report (Markdown + HTML).
# Usage: just report 2026 2
report year quarter:
    venv/bin/python portfolio_yic_reports/analyze_portfolio_reports.py --year {{year}} --quarter {{quarter}} --format markdown
    venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --year {{year}} --quarter {{quarter}}
