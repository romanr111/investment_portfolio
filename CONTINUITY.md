# Continuity Ledger

## Snapshot
- 2026-04-28 [USER] Goal: keep portfolio `data/` local-only and remove tracked data from the current GitHub tree without history rewrite.
- 2026-04-28 [USER] Success criteria: preserve local data, ignore private `data/` files, keep only `data/README.md` tracked, commit, push, and verify.
- 2026-04-28 [ASSUMPTION] No app refactor, sanitized fixtures, or history rewrite are in scope.

## Decisions
- D001 ACTIVE 2026-04-28 [USER] Use current-tree cleanup only; no force-push or Git history rewrite.
- D002 ACTIVE 2026-04-28 [USER] Fresh clones require private local `data/` files; commit only `data/README.md` under `data/`.

## Done (recent)
- 2026-04-28T19:22Z [TOOL] Backed up local `data/` outside the repo at `/Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z`.
- 2026-04-28T19:24Z [TOOL] Confirmed `git ls-files -- data` lists only `data/README.md`.
- 2026-04-28T19:24Z [TOOL] Confirmed private files such as `data/api_keys.py`, `data/credentials.json`, `data/assets_data.py`, and `data/final_data.json` still exist locally and are ignored.
- 2026-04-28T19:25Z [CODE] Staged and committed the current-tree cleanup locally.
- 2026-04-28T19:27Z [TOOL] Pushed cleanup to `origin/master` and verified GitHub lists only `data/README.md` under `data/`.

## Now
- 2026-04-28 [CODE] Local-only `data/` cleanup is complete.

## Next
- 2026-04-28 [USER] Rotate any credentials or tokens that were previously exposed in Git history, if applicable.

## Open questions
- 2026-04-28 [USER] None.

## Working set
- 2026-04-28 [CODE] `.gitignore`
- 2026-04-28 [CODE] `data/README.md`
- 2026-04-28 [CODE] `CONTINUITY.md`
- 2026-04-28 [CODE] Git index entries under `data/`

## Receipts
- 2026-04-28T19:22Z [TOOL] `rsync -a data/ /Users/roman/Documents/Development/investment_portfolio_data_backup_20260428T192224Z/data/` completed with 34 files.
- 2026-04-28T19:24Z [TOOL] `git check-ignore -v` matched `/data/**` for private data files.
- 2026-04-28T19:25Z [TOOL] `git commit -m "Stop tracking local portfolio data"` created the local cleanup commit.
- 2026-04-28T19:27Z [TOOL] `gh api 'repos/romanr111/investment_portfolio/contents/data?ref=master' --jq '.[].path'` returned `data/README.md`.
