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

# Generate report, convert to HTML, and publish to GitHub Pages.
# Usage: just publish 2026 2
publish year quarter:
    #!/usr/bin/env bash
    set -euo pipefail

    ORIG_DIR="$(pwd)"
    TMP_HTML=""
    TMP_WT=""
    cleanup() {
        cd "$ORIG_DIR" 2>/dev/null || true
        [ -n "$TMP_WT" ] && git worktree remove "$TMP_WT" --force 2>/dev/null || true
        [ -n "$TMP_HTML" ] && rm -f "$TMP_HTML" 2>/dev/null || true
    }
    trap cleanup EXIT

    # 1. Generate markdown + HTML report
    just report {{year}} {{quarter}}

    # 2. Convert the styled HTML report to a self-contained index.html
    REPORT_HTML="portfolio_yic_reports/portfolio_report_q{{quarter}}_{{year}}.html"
    [ -s "$REPORT_HTML" ] || { echo "ERROR: HTML report not generated" >&2; exit 1; }
    TMP_HTML=$(mktemp /tmp/report_XXXXXX.html)
    cp "$REPORT_HTML" "$TMP_HTML"

    # 3. Pre-push verification
    [ -s "$TMP_HTML" ] || { echo "ERROR: HTML not generated" >&2; exit 1; }
    ! grep -qE "U[0-9]{7}" "$TMP_HTML" || { echo "ERROR: account ID leak in HTML" >&2; exit 1; }

    # 4. Push to report-source via worktree
    git fetch origin
    TMP_WT=$(mktemp -d)
    if git show-ref --verify --quiet refs/remotes/origin/report-source; then
        git worktree add "$TMP_WT" report-source
        cd "$TMP_WT"
        git pull --ff-only origin report-source
    else
        git worktree add --detach "$TMP_WT"
        cd "$TMP_WT"
        git checkout --orphan report-source
        git rm -rf . 2>/dev/null || true
    fi
    cp "$TMP_HTML" index.html
    git add index.html

    if git diff --cached --quiet; then
        echo "No changes since last publish — skipping commit/push."
    else
        git commit -m "publish Q{{quarter}} {{year}} report"
        git push --force-with-lease origin report-source
    fi

    echo ""
    echo "Published: https://romanr111.github.io/investment_portfolio/"
    echo "(CDN cache may take 1-2 minutes to update)"
