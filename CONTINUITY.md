# Continuity Ledger

## Snapshot

- 2026-11-07 [CODE] PR #34 is open at `ca41a84` on `feat/holy-grail-v4-car-composite`; the local worktree is on `feat/risk-progress-v3-individual` (code `1ad7732`, docs `f66da10`, `ca41a84`). Triage T1-T8 implemented; T3 waived by the owner (no new tests); T9-T11 deferred; triage reply `6709958592`.
  - T1-T8: model row allowlist and parameter-only method fingerprint, `-` location normalization, cash-sourced deposits netted from the "Кеш поза оцінкою" view row, failure-cause suffixes, methodology/reference docs and total-volatility wording.
  - Docs commits: `f66da10` compressed the methodology reference; `ca41a84` audited the six markdown files changed by this PR. This follow-up prunes the Holy Grail reference and this ledger.
  - Sensitive triggers: public APIs or serialized formats (saved-record shape and replay validation); payments or financial calculations (cash share and coverage).
  - Python 3.10.18: 314 tests run, 309 pass; `test_rounded_source_total_keeps_the_saved_estimate_visible` fails identically at pristine `f417dfd`; four `ib_insync` import errors are environmental.
  - Focused checks pass for docs-only fingerprint invariance, model-invalid replay, unknown row-key rejection and `-` location collision.
  - Existing saved `risk_progress_v3` records fail replay by design until the owner regenerates the current snapshot with `just run`; not run. The worktree is clean at the start of this prune; only the two docs files change.

## Decisions

- D001 ACTIVE 2026-04-28 [USER] Use current-tree cleanup only; no force-push or Git history rewrite.
- D002 ACTIVE 2026-04-28 [USER] Fresh clones require private local `data/` files; commit only `data/README.md` under `data/`.

## Done (recent)

- 2026-10-22 [CODE/TOOL] PR #22 resolved and merged.
  - Resolved against master `314b86b` through merge commit `508bea3`, preserving history; four textual conflicts resolved.
  - The saved ENHANCED_STOCKS guard was retained and the upstream snapshot P&L regression adapted to the typed renderer.
  - Sensitive triggers: payments or financial calculations; public APIs or serialized formats; concurrency, retries, idempotency.
  - Python 3.10.18: 75 focused and 276 full-suite tests pass; compile, scoped Black and diff checks pass. The initial full-suite failure was a missing local `filters_constants`; a local-only symlink fixed the subprocess environment.
  - Incoming files exactly match master; Sheets renderer/helpers/timeline code unchanged. Push verified by exact remote SHA `508bea333ea0d3fdca952fc7b2b149760abaddb9`; GitHub mergeable=true, clean; no CI checks; production excluded.

- 2026-10-22 [CODE] PR #22 renderer, timeline, FIRE and monitor polish.
  - Replaced the legacy plus thematic-tab output with one typed snapshot renderer, a holdings header at row 8, expandable sections, saved benchmark/IB coverage and a shared timeline with sorted same-tab chart data.
  - Same-date runs preserve sheet IDs; later dates add one main tab.
  - Reused the existing regular `net_worth_timeline` and legacy configuration; unmarked timelines need no adoption; same-date runs change A only, new dates append A=value/B=date.
  - Missing timelines use the legacy two-column setup; only a full grid grows.
  - Removed the redundant Eligible assets row and duplicate eligibility table; FIRE progress/remaining now use saved `TOTAL_ASSETS` exactly, with legacy category filters ignored/documented and result keys compatible.
  - Monitor polish: exact A:L widths, Arial hierarchy, warm neutrals, scoped one-decimal percentages and whole amounts, readable dates and safe shared-row heights. Native repeated refresh preserved values, formulas, formats, IDs, one rule/group and charts.
  - Python 3.10.18: 68 focused and 189 full-suite checks pass for the timeline; 66 focused and 187 full-suite for FIRE; 184 full-suite and 63 focused for the monitor; compile/Black/diff checks pass. Production untouched; synthetic workbook QA only.

- 2026-10-21 [CODE/REPORT] Q3 KPI cards and benchmark gap.
  - Four compact KPI cards with aligned values: current Car Resale share plus previous share, the largest-change context only on card 4.
  - An unsigned benchmark-gap magnitude with full units, a dated summary heading and sentence-case labels.
  - Largest-change selection ranks absolute allocation-share changes rather than dollars; IBKR/index values use comma decimals; the spread displays points without a percent suffix.
  - Restored the simpler benchmark gap after comparing relative percent and percentage points: card 3 shows the gap in percentage points, without a minus or percent sign; the other three values retain percent signs.
  - 37 quarterly tests, compileall and diff checks pass; generator, tests and generated HTML match the approved committed version byte for byte. Native Brave screenshots confirm alignment and no clipping; mobile/print and the full suite remain unverified.

- 2026-10-18 [CODE/REPORT] Q3 masthead, Car Resale descriptor and crypto table.
  - Removed the "Portfolio Review" masthead and regenerated Q3 HTML/Markdown with `just report 2026 3`; the category descriptor is "Інші активи (Car Resale)" in the allocation row and performance footnote.
  - The legacy `Other Bets` bucket remains a portfolio category; no category rename or valuation change.
  - Public crypto table keeps only position, coin-count change and weight, with no price/profit column, empty profit cells or private values.
  - Added and then removed requested detail sections (crypto lending, volatile Earn rewards, active cars, P2P); the shared skill preserves the exclusions while retaining crypto details and overall allocation categories.
  - Self-QA fixed nonfinite USD display, nonfinite quantity falsely marked new, and tiny nonzero quantity falsely marked closed; regeneration produced byte-identical HTML.
  - 34 HTML + 1 period tests, 29-33 focused report tests and Decimal readback pass; exact HTML comparisons preserve all other sections. Basis/coverage caveats and blocked visual/print checks remain.

- 2026-10-15 [CODE/DATA] USD1 as cash and crypto data integrity.
  - USD1 now counts as cash across Spot/Earn/cold storage, exchange adapters, the ledger contract, snapshot recovery and the Q3 report; failed balance sources retain cached USD1 once with partial quality.
  - Fixed the WhiteBit cash cents/USD mismatch with a reproducing regression.
  - Backed up originals, migrated September snapshots idempotently, reconciled the active snapshot with previously approved manual balances and updated nine category history rows.
  - Live Sheet write/readback confirmed the transfer and unchanged net worth; full primary suite 199 tests passed with existing fixture warnings; compile, diff, skill validation and arithmetic/readback checks passed.
  - Stale allocation discrepancy resolved; a prior Treasury ETF denominator, T Bills P/L, a legacy position basis and partial crypto coverage remain. No fresh broker collection or native visual/print validation; no Telegram post, commit or push.

- 2026-10-04 [CODE] PR #19 review remediation.
  - Pushed to `agent/portfolio-ledger-v2`: `bf4e05c` fixed four Codex comments (two-sided boundary-window start snapshot selection, mid-quarter Modified Dietz cap at the as-of date, failed balance-source recovery to the snapshot union with partial freshness, STABLECOINS unification onto the contract canonical set).
  - `ecedc4c` fixed six independent-review findings.
  - Full suite 185 tests OK with 6 new tests; whitespace and compile checks clean; push verified `bf4e05c..ecedc4c`.
  - Review results posted: replies to all four Codex threads and consolidated findings comment `5978089653` listing fixed findings and five deferred P3s with rationale; API readback confirmed.
  - The user's uncommitted ENHANCED_STOCKS fix, totals-test edits and skill/AGENTS changes were preserved and excluded by selective staging. Independent validation: business value VALID; no P0/P1 findings.

- 2026-10-01 [CODE/TOOL] Quarterly workflow, secrets and shared skill.
  - Migrated the canonical quarterly-report skill to `.agents/skills/quarterly-report` with a relative Claude symlink; PR #20 squash-merged to master at `9db8bd9`; one-line skill policy added to AGENTS.md.
  - Updated the skill for styled HTML primary, approved design reuse, exact XML boundaries and workflow-step/artifact verification, the correct IBFlexPortfolioFetcher/env loader, dated combined-data selection, closing-quarter labels/activity, partial-data/YTD semantics and honest visual/print limitations.
  - Configured repository Actions secrets `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` and `IB_FLEX_QUERY_ID_QUARTERLY_TRADES`; manual dispatch run `36890045196`. IB_FLEX_TOKEN and Telegram credentials remain unconfigured.
  - Skill validator, code-example parsing/API signature/path checks and diff checks pass; no fresh report generation or runtime/workflow change.

- 2026-10-01 [CODE] Q3 report completed locally.
  - Built from exact 20260930 positions (run `36890045196`) and 20260701-20260930 trades (local query `1575659`, 23 trades).
  - Fixed prior-quarter labels and activity selection by using the closing export date in both report entry points.
  - A test-first CLI regression passed; `just test` passed 172 tests with existing numerical warnings; compileall and diff checks passed.
  - Generated Q3 HTML and Markdown; verified 25 position rows and nine allocations against June/September combined-data snapshots.
  - Crypto coverage remains partial; fixed FX and a legacy position assumption remain; visual/print review is unverified after the browser policy rejected local-file preview. No Telegram send, commit, push or workflow change.

- 2026-09-30 [CODE] Snapshot P&L fix.
  - Fixed lost spreadsheet position P&L after snapshot-only regeneration: `DataSource.get_combined_data` now includes cached `ENHANCED_STOCKS`. The main checkout contains the uncommitted tested fix and snapshot round-trip regression coverage in `tests/test_portfolio_totals.py`; unrelated pre-existing edits were preserved.
  - `just test` passed 171 tests in the isolated worktree; compileall and diff checks passed.
  - Live pipeline rerun succeeded; readback of 30 Sep 2026 verified position P&L values, effective percentage/green-red formatting, the timeline and all earlier tabs.
  - Local Q3 input manifests document September 29 positions and Q2 trades, missing exact Q3 closing exports, and partial crypto activity. No credentials were changed and no Telegram post was sent.

- 2026-07-25 [CODE] Portfolio ledger v2 and Q2 import.
  - Added the private git-ignored portfolio ledger, exchange activity adapters, additive v2 combined_data contract, Modified Dietz performance, car/P2P models, automatic history upsert and quarterly alternative-asset tables.
  - Repaired post-review correctness issues: Modified Dietz history stored as a decimal, partial API cursors not advancing, OKX volatile Earn principal including fractional amounts retained in Crypto Coins, matched on-chain transfer legs with zero portfolio return impact, and quarterly HTML snapshot selection.
  - Imported Q2 2026 API history: 7,520 exchange records and 128 exchange records; repeat sync imported zero duplicates. WhiteBit fallback and manual Telegram/cold-storage history remain partial.
  - `just test` passed 165 tests; `just report 2026 2` generated a self-contained HTML report from a local v2 Q2 snapshot. Raw ledger fields were absent from tracked HTML.

- 2026-04-28 [TOOL] Kept portfolio `data/` local-only.
  - Backed up local data outside the repo, confirmed only `data/README.md` is tracked and private files remain ignored, committed the current-tree cleanup locally, pushed to origin/master and verified GitHub lists only `data/README.md` under `data/`.
  - No history rewrite or force-push. This is the origin of D001/D002.

## Now

- 2026-11-07 [CODE] PR #34 is open at `ca41a84`; local worktree on `feat/risk-progress-v3-individual` (code `1ad7732`, docs `ca41a84`). Triage reply `6709958592` posted. T3 waived; T9-T11 deferred. This docs prune is the current working set; the owner still needs to regenerate the saved snapshot with `just run`.

## Next

- PR #34: run `just run` to regenerate the saved snapshot, then confirm the new `risk_progress_v3` record's status, headline, scenario range and replay; decide whether T9-T11 are worth implementing or should be closed.
  - The current saved v3 records fail replay until this regeneration; do not treat that as a code regression.
- Review the synthetic workbook before production writeback (older, still open). Only unmarked main tabs require reviewed adoption; the legacy timeline is reused without adoption.
- Add stable manual Q2 event IDs before treating WhiteBit/Telegram/cold-storage return coverage as complete (older, still open).
  - Coverage remains partial for those sources; the limitation is documented in the Q3 report.

## Open questions

None.

## Working set

- PR #34 (open): `analytics/holy_grail/risk_progress_v3.py`, `analytics/holy_grail/views/risk_progress_v3.py`, `docs/diversification-methodology.md`, `.agents/references/holy-grail.md`, `CONTINUITY.md`.
- This docs prune touches only `.agents/references/holy-grail.md` and `CONTINUITY.md`; no code, tests, config or `data/` changes.

## Receipts

- 2026-11-07 [TOOL] PR #34 triage/tests: 314 tests run, 309 pass; `test_rounded_source_total_keeps_the_saved_estimate_visible` fails identically at pristine `f417dfd`; four `ib_insync` import errors are environmental. Focused checks pass for docs-only fingerprint invariance, model-invalid replay, unknown row-key rejection and `-` location collision; T3 waived, so no new tests were added. Triage reply `6709958592`. No broker fetch or production write.
- 2026-10-22 [TOOL] PR #22 merge/resolution: merge `508bea3` preserved history; four textual conflicts resolved; the ENHANCED_STOCKS guard retained and the upstream P&L regression adapted to the typed renderer; 75 focused and 276 full-suite tests pass; compile, scoped Black and diff checks pass; remote SHA verified `508bea333ea0d3fdca952fc7b2b149760abaddb9`; GitHub mergeable=true and clean; no CI checks; production excluded. Initial full-suite failure was a missing local `filters_constants`; a local-only symlink fixed the subprocess environment.
- 2026-10-04 [TOOL] PR #19 push/review: commits `bf4e05c` and `ecedc4c` pushed to `origin/agent/portfolio-ledger-v2` after `git ls-remote` matched refs; `bf4e05c` fixed four Codex comments and `ecedc4c` six independent-review findings; full suite 185 tests with 6 new; review-thread replies `4176751501`, `4176753431`, `4176753541`, `4176753579` and consolidated summary comment `5978089653` posted; API readback confirmed. Five P3s deferred with rationale; business value VALID; no P0/P1 findings.
- 2026-10-15 [TOOL] USD1 live write/readback: passed with USD1 counted as cash across the tested surfaces; the WhiteBit cash cents/USD mismatch has a reproducing regression; originals backed up, September snapshots migrated idempotently and nine category history rows updated; full primary suite 199 tests passed. No amounts or sheet ids retained in this ledger.
