# Continuity Ledger

## Snapshot
- 2026-07-24 [USER] Implement additive v2 portfolio ledger contract for crypto activity/lending, car-flip assets, P2P, history, and quarterly HTML while preserving legacy Sheets/report keys and keeping raw ledger local-only.
- 2026-07-24 [TOOL] CodeGraph bootstrap succeeded for the current primary worktree; baseline worktree had only unrelated untracked `.codex/`.
- 2026-06-13T07:01Z [TOOL] Adopted CodeGraph + Headroom agent-tooling setup from Cash Runway: added `.mcp.json`, `justfile` with graph recipes, `Scripts/codegraph-bootstrap.sh`, `Scripts/test-codegraph-bootstrap.sh`, `AGENTS.md`, and ignored `.codegraph/`. Initialized CodeGraph index for the current worktree.
- 2026-05-06T23:02+03:00 [DOC] Replaced stale long `README.md` with a concise current guide for `python -m src.portfolio_sync`, local-only data, common runs, outputs, and tests.
- 2026-05-06T22:51+03:00 [CODE] Optimized the dividend fetch path so `forward_dividend()` is only called once per ticker in `src/brokers/data_fetchers/yfinance_fetcher.py`; added regression coverage in `tests/test_yfinance_fetcher.py`.
- 2026-05-06T22:51+03:00 [TOOL] Primary checkout `/Users/roman/Documents/Development/investment_portfolio` is on `master` with local edits in `src/brokers/data_fetchers/yfinance_fetcher.py`, `tests/test_yfinance_fetcher.py`, and `CONTINUITY.md`.
- 2026-04-28 [USER] Goal: keep portfolio `data/` local-only and remove tracked data from the current GitHub tree without history rewrite.
- 2026-04-28 [USER] Success criteria: preserve local data, ignore private `data/` files, keep only `data/README.md` tracked, commit, push, and verify.
- 2026-04-28 [ASSUMPTION] No app refactor, sanitized fixtures, or history rewrite are in scope.

## Decisions
- D001 ACTIVE 2026-04-28 [USER] Use current-tree cleanup only; no force-push or Git history rewrite.
- D002 ACTIVE 2026-04-28 [USER] Fresh clones require private local `data/` files; commit only `data/README.md` under `data/`.

## Done (recent)
- 2026-07-25 [CODE] Added the private git-ignored portfolio ledger, exchange activity adapters, additive v2 combined_data contract, Modified Dietz performance, car/P2P models, automatic history upsert, and quarterly alternative-asset tables.
- 2026-07-25 [DATA] Imported Q2 2026 API history locally: 7,520 Binance records and 128 OKX records; repeat sync imported zero duplicates. WhiteBit fallback and manual Telegram/cold-storage history remain partial.
- 2026-07-25 [TOOL] Final `just test` passed 165 tests. `just report 2026 2` passed and generated a self-contained HTML report from a local v2 Q2 snapshot. Raw ledger fields were absent from tracked HTML.
- 2026-05-06T23:02+03:00 [DOC] Removed old XML-analyzer-first README content and documented the active portfolio sync pipeline, private local data expectations, optional history/Dalio flows, and test command.
- 2026-05-06T22:51+03:00 [CODE] Removed the duplicate early forward-dividend lookup in `YFinanceFetcher._get_etf_info`, so rate-limited fallback retries now happen once per symbol instead of twice for the same ticker.
- 2026-05-06T22:51+03:00 [CODE] Added regression tests proving both generic symbols like `PDD` and special-case `BABA` only invoke `forward_dividend()` once.
- 2026-04-28T19:22Z [TOOL] Backed up local `data/` outside the repo at `/Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z`.
- 2026-04-28T19:24Z [TOOL] Confirmed `git ls-files -- data` lists only `data/README.md`.
- 2026-04-28T19:24Z [TOOL] Confirmed private files such as `data/api_keys.py`, `data/credentials.json`, `data/assets_data.py`, and `data/final_data.json` still exist locally and are ignored.
- 2026-04-28T19:25Z [CODE] Staged and committed the current-tree cleanup locally.
- 2026-04-28T19:27Z [TOOL] Pushed cleanup to `origin/master` and verified GitHub lists only `data/README.md` under `data/`.

## Now
- 2026-07-25 [CODE] Implementation and local Q2 migration are complete on `agent/portfolio-ledger-v2`; a draft PR to `master` is being prepared. Quarterly HTML renders aggregated crypto/lending/volatile Earn/car/P2P tables and accepts an explicit `--after` contract snapshot without reading raw ledger.
- 2026-05-06T23:02+03:00 [DOC] README refresh is implemented; code changes from dividend-fetch optimization remain in the working tree.

## Next
- 2026-07-25 [BLOCKED] Full live `src.portfolio_sync --skip-sheet-update` could not reach IB Gateway and stopped before snapshot/history writes. Re-run when IB Gateway is available.
- 2026-07-25 [USER] Add stable manual Q2 event IDs for Telegram, cold storage, and incomplete WhiteBit periods before treating Q2 movement/return coverage as complete.
- 2026-05-06T22:51+03:00 [ASSUMPTION] No further code changes are needed unless you want me to push the fix or trim the noisy Yahoo retry handling further.
- 2026-04-28 [USER] Rotate any credentials or tokens that were previously exposed in Git history, if applicable.

## Open questions
- 2026-04-28 [USER] None.

## Working set
- 2026-07-24 [CODE] `tests/test_portfolio_contract.py`
- 2026-07-24 [CODE] `src/portfolio_ledger/contract.py`
- 2026-07-24 [CODE] `src/data_source.py`
- 2026-07-24 [CODE] `justfile`
- 2026-07-24 [CODE] `data/README.md`
- 2026-07-24 [CODE] `src/portfolio_history/unified_history.py`
- 2026-07-24 [CODE] `main.py`
- 2026-07-24 [CODE] `portfolio_yic_reports/generate_quarterly_report.py`
- 2026-07-24 [CODE] `portfolio_yic_reports/quarterly_report_html.py`
- 2026-07-24 [CODE] `tests/test_quarterly_report_html.py`
- 2026-07-24 [CODE] `tests/test_portfolio_ledger.py`
- 2026-07-24 [CODE] `src/portfolio_ledger/__init__.py`
- 2026-07-24 [CODE] `src/portfolio_ledger/storage.py`
- 2026-07-24 [CODE] `src/portfolio_ledger/sources.py`
- 2026-07-24 [CODE] `src/portfolio_ledger/sync.py`
- 2026-07-24 [CODE] `src/portfolio_ledger/cli.py`
- 2026-04-28 [CODE] `.gitignore`
- 2026-04-28 [CODE] `data/README.md`
- 2026-04-28 [CODE] `CONTINUITY.md`
- 2026-04-28 [CODE] Git index entries under `data/`

## Receipts
- 2026-04-28T19:22Z [TOOL] `rsync -a data/ /Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z/data/` completed with 34 files.
- 2026-04-28T19:24Z [TOOL] `git check-ignore -v` matched `/data/**` for private data files.
- 2026-04-28T19:25Z [TOOL] `git commit -m "Stop tracking local portfolio data"` created the local cleanup commit.
- 2026-04-28T19:27Z [TOOL] `gh api 'repos/romanr111/investment_portfolio/contents/data?ref=master' --jq '.[].path'` returned `data/README.md`.
