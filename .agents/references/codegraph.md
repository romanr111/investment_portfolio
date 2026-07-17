# CodeGraph usage

## General rule

Use CodeGraph before broad text search or raw file-read loops. Run `just graph-bootstrap` before CodeGraph work in every worktree, then use `just graph-status`, `just graph-sync`, or `just graph-reindex`.

## Worktree separation

- Treat each git worktree as a separate CodeGraph project with its own `.codegraph/codegraph.db`.
- Do not share or copy `.codegraph/` between worktrees.
- Multiple agents in the same worktree can share one CodeGraph daemon; different worktrees must use separate indexes.

## New-worktree setup

```bash
git worktree add ../investment_portfolio_feature_x -b feature/x
cd ../investment_portfolio_feature_x
just graph-bootstrap && just graph-status
```