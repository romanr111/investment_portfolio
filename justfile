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

# Apply a reviewed adoptions JSON (from adoption-preview) during a sheet update.
# Usage: just adoption-apply data/adoptions.json
adoption-apply file:
    venv/bin/python -m src.portfolio_sync --adoptions-file {{file}}

crypto-sync *args:
    venv/bin/python -m src.portfolio_ledger.cli {{args}}

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
