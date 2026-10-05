# Continuity Ledger

## Snapshot
- 2026-10-01 [TOOL] Shared quarterly-report skill migrated to `.agents/skills/quarterly-report` with a relative Claude symlink; project references updated. PR prepared from `master` separately from existing ledger work.
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
- 2026-05-06T23:02+03:00 [DOC] Removed old XML-analyzer-first README content and documented the active portfolio sync pipeline, private local data expectations, optional history/Dalio flows, and test command.
- 2026-05-06T22:51+03:00 [CODE] Removed the duplicate early forward-dividend lookup in `YFinanceFetcher._get_etf_info`, so rate-limited fallback retries now happen once per symbol instead of twice for the same ticker.
- 2026-05-06T22:51+03:00 [CODE] Added regression tests proving both generic symbols like `PDD` and special-case `BABA` only invoke `forward_dividend()` once.
- 2026-04-28T19:22Z [TOOL] Backed up local `data/` outside the repo at `/Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z`.
- 2026-04-28T19:24Z [TOOL] Confirmed `git ls-files -- data` lists only `data/README.md`.
- 2026-04-28T19:24Z [TOOL] Confirmed private files such as `data/api_keys.py`, `data/credentials.json`, `data/assets_data.py`, and `data/final_data.json` still exist locally and are ignored.
- 2026-04-28T19:25Z [CODE] Staged and committed the current-tree cleanup locally.
- 2026-04-28T19:27Z [TOOL] Pushed cleanup to `origin/master` and verified GitHub lists only `data/README.md` under `data/`.

## Now
- 2026-05-06T23:02+03:00 [DOC] README refresh is implemented; code changes from dividend-fetch optimization remain in the working tree.
- 2026-10-05 [CODE] Issue #21 insight tabs are implemented in `/Users/roman/agent/ip-issue-21` on `feat/issue-21-sheets-insights`; `just test` passes 144 tests. No live Sheets writeback has been attempted. Commits, PR, CI, and test-workbook review remain pending.

## Next
- 2026-10-05 [TOOL] Commit the reviewed issue #21 source and test changes, push the branch, create the PR, and watch CI.
- 2026-10-05 [USER] Review the generated test workbook before any live Sheets writeback.
- 2026-05-06T22:51+03:00 [ASSUMPTION] No further code changes are needed unless you want me to push the fix or trim the noisy Yahoo retry handling further.
- 2026-04-28 [USER] Rotate any credentials or tokens that were previously exposed in Git history, if applicable.

## Open questions
- 2026-04-28 [USER] None.

## Working set
- 2026-04-28 [CODE] `.gitignore`
- 2026-04-28 [CODE] `data/README.md`
- 2026-04-28 [CODE] `CONTINUITY.md`
- 2026-04-28 [CODE] Git index entries under `data/`
- 2026-10-05 [CODE] `src/google_sheets/insights_*.py` and `tests/*insights*.py`
- 2026-10-05 [CODE] `src/data_source.py`, `src/google_sheets/spreadsheet_structure.py`, and `data/README.md`

## Receipts
- 2026-10-05 [TOOL] `PYTHONPATH=/Users/roman/Documents/Development/investment_portfolio just test` passed all 144 tests on `feat/issue-21-sheets-insights` using the shared Python 3.10.18 environment.
- 2026-04-28T19:22Z [TOOL] `rsync -a data/ /Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z/data/` completed with 34 files.
- 2026-04-28T19:24Z [TOOL] `git check-ignore -v` matched `/data/**` for private data files.
- 2026-04-28T19:25Z [TOOL] `git commit -m "Stop tracking local portfolio data"` created the local cleanup commit.
- 2026-04-28T19:27Z [TOOL] `gh api 'repos/romanr111/investment_portfolio/contents/data?ref=master' --jq '.[].path'` returned `data/README.md`.
