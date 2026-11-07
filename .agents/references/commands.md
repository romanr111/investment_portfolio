# Command reference

## just recipes

The authoritative list lives in `justfile`. Key recipes:

- `just test` - run the Python test suite (`python3 -m unittest discover -s tests`)
- `just run` - run the main portfolio sync pipeline (`python -m src.portfolio_sync`)
- `just report` - generate the quarterly YIC portfolio report (Markdown + HTML) via `analyze_portfolio_reports.py` + `generate_quarterly_report.py`
- `just fetch-snapshots` - download the Flex snapshot artifacts of the last 4 CI runs into `data/ib_flex_snapshots/` (needs an authenticated `gh`)
- `just holy-grail --snapshot data/snapshots/combined_data_<date>_<timestamp>.json --output data/derived_snapshots/<new>.json [--offline] [--previous-snapshot PATH] [--car-category PATH] [--car-proxies PATH]` - enrich a copy of a dated snapshot into a new file (`--config` and `--cache-dir` default to `data/`); never fetches positions or writes Sheets. Without `--car-proxies`, a positive car-business weight leaves `risk_progress_v2` unavailable (`car_proxies_missing`). `just holy-grail --what-if ID_A=+20000 --what-if ID_B=-5000 --offline` - offline before/after on a copy; reads only, writes nothing.
- `just holy-grail-sheet --snapshot data/derived_snapshots/<new>.json --spreadsheet-id ID --sheet-id GID --dry-run` - update only the owned Holy Grail region of a dated worksheet; rerun with `--apply` only after the owner approves the dry run.
- `just risk-progress --snapshot data/snapshots/combined_data_<date>_<timestamp>.json [--car-proxies PATH]` - offline view of the older `risk_progress_v1` (covered groups, car-business scenarios when a proxy block exists); reads a saved snapshot, writes nothing unless `--out NEW_FILE` is given. The headline `risk_progress_v3` (with private streams from the `private_streams` config key) and `risk_progress_v2` are derived by `just run` (basket collected automatically) or `just holy-grail --car-proxies PATH` (explicit frozen block, offline; declared private streams need their factor and proxy histories in the cache, so the first run after declaring them is online)
- `just car-proxies build --raw data/car_category/raw_<date> --proxy-csv <csv> --as-of <as_of_date> --out data/car_category/proxies_<date>.json` - freeze the public used-vehicle proxy series (offline, refuses to overwrite); copy to `data/car_category/proxies_latest.json` so `just run` imports the auxiliary price-index series into the `car_proxies_v3` block (the CPRT/KMX/OPLN basket itself is collected automatically and needs no `--proxy-csv` each month) and derives `risk_progress_v1`. `report --block PATH` prints the series. `fetch-ukraine --raw data/car_category/raw_<date> --as-of <as_of_date>` first downloads the Ukrstat vehicle CPI and the NBU USD rates into the raw directory (network, never overwrites); without them the Ukrainian series is left out of the block.

### Car-category tracker (method v3)

- `just car-category build --raw data/car_category/raw_<date> --long-returns <csv> --as-of <as_of_date> --out data/car_category/block_<date>.json` - freeze the Manheim index and long group histories into one block (offline, refuses to overwrite). Copy it to `data/car_category/block_latest.json` for `just run` to derive `allocation_score_v3`; `just holy-grail --car-category PATH` does the same for a derived snapshot copy.
- `just car-category report --snapshot PATH --block PATH [--append-history data/car_category/history.jsonl]` - per-group correlations with the used-vehicle price index, v2 vs v3 scores, and the equivalent uniform car correlation. Read-only apart from the optional append-only history.
- `just car-crisis --raw ... --long-returns ... --out ... [--fetch-manheim-url URL --as-of DATE [--bls-contact CONTACT]]` - H1-H3 crisis test; the fetch variant downloads the raw files into a new directory first (BLS needs a contact you choose, otherwise its CPI file is skipped). See `docs/car-flip-category-evidence.md`.
- `just car-proxy` - listed auto-remarketing equity basket vs the car business (equity beta, not a measurement; superseded by the price index above).
- Data lives in ignored `data/car_category/`; method notes are in `docs/diversification-methodology.md` (v3 section).

### `just run` (portfolio sync pipeline)

By default (`just run` with no flags):
1. Fetches live positions from IB Gateway (`ib_insync`)
2. Fetches YTD performance from IB Flex Web Service
3. Calculates allocation and dividend income (yfinance/Yahoo)
4. Writes `data/snapshots/combined_data_<date>_<timestamp>.json` (+ `_latest.json`)
5. Updates Google Sheets (`data/credentials.json`)
6. Skips history sync and Dalio analysis by default

Full data collection (all sources + history + Dalio):
```bash
just run -- --run-history-sync --run-dalio-analysis
```

Key flags:
- `--force-refresh` - re-fetch all data sources
- `--skip-sheet-update` - skip Google Sheets write
- `--run-history-sync` - sync monthly history from Google Sheets
- `--run-dalio-analysis` - run Dalio risk analyzer
- `--dalio-only` - skip fetch, run Dalio on existing CSV

Full flag list: `python -m src.portfolio_sync --help` or see `README.md`.

Required env vars (in `data/ib_flex_env.sh`): `IB_GATEWAY_HOST`, `IB_GATEWAY_PORT`, `IB_FLEX_TOKEN`, `IB_FLEX_QUERY_ID_YTD_PERFORMANCE`, `IB_ACCOUNT_ID`. For the quarterly report also: `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` (see `.agents/skills/quarterly-report/SKILL.md`).

Outputs: `data/snapshots/combined_data_*.json`, `data/portfolio_history.csv`, `data/portfolio_history.jsonl`, `analytics/output/` (Dalio).

### `just report` flags

`just report` runs both the Markdown generator (`analyze_portfolio_reports.py`) and the HTML generator (`generate_quarterly_report.py`) with no passthrough flags. To pass flags to the HTML generator, invoke it directly:

```bash
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --before path.json
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --ibkr-ytd -6.8 --sp500-ytd 9.3
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --output path.html --open
```

- `--before PATH` - explicit start-of-quarter `data/snapshots/combined_data_*.json` snapshot. Auto-selected otherwise: newest one dated on or before quarter start + 5 days grace that carries allocation data.
- `--ibkr-ytd N` / `--sp500-ytd N` - override the YTD figures (default: from `data/final_data.json`).
- `--output PATH` - output HTML path (default: `portfolio_yic_reports/portfolio_report_qN_YYYY.html`).
- `--open` - open the generated report in a browser.

### `just fetch-snapshots`

Downloads the artifacts of the last 4 runs of `.github/workflows/flex-snapshot.yml` (positions and quarterly trades XML) into `data/ib_flex_snapshots/` with the authenticated `gh` CLI. Download failures are suppressed and artifacts can land in nested folders: inspect the XML and keep validated exports in the top-level directory. There is no recipe for a direct fetch; a missing export is fetched with `IBFlexPortfolioFetcher` (`src/brokers/ib_flex_portfolio.py`; needs `IB_FLEX_TOKEN` and the query id env var, see `data/ib_flex_env.sh`), as shown in the `quarterly-report` skill.
