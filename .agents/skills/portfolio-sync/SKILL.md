---
name: portfolio-sync
description: Collect current investment portfolio positions and update the Google Sheets portfolio and net-worth timeline. Use for a full current portfolio refresh, not historical quarterly report generation.
---

# Current portfolio sync

A full portfolio collection means collecting current source data, saving the combined snapshot, and updating the portfolio Google spreadsheet. The user has chosen this as the default flow when requesting a full refresh. An explicit request to preview or avoid writes takes precedence.

The verified sync fixes are currently in `/Users/roman/.codex/worktrees/portfolio-sync-integrity/investment_portfolio`, not the primary checkout. Until integrated, run from that worktree and check it still exists. Do not silently run an older checkout or copy over unrelated changes.

Before a full refresh, verify the actual run directory (including any temporary copy) can read `data/holy_grail_config.json` with an `allocation` section and can access `data/holy_grail_history`. The verified worktree links both paths to the primary checkout's private data. If either input is missing or invalid, stop before live writeback and fix the run environment; otherwise the generated worksheet can silently omit diversification. Check an offline replay of an existing snapshot before the run. After a live run, verify that run's saved `DIVERSIFICATION_DATA.allocation_score_v2` and the rendered section in the sheet. `--write` collects and writes in one process, so this preflight cannot guarantee the later live calculation. Do not copy private inputs into tracked files.

1. Run `venv/bin/python -m src.portfolio_sync --write` from the verified worktree for the full flow. `just run` alone is a dry run and does not update Google Sheets. Use it when a dry run is requested.
2. Collect current balances and positions from configured sources. A failed or unavailable balance must not be silently treated as zero. Transaction history, bond acquisition dates, or complete activity coverage are not prerequisites for publishing current positions. Mark unsupported income or activity estimates as unavailable or partial instead of inventing values.
3. Confirm the command completed and a Sheets write was sent. Read back the dated worksheet and `net_worth_timeline`, comparing them with the saved snapshot from that same run. Report any mismatch or failed source; do not claim success from a preview alone.

Keep credentials, source exports, and private snapshots local. Preserve historical snapshots and manual inputs. Do not generate a quarterly HTML report unless requested.
