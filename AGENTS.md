# Investment Portfolio - agent guide

Personal portfolio automation: IB Gateway live data, dividend income estimates, Google Sheets sync, historical snapshots, Dalio-style risk analysis, and automated quarterly YIC portfolio reports. Python 3; venv at `venv/`; env vars loaded from `data/ib_flex_env.sh` (local-only).

## Where to look (load on demand)

| Task | Read |
|------|------|
| Run, test or report commands and flags | `.agents/references/commands.md` (authoritative list: `justfile`) |
| Quarterly report: data sources, snapshot matching, core/satellite split, output names | `.agents/references/quarterly-report-data.md`; runbook in the `quarterly-report` skill |
| Holy Grail: diversification score (risk_progress_v2 headline, v2 and optional v3 car-category as details), risk progress, asset correlation, concentration limits, what-if, saved `DIVERSIFICATION_DATA` | `.agents/references/holy-grail.md`; formulas and policy in `docs/diversification-methodology.md` |
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

## Holy Grail invariants (scores, views, saved records)

- `capital_diversification_v2` is the base method calculated for new snapshots. An explicit v1 or unknown method is unavailable, and an invalid v2 result never falls back to v1.
- `capital_diversification_v3` (`allocation_score_v3`) is an optional sibling derived from the saved v2 and a frozen `car_category_v2` block; v2 stays sealed and is still calculated. A v3 that fails replay renders unavailable and never falls back; a stale block gives the v2 numbers with a warning.
- `risk_progress_v2` is the headline record for new snapshots: one 0-100 score over all invested weights, with the car business included through the labelled CPRT/KMX/OPLN proxy (never called a measurement of the business; its actual profitability is not yet verified), with the worst modelled months and a separate car-business write-off scenario in the details. The qualitative environment map carries no percentages and never claims "protection". It is derived from the saved v2 and a frozen car proxy block (`car_proxies_v3` from normal collection, `car_proxies_v2` for offline recalculation). A record that fails replay shows "Недоступно" and never falls back to v2, v3 or `risk_progress_v1`. `risk_progress_v1` keeps its car-out-of-headline rule for its own records.
- `risk_progress_v1` is a separate optional sibling kept for its own records, written only with a frozen car proxy block (`car_proxies_v1` or `car_proxies_v2`). It is progress, not a grade (never say "achieved"), is never mixed into v2/v3 or `risk_progress_v2` trends (a method boundary shows "Змінено методику"), and keeps the car business out of the headline (labeled proxy scenarios only). A record that fails replay shows "Недоступно", never a number.
- Views (Sheets, quarterly HTML) show the saved `DIVERSIFICATION_DATA` via `analytics/holy_grail/views/diversification.py`; a v2 record, and a risk_progress_v2, v3 or risk_progress_v1 record when present, is replay-validated against its own frozen inputs first. They never fetch market data or read today's config.
- Enrichment never changes balances or totals. `just holy-grail` writes a new derived file: never over an original, in the source's directory, in `data/snapshots/`, or as `combined_data_latest.json`.
- Private inputs (`data/holy_grail_config.json`, `data/holy_grail_history/`, `data/car_category/`, evidence, account ids) stay in ignored `data/`. Public views whitelist generic labels, percentages and counts; tracked files and PR text never carry holdings, weights, amounts, scores or account ids from `data/`. A missing config, or one without an `allocation` object, silently yields no v2 block.
- v2 and v3 are group-level breadth, and `risk_progress_v2` is group-level too (a diversification-ratio score over group representatives). They cannot see issuer or thesis concentration (`concentration_v1` does), are not forecasts, and are never trended against legacy streams or `risk_progress_v1` values.
- Unknown instruments need explicit dated profiles (`analytics/models/economic_profiles_v1.json` or private `allocation.profiles`); region is never inferred from currency, venue or broker bucket. What each pair rests on (`measured`, `modeled`, `category`, `missing`, and the HYG proxy for lending/P2P): reference section "Evidence status and data sufficiency".

## Workflow

- Keep project skills in `.agents/skills/<name>/`; use relative symlinks from provider-specific skill folders (such as `.claude/skills/`) so all agents share one source.
- Use `commit-hygiene`, `code-review`, `self-review` skills for project workflows.
