# Holy Grail / diversification reference

Load this for any task on the diversification score, asset correlation, concentration limits, the what-if CLI, the car-category tracker (v3), risk progress, or the saved `DIVERSIFICATION_DATA` record.

This is a map, not the methodology. Formulas, thresholds and policy live in `docs/diversification-methodology.md`, which wins on any conflict. Link to its headings by name, not by line number. The repo is public: never put holdings, weights, amounts, scores or account ids from `data/` into tracked files.

## 1. What exists

| Layer | Status | Answers |
|---|---|---|
| `capital_diversification_v2` (`DIVERSIFICATION_DATA.allocation_score_v2`) | Current base method, calculated for new snapshots and sealed. | How invested capital is spread across economic groups that are not correlated with each other, plus equity-sector breadth. |
| `capital_diversification_v3` (`DIVERSIFICATION_DATA.allocation_score_v3`) | Optional sibling of v2, present only when a frozen car-category block is supplied. | The v2 score with the Car Resale pairs taken from a public used-vehicle price index instead of the fixed 0.25. A category proxy, not a measurement of the business. |
| `risk_progress_v1` (`DIVERSIFICATION_DATA.risk_progress_v1`) | Optional sibling of v2, written only when a frozen `car_proxies_v1` block is supplied. Not part of the capital score. | How many independent equal-risk streams (DR-squared, target 15) the covered part of the portfolio behaves like, as points out of 100. Progress, not a grade. Revives the retired risk-equivalent formula on a different basis (frozen v2 group histories). |
| `concentration_v1` (`DIVERSIFICATION_DATA.concentration_v1`; the `version` field inside is `concentration_v2`) | Current. Rendered beside the score. | Issuer, thesis, country and core-bucket limits, which v2 cannot see. |
| v1 capital score, risk-equivalent count and DR-squared, ten-check policy, simple indicator | Frozen. Rendered only from records that already contain them. | Historical comparisons. Never trend them against v2. |
| `analytics/dalio_holy_grail.py` | Separate standalone analyzer (`main.py --run-dalio-analysis`, `python3 -m analytics.dalio_holy_grail --help`). Not part of the saved score. | Independent risk sources (README "Dalio Holy Grail Analyzer"). |

"How correlated are my assets with each other" is answered by the `pairs` inside the v2 scenarios (the v3 scenarios copy every non-car pair from v2). Those are correlations between economic groups, not between individual holdings.

## 2. Data flow

1. `DataSource.get_combined_data` (`src/data_source.py`) builds the combined data and calls `holy_grail_data.enrich_combined_data`.
2. `extract_exposures` turns positions into exposures; `allocation_inputs.allocation_history_requests` lists the group representatives needed.
3. `collect_return_history` fetches daily prices (yfinance), cached under `data/holy_grail_history`; `monthly_usd_returns` converts them to monthly USD returns.
4. `allocation_v2_inputs.calculate_allocation_score_v2` maps positions to groups with `allocation_inputs.profile_for`, then calls `allocation_score_v2.evaluate_scenarios` and `score_components_v2`.
5. When a frozen car-category block is passed, `allocation_score_v3.derive_allocation_score_v3(v2, block)` builds the sibling record from the saved v2. The argument is `car_category=` on `enrich_combined_data` and `enrich_snapshot_file`, and `--car-category` on the CLI; `DataSource` passes `car_category.load_block()`, which reads `data/car_category/block_latest.json` and returns None when the file is absent. Omitted means no v3 record.
6. When a frozen proxy block is passed, `holy_grail_risk_progress.derive_risk_progress_v1(v2, proxies)` derives `risk_progress_v1` from the saved v2. The argument is `car_proxies=` (same two functions) and `--car-proxies` on the CLI; `DataSource` passes `car_risk_proxies.load_block()`, which reads `data/car_category/proxies_latest.json` and returns None when absent. Omitted means no record.
7. `concentration_v1.build_block` and `match_decisions` build the concentration block from the same frozen inputs (it stays on v2).
8. All results are saved under `DIVERSIFICATION_DATA` in the combined-data snapshot (`data/snapshots/combined_data_*.json`).
9. `diversification_view.saved_diversification_view` selects the public view. A saved v2 record always goes through `allocation_view.allocation_view_v2(data, expected_date, saved_at_utc)` (older records use their own views), which replay-validates the v2 record, and a v3 or risk-progress record when present, against their own frozen inputs. The view never fetches data or reads today's config.
   - v3: valid, it supplies the headline and scenarios; unavailable, the v2 numbers show with a warning; failing replay, it renders unavailable.
   - Risk progress (`holy_grail_risk_progress.validate_saved_risk_progress_v1`): valid, it adds the summary row "Ризиковий прогрес" (after "Сценарний розкид") and a paragraph in the conclusion note; failing replay, the row shows "Недоступно" instead of a number and the rest of the view is unaffected; absent, the view is unchanged.
   - The note under the conclusion comes from `car_resale_market.conclusion_note` (frozen `CAR_RESALE_MARKET_CONTEXT`).
10. The view feeds Google Sheets (`src/google_sheets/insights_tables.py`; the scoped writer is `analytics/holy_grail_sheet.py`) and the quarterly HTML (`portfolio_yic_reports/generate_quarterly_report.py`). Both Sheets writers deliver the conclusion note as an owned cell note (marker `car_resale_market.NOTE_MARKER`) and treat a foreign note as a conflict.

Historical snapshots take a different entry: `holy_grail_data.enrich_snapshot_file` (via `just holy-grail`) enriches a copy and writes a new derived file.

## 3. Module map (`analytics/`)

| Module | Role |
|---|---|
| `holy_grail_cli.py` | CLI: enrich a copy of a dated snapshot (optional `--car-category` and `--car-proxies`), or run `--what-if`. Never fetches positions or writes Sheets. |
| `holy_grail_data.py` | `enrich_combined_data`, `enrich_snapshot_file`, exposure extraction, return-history collection and cache, `load_config`. |
| `allocation_inputs.py` | Economic `GROUPS` (label and representative ticker), `allocation_settings`, `profile_for` (dated profile lookup and category defaults), history requests, result sealing. |
| `allocation_v2_inputs.py` | `METHOD`, `calculate_allocation_score_v2`, risk facts, replay validation (`validate_saved_allocation_v2`), previous-record attribution. |
| `allocation_score_v2.py` | Pure math: `score_components_v2`, `evaluate_scenarios`, `category`. |
| `allocation_score_v3.py` | `derive_allocation_score_v3` (sibling record from the saved v2 plus a frozen block), `validate_saved_allocation_v3` (full replay from the saved v2 and the embedded block), `HEADLINE`, `METHOD_V3`. |
| `allocation_score.py` | v1 score plus helpers v2 still imports (`monthly_window`, `pair_correlations`, `correlation_map`, `history_frame`, `history_payload`). Do not remove. |
| `holy_grail.py` | `fingerprint`, `holdings_fingerprint`, `completed_month_end` (used by v2) and `saved_progress_view` for legacy records. |
| `concentration_v1.py` | Issuer, thesis, core and country facts, limits, decision matching, saved-block validation. |
| `what_if.py` | Offline before/after on a copied snapshot (`run`). |
| `diversification_view.py` | `saved_diversification_view`: dispatch to the public view of a saved record. |
| `allocation_view.py` | Public whitelist views (`allocation_view_v2` for v2, v3 and the risk-progress row, `allocation_view` for v1 records) and the concentration section. |
| `holy_grail_sheet.py` | Scoped, readback-verified Sheets writer for the saved view. |
| `car_category.py` | `build_block`, `validate_block`, `load_block`, `METHOD`, `group_measures` (three correlation measures per group), and the tracker CLI `build` / `report` (`just car-category`). |
| `car_category_data.py` | Offline parsers and sha256 manifest for the public used-vehicle datasets. `fetch_raw` and `long_group_returns` are the only network entry points and are called explicitly. |
| `car_crisis_test.py` | H1-H3 crisis test of the index against the groups (`just car-crisis`); write-up in `docs/car-flip-category-evidence.md`. |
| `car_industry_proxy.py` | One retrospective check of the car business against a listed industry basket (`just car-proxy`). Equity beta, not a measurement of the business. |
| `car_resale_market.py` | `build_context`, `validated_context`, `conclusion_note`, `NOTE_MARKER`: frozen public market context shown beside the score, not part of it. |
| `holy_grail_risk_progress.py` | `derive_risk_progress_v1` (sibling record from the saved v2, optional proxy block), `validate_saved_risk_progress_v1` (full replay), and the offline CLI (`just risk-progress`). Imported by `holy_grail_data` and `allocation_view`. |
| `car_risk_proxies.py` | `build_block`, `validate_block`, `load_block`, `METHOD`: the frozen `car_proxies_v1` block of public used-vehicle proxy series (`just car-proxies build` / `report`). |
| `diversification_inputs.py` | `quality_inputs_fingerprint`. |
| `diversification_quality.py` | `reviewed_record` (dated risk-evidence validation) and legacy check summaries. |
| `holy_grail_indicator.py`, `holy_grail_indicator_view.py` | Validation and public view of the frozen simple indicator. |
| `dalio_holy_grail.py` | Standalone Dalio analyzer (section 1). |
| `risk_analyzer.py` | Standalone heuristic 1-10 per-asset risk scorer (`PortfolioRiskAnalyzer`); not imported by the pipeline. |

The group list and each group's representative ticker live in `analytics/allocation_inputs.py` (`GROUPS`). Read them there instead of copying them into prose.

## 4. Inputs and local artifacts

- Public profiles: `analytics/models/economic_profiles_v1.json` (dated economic profiles, sector shares, optional fund `holdings`). Its `core: true` flag is also used by the quarterly report's core/satellite split.
- Private config: `data/holy_grail_config.json`. Top-level keys: `schema_version`, `mappings`, `qualifications`, `indicator`, `allocation` (`profiles`, `method_version`, optional `concentration_limits`, `linked_theses`, `concentration_decisions`), and optional `diversification`. Of that block the current code reads only `diversification.exposures` (v2 risk facts); `policy` and `cash_components` belong to the retired ten-check calculators. See "Private evidence and collection" in the methodology doc.
- Ignored local artifacts: `data/holy_grail_history/` (price cache), `data/derived_snapshots/` (derived enrichments), `data/snapshots/combined_data_*.json` (saved records), `data/car_category/` (the car-category block `block_latest.json`, the proxy block `proxies_latest.json`, raw dataset files, `history.jsonl`).
- Optional context: a derived snapshot may carry `CAR_RESALE_MARKET_CONTEXT`, a manually collected one-time public dataset frozen with `car_resale_market.build_context`. Related docs: `docs/car-resale-market-context.md` (note rules), `docs/car-flip-category-evidence.md` (crisis test), `docs/car-deal-ledger.md` (deal record schema).
- Snapshot envelope: `{as_of_date, saved_at_utc, source, data}`. The record is under `data`.

## 5. Saved record map

`DIVERSIFICATION_DATA.allocation_score_v2` (structure only):

- Result: `status` (`modeled`, `provisional`, `unavailable`, `not_applicable`), `score`, `display_score`, `category`, `warnings`, `input_flags`.
- Composition: `groups`, `sectors`, `profiles`, `positions`, `coverage` (including `unknown_pct_invested` and `missing_pair_max_points`).
- Scenarios: `scenarios` with keys `m60_r025`, `m60_r075`, `m36_r025`, `m36_r075` (window months, Car Resale correlation). Each has `pairs` with `kind`, `correlation`, `observations`, `last_month`.
- Judgement aids: `assessment` (`business_dependent`, `window_dependent`, `combined_dependent`, min and max across available scenarios), `risk_facts`, `risk_unknown`, `comparison` (previous-record attribution).
- Integrity: `histories`, `configuration`, and the fingerprints checked on replay.

`DIVERSIFICATION_DATA.allocation_score_v3` (structure only): the v2 result fields plus:

- `measures`: by window (`m60`, `m36`) and group, the three measures `monthly`, `lagged_1m`, `stress_quintile` (each with `r` and `n`), then `selected`, `point`, `upper90`, `n`, `upper_selected`, `upper_n`.
- `scenarios`: `m60_cat_point`, `m60_cat_upper90`, `m60_r075`, `m36_cat_point`, `m36_cat_upper90`, `m36_r075`. Car pairs carry `kind: category` and a `sample` (`monthly`, `lagged_1m`, `stress_quintile`); `r075` copies the v2 assumption.
- `method` (including `headline_scenario`), `car_category` (the embedded frozen block), `source_v2` (fingerprints and score of the v2 it was derived from), `method_fingerprint`, `result_fingerprint`.
- `status` can be `unavailable` with warning `invalid_car_category_block` (stale, unreadable or invalid block).

`DIVERSIFICATION_DATA.risk_progress_v1` (structure only):

- Result: `status` (`modeled`, `provisional`, `unavailable`), `progress_points`, `progress_display`, `warnings` (for example `partial_scope_excluded_weight`).
- `windows`: `m60` (headline) and `m36` (comparison), each with `status` and `effective_streams`. `coverage`: `covered` and `excluded` groups (excluded rows carry a `reason`), `covered_pct_invested`, `excluded_pct_invested`, cash share. `method` (including `target_streams`), `source_v2` (identifiers of the v2 it was derived from), `method_fingerprint`, `result_fingerprint`.
- `car_scenarios` (only when a block was supplied): `status`, `reason` (`invalid_car_proxies_block` when the block fails), `range` (`low_display`, `high_display`), `car_weight_pct_invested`, and `items` by proxy (`manheim_wholesale`, `bls_used_retail`, `auto1_wholesale_eu`, `listed_remarketers`), each with `effective_streams`, `baseline_streams` (the covered-only count on the scenario's own months), `delta_streams` (their difference), `progress_display`, `correlation_covered`, `relation`, `effect`.

## 6. Evidence status and data sufficiency

What the score rests on, by `kind` of pair:

- `measured`: group-representative ETF monthly USD returns, a 60-month window ending at the last completed month (36-month alternative), at least 36 real overlapping months per pair, no zero-filling.
- `modeled`: in v2 (and in the v3 `r075` stress scenario) pairs involving the Car Resale business use an assumed correlation (0.25 main, 0.75 sensitivity). There is no observed business return series.
- `category`: v3 only. A Car Resale pair taken as R x rho(group, public used-vehicle price index) with R fixed at 1. Per group the largest of three measures (same-window monthly, a one-month price lag, equity-stress months since 1997); their samples differ, so each pair stores its `sample` and `observations`. A price-channel scenario assumption, not a measurement of the business and not a bound on it.
- `missing`: fewer than 36 overlapping months, zero variance, or a history that failed to load (the run then sets the `history_collection_incomplete` flag). Treated as correlation 1; `coverage.missing_pair_max_points` bounds the effect. A missing-pair effect above 5 points makes that scenario unavailable (`insufficient_pair_coverage`). Unknown invested weight above 5% makes the whole result unavailable (`insufficient_coverage`).

Where assumptions enter besides the business pairs:

- Crypto lending and P2P default to the `credit_hy_usd` group (HYG representative) through the category model in `profile_for`, unless a dated profile overrides it. Their pairs show as `measured` because HYG's history is real, so `kind` does not flag this proxy; proxy-mapped positions carry `kind: proxy` in `positions`.
- A confirmed short individual Treasury uses a dated private mapping to the SHV group.
- Single stocks collapse into their group representative; correlation between two holdings in the same group is not measured.
- Sector breadth comes from reviewed profiles, not live data. Unknown equity-sector weight goes to the largest known sector.

Risk progress rests on the same v2 group histories (one representative series per group, common months only, never zero-filled; 60-month headline, 36-month comparison). Its headline covers only groups with a return history: `car_business` has none, is excluded and reported (`partial_scope_excluded_weight`), and enters only as labeled scenarios "the business behaves like public series X" from the frozen `car_proxies_v1` block: Manheim (US wholesale), BLS used-car CPI (US retail), AUTO1 (EU wholesale, scraped, medium confidence) and an equal-weight basket of CPRT, KMX and OPLN (equity-like). These are category proxies, never the return of the business, and they are shown as a range that is wide on purpose: only the owner's own monthly numbers could say which proxy is closer. The points scale is a policy choice, not a percentage of risk.

Not collected: a Car Resale return series (v3 and the risk-progress scenarios add public category proxies, not business data), return histories for lending and P2P platforms, regimes older than the 60-month window, and pairwise correlation between individual holdings.

Reading the result:

- `assessment.business_dependent` is true when the category differs between the Car Resale scenarios of the same window (v2: 0.25 vs 0.75; v3: `cat_point`, `cat_upper90`, `r075`). Read the min/max range, not only the headline.
- In v3 the headline is `m60_cat_point` (`HEADLINE`, a judgment call). `cat_upper90` uses nominal per-estimate Fisher endpoints: a sensitivity, not a confidence interval for the score.
- Sampling noise: near zero correlation the standard error is about 0.13 at n=60 and about 0.17 at n=36, so small differences between pairs are noise.

Check data sufficiency on any snapshot (prints counts and flags only, no weights or scores):

```python
import json
import sys
from collections import Counter

payload = json.load(open(sys.argv[1]))
data = payload.get('data', payload)  # saved snapshots wrap the record in "data"
records = data['DIVERSIFICATION_DATA']
for name in ('allocation_score_v2', 'allocation_score_v3'):
    record = records.get(name)
    if record is None:
        print(name, 'absent')
        continue
    print(name, 'status:', record['status'], '| warnings:', record['warnings'])
    print('  unknown_pct_invested:', round(record['coverage']['unknown_pct_invested'], 2))
    for key, scenario in record['scenarios'].items():
        kinds = Counter(pair['kind'] for pair in scenario['pairs'])
        observed = [pair['observations'] for pair in scenario['pairs'] if pair['kind'] in ('measured', 'category')]
        print(' ', key, scenario['status'], dict(kinds), 'observations:', (min(observed), max(observed)) if observed else None)
    print('  assessment flags:', {k: v for k, v in record['assessment'].items() if isinstance(v, bool)})
print('risk_unknown keys:', sorted((records.get('allocation_score_v2') or {}).get('risk_unknown', {})))
progress = records.get('risk_progress_v1')
if progress is None:
    print('risk_progress_v1 absent')
else:
    print('risk_progress_v1 status:', progress['status'], '| warnings:', progress['warnings'],
          '| car scenarios:', (progress.get('car_scenarios') or {}).get('status', 'none'))
```

Next data worth collecting, in priority order:

1. A Car Resale monthly series. It is the only way to replace the R = 1 assumption in v3, the proxy scenarios in risk progress and the 0.25 / 0.75 assumption in v2. The methodology doc and `docs/car-deal-ledger.md` require dated inventory, cost and proceeds records; the record types live in `src/portfolio_ledger/contract.py`.
2. Monthly return histories for the crypto lending and P2P platforms, to replace the HYG proxy.

## 7. Commands

```bash
# Enrich a copy of a dated snapshot (new file; --config and --cache-dir default to data/)
just holy-grail --snapshot data/snapshots/combined_data_<date>_<ts>.json \
  --output data/derived_snapshots/<new>.json --offline
# optional: --previous-snapshot PATH for attribution
# optional: --car-category PATH (a frozen block) also derives the v3 record; omitted means no v3
# optional: --car-proxies PATH (a frozen proxy block) also derives risk_progress_v1; omitted means none

# Offline risk progress for a saved snapshot (validates by replay, writes nothing unless --out NEW_FILE)
just risk-progress --snapshot data/snapshots/combined_data_<date>_<ts>.json

# Offline what-if on a copy (repeatable; reads only, writes nothing)
just holy-grail --what-if ib:VOO=+20000 --what-if ib:9988=-5000 --offline

# Update only the owned Holy Grail region of a dated worksheet
just holy-grail-sheet --snapshot data/derived_snapshots/<new>.json \
  --spreadsheet-id ID --sheet-id GID --dry-run    # then --apply
```

Car-category tracker (`just car-category build|report`, `just car-crisis`, `just car-proxy`) and the proxy block (`just car-proxies build|report`): flags are in `.agents/references/commands.md`, section "Car-category tracker (method v3)" and the `just risk-progress` and `just car-proxies` bullets.

Report rendering from a derived snapshot: `generate_quarterly_report.py --after PATH` (see the `quarterly-report` skill section "Holy Grail saved-data enrichment"). Walkthrough and constraints: methodology doc sections "Offline what-if scenarios" and "Simple Holy Grail indicator (v1)" (replay and scoped delivery).

## 8. Gotchas

- A missing `data/holy_grail_config.json`, or one without an `allocation` object, silently produces no v2 block. A malformed config produces an `unavailable` record (`invalid_allocation_config`). The `portfolio-sync` skill preflight exists for this reason; run it before any live write.
- The derived output path must be new, outside the source directory and outside `data/snapshots/`, and never `combined_data_latest.json` or `final_data.json`.
- `--offline` uses cached public history only. A series missing from the cache sets `history_collection_incomplete` and its pairs become `missing`, which leaves scenarios provisional or unavailable.
- Never fall back from an invalid v2 record to v1 or a previous result, or from an invalid v3 record to v2.
- Two optional frozen blocks switch the sibling records on: `data/car_category/block_latest.json` (v3) and `data/car_category/proxies_latest.json` (risk progress). With no block there is no record, and that is not an error, so merging the code enables neither. `just car-category build` and `just car-proxies build` refuse to overwrite an existing output path.
- Rebuild both blocks every month, after the new month's source data is published. A block is accepted only while its newest month (every series, for the proxy block) is at most one month behind the snapshot's completed month (`max_index_lag_months` in `car_category.METHOD`, `max_lag_months` in `car_risk_proxies.METHOD`). A stale or invalid v3 block (including a `car_category_v1` block) gives an `unavailable` v3 record and the view shows the v2 numbers with a warning. A stale or invalid proxy block keeps the risk-progress headline and shows the car scenarios as `unavailable` (`invalid_car_proxies_block`).
- `just risk-progress` validates the saved v2 by replay, changes no snapshot, fetches nothing and never writes Sheets; `--out` writes a new file only, outside the automatic snapshot directories.
- `what_if.py` and `concentration_v1.py` stay on v2.
- The market-context note needs the snapshot's timezone-aware `saved_at_utc`; without it the note is unavailable while the score still renders. A foreign cell note at the target is a conflict (`SheetConflictError` in the full writer, `ValueError` in the scoped one).
- The Sheets writer edits only its owned region and refuses on conflict or insufficient grid space. After a write error, read back before any retry.
- Frozen-record validation replays from saved histories and the saved configuration, never from today's config. Changing a profile does not change an old record.
- Do not copy score formulas or concentration limits here or into `AGENTS.md`; link the methodology heading. The data-sufficiency constants in section 6 mirror the code: re-check them when `analytics/` changes.
