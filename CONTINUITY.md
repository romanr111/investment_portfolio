# Continuity Ledger

## Snapshot
- 2026-10-15 [CODE] PR #22 reworked on `feat/issue-21-sheets-insights` in `/Users/roman/agent/ip-issue-21`: one dated main portfolio tab and shared `net_worth_timeline`. Financial corrections, explicit adoption/preflight, saved-data replay, and synthetic workbook validation are implemented. Acceptance: tab limit, preservation/idempotency, financial consistency, replay, and test-workbook delivery. Work began at `43fa62d`; primary PR #19 checkout and pre-existing untracked `venv` symlink remain untouched. Production writeback requires human review of the synthetic workbook.
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
- 2026-10-15 [CODE] Replaced legacy plus thematic-tab output with a single typed snapshot renderer, holdings header at row 8, expandable sections, saved benchmark/IB coverage, and a shared timeline with sorted same-tab chart data. Same-date runs preserve sheet IDs; later dates add one main tab.
- 2026-10-15 [CODE] Corrected closed-category headline reconciliation, REIT coverage, duplicate FIRE eligibility, saved income-principal basis, persisted ENHANCED_STOCKS, and native-currency receipt formats. Rendering makes no broker calls.
- 2026-10-15 [TOOL] Synthetic native workbook created, generated requests applied repeatedly, read back, and visually inspected. Confirmed numeric precision, formulas/formats, 8 row groups, holdings filter/frozen headers, continuous irregular-date chart spacing, retained adjacent formula and Deployed Capital chart. Test workbook only; no production writeback.
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
- 2026-10-15 [CODE] PR #22 implementation and self-QA complete locally. Shared runtime is Python 3.10.18, not the handoff's suggested 3.11. No project-declared static gates or PR CI workflow exist. Synthetic workbook review is the remaining production gate.

## Next
- 2026-10-15 [USER] Review synthetic workbook `https://docs.google.com/spreadsheets/d/1cXSNdREcheLWKCUhK9U-W1gjKKOEHIojixrLQFiLPv0/edit` before production writeback. Unmarked production tabs require explicit reviewed adoption; existing thematic tabs are never deleted automatically.
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
- 2026-10-15 [TOOL] Focused insights suite passed 49 tests; `PYTHONPATH=/Users/roman/Documents/Development/investment_portfolio just test` passed 168 tests. `venv/bin/python -m compileall -q src tests`, Black check on rewritten modules/tests, and `git diff --check` passed. Existing numerical warnings and deliberate source/notification failure logs remain.
- 2026-10-15 [TOOL] Synthetic main/timeline IDs are 391946242/1818790324. Latest generated native batch had 142 requests; no new tabs on repeat. Readback: tracked total 930.003, native HKD receipt 12.5 without USD symbol, bond market/principal 200/225, timeline sorted date serials 46203/46295/46299, preserved C4 formula `=A4/2`, chart IDs 1 and 2. Screenshots saved outside Git at `/Users/roman/.codex/visualizations/2026/10/15/portfolio-pr22/`.
- 2026-10-05 [TOOL] `PYTHONPATH=/Users/roman/Documents/Development/investment_portfolio just test` passed all 144 tests on `feat/issue-21-sheets-insights` using the shared Python 3.10.18 environment.
- 2026-10-05 [TOOL] Opened PR #22 at `https://github.com/romanr111/investment_portfolio/pull/22`; `gh pr checks` reported 0 checks, and the repository has only the scheduled quarterly snapshot workflow.
- 2026-04-28T19:22Z [TOOL] `rsync -a data/ /Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z/data/` completed with 34 files.
- 2026-04-28T19:24Z [TOOL] `git check-ignore -v` matched `/data/**` for private data files.
- 2026-04-28T19:25Z [TOOL] `git commit -m "Stop tracking local portfolio data"` created the local cleanup commit.
- 2026-04-28T19:27Z [TOOL] `gh api 'repos/romanr111/investment_portfolio/contents/data?ref=master' --jq '.[].path'` returned `data/README.md`.
