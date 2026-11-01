# Investment Portfolio - agent guide

Personal portfolio automation: IB Gateway live data, dividend income estimates, Google Sheets sync, historical snapshots, Dalio-style risk analysis, and automated quarterly YIC portfolio reports. Python 3; venv at `venv/`; env vars loaded from `data/ib_flex_env.sh` (local-only).

## Where to look (load on demand)

| Task | Read |
|------|------|
| Run, test or report commands and flags | `.agents/references/commands.md` (authoritative list: `justfile`) |
| Quarterly report: data sources, snapshot matching, core/satellite split, output names | `.agents/references/quarterly-report-data.md`; runbook in the `quarterly-report` skill |
| Full portfolio sync and Google Sheets write | `portfolio-sync` skill |

## Python project notes

- Do not create or expand unit tests unless the user explicitly requests them. Run existing tests and other appropriate checks, and adapt existing fixtures when authorized.
- Keep `data/` local-only. Only `data/README.md` is tracked. Do not commit credentials, snapshots, or private sheets config.
- Use Headroom as the primary context-optimization layer for bulky/noisy outputs. Do not default to RTK when Headroom is available.
- Prefer `just` for project commands when a recipe exists (see `justfile` or `.agents/references/commands.md`).
- Quarterly report worktree venvs may lack deps (pandas, numpy, requests); use the primary worktree venv at `/Users/roman/Documents/Development/investment_portfolio/venv/bin/python` when needed.

## Data invariants (every change)

- The quarterly report **never re-fetches or recomputes** TWR/benchmarks/income. It reads `data/snapshots/combined_data_*.json` written by `just run`.
- `combined_data` is the single source of truth for both Google Sheets and the quarterly report. Do not duplicate fetch/calc logic in the report package.
- Ticker sets, FX rates, and hardcoded prices live in `portfolio_yic_reports/analyze_portfolio_reports.py` only. Do not redefine them elsewhere.

## Workflow

- Keep project skills in `.agents/skills/<name>/`; use relative symlinks from provider-specific skill folders (such as `.claude/skills/`) so all agents share one source.
Use `commit-hygiene`, `code-review`, `self-review` skills for project workflows.
