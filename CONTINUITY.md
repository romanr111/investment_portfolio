# Continuity Ledger

## Snapshot
- 2026-10-18 [CODE] PR #22 screenshot-directed revision implemented in `/Users/roman/agent/ip-issue-21` on `feat/issue-21-sheets-insights`: FIRE/performance A:B, grouped holdings D:F, totals/allocation G:I, income K:L. Neutral headers and the original dynamic P&L gradient (-30% red, 0 white, +50% green); one collapsed Details section. Python 3.10.18: 179 full-suite tests and 33 focused rendering/writer checks pass; compile, Black and diff checks pass. Native values/formats and default/expanded views verified. PR #19 and production remain untouched.
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
- 2026-10-15 [CODE] Simplified the default view to original-style adjacent panels. Removed repeated status labels, target columns, native P&L/account detail, and methodological text from the default view; all remain under Details. Filters sit below the summary panels. Amounts and allocation weights omit redundant plus signs and decimals.
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
- 2026-10-18 [CODE] Screenshot-directed presentation is complete locally and in the synthetic review workbook. Production adoption and live Python gspread authentication remain unverified; human workbook review is the production gate. No PR CI checks are configured.

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
- 2026-10-18 [TOOL] Test-first regressions cover the four-zone layout, neutral headers, original P&L scale, rule ownership/repeated growth/shrink, empty ranges, singleton duplication, missing IB data and readable detail widths. Native repeated refresh: 169 requests, zero created tabs, stable main/timeline IDs 391946242/1818790324, one gradient rule and one collapsed group; C4 formula and both timeline charts preserved. Same-cell +79.3%/-10%/0 changes produced green/red/white effective fills and the original value was restored. Synthetic total remains 1330.003; no formula errors. Final suite: 179 tests in 50.074s, OK, with existing fixture/numerical warnings. Screenshot: `/Users/roman/.codex/visualizations/2026/10/18/portfolio-pr22/original-layout-gradients.jpg`.
- 2026-10-15 [TOOL] Compact revision: 64 focused tests and 174 full-suite tests passed (32.793s), compile/Black/diff checks passed. Native repeated generation sent 141 requests, retained both sheet IDs and two timeline charts, preserved C4, and produced one collapsed group. Main total remains 930.003 (display $930). UI inspected at 100%; default and expanded holdings are readable. Screenshot: `/Users/roman/.codex/visualizations/2026/10/15/portfolio-pr22/compact-portfolio.jpg`.
- 2026-10-15 [TOOL] Native QA caught lingering hidden rows when replacing old groups. Writer now unhides only previously managed group ranges before rebuilding; a regression test covers moving Details. Eight old managed ranges were reset in the synthetic workbook after the first preview.
- 2026-10-15 [TOOL] Focused insights suite passed 49 tests; `PYTHONPATH=/Users/roman/Documents/Development/investment_portfolio just test` passed 168 tests. `venv/bin/python -m compileall -q src tests`, Black check on rewritten modules/tests, and `git diff --check` passed. Existing numerical warnings and deliberate source/notification failure logs remain.
- 2026-10-15 [TOOL] Synthetic main/timeline IDs are 391946242/1818790324. Latest generated native batch had 142 requests; no new tabs on repeat. Readback: tracked total 930.003, native HKD receipt 12.5 without USD symbol, bond market/principal 200/225, timeline sorted date serials 46203/46295/46299, preserved C4 formula `=A4/2`, chart IDs 1 and 2. Screenshots saved outside Git at `/Users/roman/.codex/visualizations/2026/10/15/portfolio-pr22/`.
- 2026-10-05 [TOOL] `PYTHONPATH=/Users/roman/Documents/Development/investment_portfolio just test` passed all 144 tests on `feat/issue-21-sheets-insights` using the shared Python 3.10.18 environment.
- 2026-10-05 [TOOL] Opened PR #22 at `https://github.com/romanr111/investment_portfolio/pull/22`; `gh pr checks` reported 0 checks, and the repository has only the scheduled quarterly snapshot workflow.
- 2026-04-28T19:22Z [TOOL] `rsync -a data/ /Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z/data/` completed with 34 files.
- 2026-04-28T19:24Z [TOOL] `git check-ignore -v` matched `/data/**` for private data files.
- 2026-04-28T19:25Z [TOOL] `git commit -m "Stop tracking local portfolio data"` created the local cleanup commit.
- 2026-04-28T19:27Z [TOOL] `gh api 'repos/romanr111/investment_portfolio/contents/data?ref=master' --jq '.[].path'` returned `data/README.md`.
