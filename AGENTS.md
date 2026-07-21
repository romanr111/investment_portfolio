## Agent tooling

- Use `just` for project commands when a recipe exists. Key recipes:
  - `just graph-bootstrap` — initialize CodeGraph for the current worktree
  - `just graph-status` — check CodeGraph status
  - `just graph-sync` — sync CodeGraph index
  - `just graph-reindex` — force-reindex CodeGraph
  - `just test` — run the Python test suite (`python3 -m unittest discover -s tests`)
  - `just run` — run the main portfolio sync pipeline (`python -m src.portfolio_sync`)
- Use Headroom as the primary context-optimization layer, especially for bulky/noisy outputs: build logs, test output, JSON, verbose diagnostics, and large diffs. Do not default to RTK when Headroom is available. Retrieve exact original diagnostics when details matter.
- Use CodeGraph before broad text search or raw file-read loops. Run `just graph-bootstrap` before CodeGraph work in every worktree, then use `just graph-status`, `just graph-sync`, or `just graph-reindex`.
- Treat each git worktree as a separate CodeGraph project with its own `.codegraph/codegraph.db`.
- Do not share or copy `.codegraph/` between worktrees.
- Multiple agents in the same worktree can share one CodeGraph daemon; different worktrees must use separate indexes.
- Practical new-worktree setup: `git worktree add ../investment_portfolio_feature_x -b feature/x && cd ../investment_portfolio_feature_x && just graph-bootstrap && just graph-status`.

## Quarterly report generation

- `just report` generates both quarterly outputs in `portfolio_yic_reports/`: Markdown tables (`analyze_portfolio_reports.py` → `portfolio_report_YYYY_qN.md`) and the styled HTML report (`generate_quarterly_report.py` → `portfolio_report_qN_YYYY.html`, e.g. `portfolio_report_q2_2026.html`, rendered by `quarterly_report_html.py`).
- Data sources (two separate IBKR Flex queries):
  - **Positions query** (`stocks_count_trades`) — Query ID `1188471`. Fetch twice:
    - `portfolio_yic_reports/stocks_count_trades1.xml` with `toDate` = first day of the quarter (quarter start positions).
    - `portfolio_yic_reports/stocks_count_trades2.xml` with `toDate` = last day of the quarter (quarter end positions).
  - **Trades query** (`stocks_trades_quarterly`) — Query ID `1575659`. Fetch once per quarter covering the full quarter and save as `portfolio_yic_reports/stocks_trades_quarterly_YYYY_qN.xml`. Required only if closed positions should show realized P/L. The parser merges its `<Trade buySell="SELL">` elements into the final portfolio.
  - Fetch both using the existing `IBFlexPerformanceFetcher` in `src/brokers/ib_flex_performance.py` with `IB_FLEX_TOKEN` from `data/ib_flex_env.sh`. Query IDs are configured in IBKR Account Management.
  - `data/final_data.json` written by `just run` (YTD performance, current allocation).
  - Dated snapshots auto-archived to `data/snapshots/` on each pipeline run (start-of-quarter "Було" column).
- Core/Satellite split is controlled by the hardcoded `CORE_SYMBOLS` set in `portfolio_yic_reports/analyze_portfolio_reports.py`; the bonds/gold table weights use the IBKR subset only (stocks + special assets), not the full portfolio.
- Step-by-step runbook (preconditions, hardcoded one-off cleanup, CLI flags, verification): the `quarterly-report` skill in `.claude/skills/quarterly-report/SKILL.md`.

## Python project notes

- The project is Python 3. Prefer the existing virtualenv at `venv/` when active; otherwise use `python3` from the host.
- Keep `data/` local-only. Only `data/README.md` is tracked. Do not commit credentials, snapshots, or private sheets config.
- Run tests with `just test` rather than invoking `unittest` directly when possible.
