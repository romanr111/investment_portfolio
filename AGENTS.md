## Agent tooling

- Use `just` for project commands when a recipe exists. Key recipes:
  - `just graph-bootstrap` — initialize CodeGraph for the current worktree
  - `just graph-status` — check CodeGraph status
  - `just graph-sync` — sync CodeGraph index
  - `just graph-reindex` — force-reindex CodeGraph
  - `just test` — run the Python test suite (`python3 -m unittest discover -s tests`)
  - `just run` — run the main portfolio sync pipeline (`python -m src.portfolio_sync`)
- Use Headroom as the primary context-optimization layer, especially for bulky/noisy outputs: build logs, test output, JSON, verbose diagnostics, and large diffs. Do not default to RTK when Headroom is available. Retrieve exact original diagnostics when details matter.
- Use CodeGraph before broad text search or raw file-read loops. Run `just graph-bootstrap` before CodeGraph work in every worktree, then use `just graph-status`, `just graph-sync`, or `just graph-reindex`.
- Treat each git worktree as a separate CodeGraph project with its own `.codegraph/codegraph.db`.
- Do not share or copy `.codegraph/` between worktrees.
- Multiple agents in the same worktree can share one CodeGraph daemon; different worktrees must use separate indexes.
- Practical new-worktree setup: `git worktree add ../investment_portfolio_feature_x -b feature/x && cd ../investment_portfolio_feature_x && just graph-bootstrap && just graph-status`.

## Python project notes

- The project is Python 3. Prefer the existing virtualenv at `venv/` when active; otherwise use `python3` from the host.
- Keep `data/` local-only. Only `data/README.md` is tracked. Do not commit credentials, snapshots, or private sheets config.
- Run tests with `just test` rather than invoking `unittest` directly when possible.
