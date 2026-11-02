# Holy Grail / diversification reference

Load this for any task on the diversification score, asset correlation, concentration limits, the what-if CLI, the car-category tracker (v3), the single risk-progress headline (`risk_progress_v2`) and its car proxy block, or the saved `DIVERSIFICATION_DATA` record.

This is a map, not the methodology. Formulas, thresholds and policy live in `docs/diversification-methodology.md`, which wins on any conflict. Link to its headings by name, not by line number. The repo is public: never put holdings, weights, amounts, scores or account ids from `data/` into tracked files.

## 1. What exists

| Layer | Status | Answers |
|---|---|---|
| `capital_diversification_v2` (`DIVERSIFICATION_DATA.allocation_score_v2`) | Current base method, calculated for new snapshots and sealed. | How invested capital is spread across economic groups that are not correlated with each other, plus equity-sector breadth. |
| `capital_diversification_v3` (`DIVERSIFICATION_DATA.allocation_score_v3`) | Optional sibling of v2, present only when a frozen car-category block is supplied. | The v2 score with the Car Resale pairs taken from a public used-vehicle price index instead of the fixed 0.25. A category proxy, not a measurement of the business. |
| `risk_progress_v2` (`DIVERSIFICATION_DATA.risk_progress_v2`) | Current headline for new snapshots, derived from the saved v2 and a frozen car proxy block (`car_proxies_v3` from normal collection, `car_proxies_v2` for offline recalculation). | One 0-100 score over all invested weights: the diversification ratio DR of the group representatives (car business through the labelled CPRT/KMX/OPLN basket), DR-squared mapped linearly with target 15 independent streams. Details: risk contribution by group, worst modelled months, a car-business write-off scenario, a qualitative environment map, volatility sensitivity and a proxy comparison. A modelled effect of diversification, not a grade, forecast or measurement of the business. |
| `risk_progress_v1` (`DIVERSIFICATION_DATA.risk_progress_v1`) | Older optional sibling of v2, kept for its own records and details, written only when a frozen car proxy block (`car_proxies_v1` or `car_proxies_v2`) is supplied. Not part of the capital score and not the headline. | How many independent equal-risk streams (DR-squared, target 15) the covered part of the portfolio behaves like, as points out of 100. Progress, not a grade. Revives the retired risk-equivalent formula on a different basis (frozen v2 group histories). |
| `concentration_v1` (`DIVERSIFICATION_DATA.concentration_v1`; the `version` field inside is `concentration_v2`) | Current. Rendered beside the score. | Issuer, thesis, country and core-bucket limits, which v2 cannot see. |
| v1 capital score, risk-equivalent count and DR-squared, ten-check policy, simple indicator | Frozen. Rendered only from records that already contain them. | Historical comparisons. Never trend them against v2. |
| `analytics/dalio/dalio_holy_grail.py` | Separate standalone analyzer (`main.py --run-dalio-analysis`, `python3 -m analytics.dalio.dalio_holy_grail --help`). Not part of the saved score. | Independent risk sources (README "Dalio Holy Grail Analyzer"). |

"How correlated are my assets with each other" is answered by the `pairs` inside the v2 scenarios (the v3 scenarios copy every non-car pair from v2). Those are correlations between economic groups, not between individual holdings.

## 2. Data flow

Module names are relative to `analytics/holy_grail/` (see section 3). Code outside the package imports only `analytics.holy_grail.api`.

1. `DataSource.get_combined_data` (`src/data_source.py`) builds the combined data and calls `enrich.enrich_combined_data`.
2. `exposures.extract_exposures` turns positions into exposures; `allocation_inputs.allocation_history_requests` lists the group representatives needed.
3. `market_history.collect_return_history` fetches daily prices (yfinance), cached under `data/holy_grail_history`; `market_history.monthly_usd_returns` converts them to monthly USD returns.
4. `allocation_v2_inputs.calculate_allocation_score_v2` maps positions to groups with `allocation_inputs.profile_for`, then calls `allocation_score_v2.evaluate_scenarios` and `score_components_v2`.
5. When a frozen car-category block is passed, `allocation_score_v3.derive_allocation_score_v3(v2, block)` builds the sibling record from the saved v2. The argument is `car_category=` on `enrich_combined_data` and `enrich_snapshot_file`, and `--car-category` on the CLI; `DataSource` passes `car.category.load_block()`, which reads `data/car_category/block_latest.json` and returns None when the file is absent. Omitted means no v3 record.
6. `risk_progress.derive_risk_progress_v2(v2, proxies)` derives the headline `risk_progress_v2` from the saved v2 and a frozen proxy block (`derive_risk_progress_v1` still derives the older sibling from a v1/v2 block). Normal collection (`DataSource`, `collect_car_basket=True` on `enrich_combined_data`) fetches the CPRT/KMX/OPLN basket itself through the existing price seam and cache when the car business has a positive weight, freezes it as `car_proxies_v3` and imports the auxiliary price-index series from `car.risk_proxies.load_block()` (`data/car_category/proxies_latest.json`, optional). An explicit `car_proxies=` block (and `--car-proxies` on the CLI) is used verbatim with no collection: that is the offline and historical path. The record is written even when the inputs fail, as `unavailable` with a reason; it is never silently absent.
7. `concentration_v1.build_block` and `match_decisions` build the concentration block from the same frozen inputs (it stays on v2).
8. All results are saved under `DIVERSIFICATION_DATA` in the combined-data snapshot (`data/snapshots/combined_data_*.json`).
9. `views.diversification.saved_diversification_view` selects the public view. A saved v2 record always goes through `views.allocation.allocation_view_v2(data, expected_date, saved_at_utc)` (older records use their own views), which replay-validates the v2 record, and the sibling records present, against their own frozen inputs. The view never fetches data or reads today's config.
   - `risk_progress_v2` present (`views/risk_progress_v2.py`): it decides the headline before any other gate. Valid, the summary shows one score with the scale anchor, the two largest modelled risk contributions and the car-business proxy assumption, and the details hold the rest; failing replay, the headline is "Недоступно" and the view never falls back to v2, v3 or `risk_progress_v1`. A corrupt v3 or `risk_progress_v1` sibling is marked unavailable in its own detail row and does not block a valid headline.
   - No `risk_progress_v2` key (older snapshots): v3 and v2 as before. v3 valid supplies the headline and scenarios; unavailable, v2 shows with a warning and a suffix in the conclusion cell; failing replay, the view renders unavailable. A valid `risk_progress_v1` adds the summary row "Ризиковий прогрес" and a paragraph in the conclusion note; failing replay, the row shows "Недоступно".
   - The note under the conclusion comes from `car.resale_market.conclusion_note` (frozen `CAR_RESALE_MARKET_CONTEXT`).
10. The view feeds Google Sheets (`src/google_sheets/insights_tables.py`; the scoped writer is `analytics/holy_grail/delivery/sheet.py`) and the quarterly HTML (`portfolio_yic_reports/generate_quarterly_report.py`). Both Sheets writers deliver the conclusion note as an owned cell note (marker `car.resale_market.NOTE_MARKER`, tested with `car.resale_market.is_owned_note`) and treat a foreign note as a conflict.

Historical snapshots take a different entry: `enrich.enrich_snapshot_file` (via `just holy-grail`) enriches a copy and writes a new derived file.

## 3. Module map (`analytics/holy_grail/`)

Outside code imports only `api.py`. Everything else is internal and may move.

| Module | Role |
|---|---|
| `api.py` | The import surface for outside code: `enrich_combined_data`, `saved_diversification_view`, `saved_progress_view`, `load_car_category_block`, `load_car_proxies_block`, `is_owned_note`. |
| `paths.py` | `REPO_ROOT`, `DATA_DIR`, `CONFIG_PATH`, `CACHE_DIR`, the two car block paths and `PROFILE_PATH`. Modules take locations from here instead of computing them from `__file__`. |
| `fingerprint.py` | `fingerprint`, `holdings_fingerprint`, `completed_month_end`: used by every saved record. |
| `cli.py` | CLI (`just holy-grail`): enrich a copy of a dated snapshot (optional `--car-category` and `--car-proxies`), or run `--what-if`. Never fetches positions or writes Sheets. |
| `enrich.py` | Orchestration only: `enrich_combined_data`, `enrich_snapshot_file`, `load_config`. |
| `exposures.py` | `extract_exposures`, `bound_exposure_record`, `iso_date`: positions to dated economic exposures. No network, no scoring. |
| `market_history.py` | `collect_return_history`, `monthly_usd_returns`, `fetch_yfinance_history`, price cache. The only code that fetches prices. |
| `correlation.py` | Monthly windows and pairwise correlations shared by every method version (`monthly_window`, `pair_correlations`, `correlation_map`, `history_frame`, `history_payload`). |
| `evidence.py` | `quality_inputs_fingerprint` (fingerprint of the saved inputs) and `reviewed_record` (dated risk-evidence validation). |
| `allocation_inputs.py` | Economic `GROUPS` (label and representative ticker), `allocation_settings`, `profile_for` (dated profile lookup and category defaults), history requests, `seal_result`. |
| `allocation_v2_inputs.py` | `METHOD`, `calculate_allocation_score_v2`, risk facts, replay validation (`validate_saved_allocation_v2`), previous-record attribution. |
| `allocation_score_v2.py` | Pure math: `score_components_v2`, `evaluate_scenarios`, `category`, `same_value` (bounded equality for replay). |
| `allocation_score_v3.py` | `derive_allocation_score_v3` (sibling record from the saved v2 plus a frozen block), `validate_saved_allocation_v3` (full replay from the saved v2 and the embedded block), `HEADLINE`, `METHOD_V3`, and `group_weights` / `scenario_with_car_pairs` (car pairs substituted into the saved base scenario; ). |
| `concentration_v1.py` | Issuer, thesis, core and country facts, limits, decision matching, saved-block validation. |
| `what_if.py` | Offline before/after on a copied snapshot (`run`). |
| `risk_progress.py` | `derive_risk_progress_v2` / `validate_saved_risk_progress_v2` (the headline record and its full replay) and the unchanged `derive_risk_progress_v1` / `validate_saved_risk_progress_v1`, plus the offline CLI (`just risk-progress`, v1). Imported by `enrich` and the views. |
| `views/diversification.py` | `saved_diversification_view`: dispatch to the public view of a saved record. |
| `views/allocation.py` | Public whitelist views (`allocation_view_v2` for v2, v3, the older risk-progress row and the dispatch to the headline view, `allocation_view` for v1 records) and the concentration section. |
| `views/risk_progress_v2.py` | `risk_progress_v2_view`: the headline view (score, three headline lines, details, qualitative environment map). Formats saved values only. |
| `views/common.py` | `empty_view`: the unavailable view every renderer falls back to. |
| `delivery/sheet.py` | Scoped, readback-verified Sheets writer for the saved view (`just holy-grail-sheet`). |
| `car/category.py` | `build_block`, `validate_block`, `load_block`, `METHOD`, `group_measures` (three correlation measures per group). A leaf: imports no score module. |
| `car/tracker_cli.py` | Tracker CLI `build` / `report` (`just car-category`); the only car module that imports the v2 and v3 scores. |
| `car/category_data.py` | Offline parsers and sha256 manifest for the public used-vehicle datasets (including the Ukrstat vehicle CPI and NBU USD rates). `fetch_raw`, `fetch_ukraine` and `long_group_returns` are the only network entry points and are called explicitly. |
| `car/crisis_test.py` | H1-H3 crisis test of the index against the groups (`just car-crisis`); write-up in `docs/car-flip-category-evidence.md`. |
| `car/industry_proxy.py` | One retrospective check of the car business against a listed industry basket (`just car-proxy`). Equity beta, not a measurement of the business. |
| `car/resale_market.py` | `build_context`, `validated_context`, `conclusion_note`, `NOTE_MARKER`, `is_owned_note`: frozen public market context shown beside the score, not part of it. |
| `car/risk_proxies.py` | `build_block`, `validate_block`, `load_block`, `METHOD`, `METHODS`: the frozen car proxy block of public used-vehicle proxy series (`just car-proxies build` / `report` / `fetch-ukraine`). `car_proxies_v2` is the offline block; `car_proxies_v1` blocks embedded in saved records still validate. `inspect_block`, `build_block_v3` and `car/proxy_collection.py` build and check the `car_proxies_v3` block of normal collection (integrity of the block and freshness of each series are judged separately). |
| `legacy/allocation_v1.py` | Frozen `capital_diversification_v1`: score, calibration, `validate_saved_allocation`. |
| `legacy/quality.py` | Frozen ten-check summary: `COUNT_VERSION`, `POLICY_VERSION`, `CHECK_IDS`, `summarize_checks`. |
| `legacy/progress_view.py` | `saved_progress_view` and `CONSTRAINT_LABELS` for the retired `holy_grail_progress_v1` record. |
| `legacy/indicator.py`, `legacy/indicator_view.py` | Validation and public view of the frozen simple indicator. |

Rules, checked by reading imports (a scan of the package finds no cycle, even through function-level imports):

- Nothing outside `views/`, `api.py` and `legacy/` imports `legacy/`.
- Leaf modules (`fingerprint`, `paths`, `correlation`, `exposures`, `market_history`, `evidence`, `views/common`, `car/category`) import none of their consumers. Do not add a function-level import to dodge a cycle: move the shared piece into a leaf.
- A name used by another module is public: no leading underscore.

Outside the package: `analytics/dalio/dalio_holy_grail.py` (standalone Dalio analyzer, section 1), `analytics/risk_analyzer.py` (standalone heuristic 1-10 per-asset risk scorer, `PortfolioRiskAnalyzer`; not imported by the pipeline) and `analytics/models/economic_profiles_v1.json` (profiles, section 4).

The group list and each group's representative ticker live in `analytics/holy_grail/allocation_inputs.py` (`GROUPS`). Read them there instead of copying them into prose.

## 4. Inputs and local artifacts

- Public profiles: `analytics/models/economic_profiles_v1.json` (dated economic profiles, sector shares, optional fund `holdings`). Its `core: true` flag is also used by the quarterly report's core/satellite split.
- Private config: `data/holy_grail_config.json`. Top-level keys: `schema_version`, `mappings`, `qualifications`, `indicator`, `allocation` (`profiles`, `method_version`, optional `concentration_limits`, `linked_theses`, `concentration_decisions`), and optional `diversification`. Of that block the current code reads only `diversification.exposures` (v2 risk facts); `policy` and `cash_components` belong to the retired ten-check calculators. See "Private evidence and collection" in the methodology doc.
- Ignored local artifacts: `data/holy_grail_history/` (price cache), `data/derived_snapshots/` (derived enrichments), `data/snapshots/combined_data_*.json` (saved records), `data/car_category/` (the car-category block `block_latest.json`, the proxy block `proxies_latest.json`, raw dataset files, `history.jsonl`).
- Optional context: a derived snapshot may carry `CAR_RESALE_MARKET_CONTEXT`, a manually collected one-time public dataset frozen with `car.resale_market.build_context`. Related docs: `docs/car-resale-market-context.md` (note rules), `docs/car-flip-category-evidence.md` (crisis test), `docs/car-deal-ledger.md` (deal record schema).
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

`DIVERSIFICATION_DATA.risk_progress_v2` (structure only):

- Result: `status` (`modeled`, `provisional`, `unavailable`, `not_applicable`), `reason`, `progress_points` (full precision), `progress_display` (`headline` integer, `detail` one decimal rounded down), `warnings`, `retrospective`, `data_vintage`. Numeric headline fields are null unless the status is modeled or provisional.
- `windows`: `m60` (headline) and `m36` (diagnostic), each with `effective_streams`, `diversification_ratio`, `capital_weights`, `risk_share` (Euler share, may be negative, sums to 1), `annual_volatility_pct` by group and `annual_portfolio_volatility_pct`.
- `coverage` (all positive invested groups, the car proxy, cash outside), `sensitivity` (`proxy_comparison` over four representatives and `volatility` multipliers, kept apart), `stress` (worst modelled months and the car-business write-off scenario), `car_proxies` and `car_proxies_fingerprint` (the embedded frozen block), `source_v2`, `method`, `method_fingerprint`, `result_fingerprint`.

`DIVERSIFICATION_DATA.risk_progress_v1` (structure only):

- Result: `status` (`modeled`, `provisional`, `unavailable`), `progress_points`, `progress_display`, `warnings` (for example `partial_scope_excluded_weight`).
- `windows`: `m60` (headline) and `m36` (comparison), each with `status` and `effective_streams`. `coverage`: `covered` and `excluded` groups (excluded rows carry a `reason`), `covered_pct_invested`, `excluded_pct_invested`, cash share. `method` (including `target_streams`), `source_v2` (identifiers of the v2 it was derived from), `method_fingerprint`, `result_fingerprint`.
- `car_scenarios` (only when a block was supplied): `status`, `reason` (`invalid_car_proxies_block` when the block fails), `range` (`low_display`, `high_display`), `car_weight_pct_invested`, and `items` by proxy (`manheim_wholesale`, `bls_used_retail`, `auto1_wholesale_eu`, `listed_remarketers`, and `ukraine_vehicle_cpi` with a v2 block), each with `effective_streams`, `baseline_streams` (the covered-only count on the scenario's own months), `delta_streams` (their difference), `progress_display`, `correlation_covered`, `relation`, `effect`.

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

The headline `risk_progress_v2` rests on the same v2 group histories with every positive invested weight included: `car_business` enters through the equal-weight monthly total return of CPRT, KMX and OPLN (all three required, no forward fill), labelled as a proxy and an owner assumption, never as a measurement of the business. The score needs at least 36 common months (36-59 is provisional), a last common month at most one month behind the completed month (a one-month lag is provisional), and a positive weight without a usable series makes it unavailable instead of dropping the group. Manheim, BLS, AUTO1 and the Ukrstat CPI only feed the comparison, never the headline. The older `risk_progress_v1` rests on the same v2 group histories (one representative series per group, common months only, never zero-filled; 60-month headline, 36-month comparison). Its headline covers only groups with a return history: `car_business` has none, is excluded and reported (`partial_scope_excluded_weight`), and enters only as labeled scenarios "the business behaves like public series X" from the frozen proxy block: Manheim (US wholesale), BLS used-car CPI (US retail), AUTO1 (EU wholesale, scraped, medium confidence), an equal-weight basket of CPRT, KMX and OPLN (equity-like) and, in a `car_proxies_v2` block, the Ukrstat national CPI "purchase of vehicles" in USD at the NBU monthly mean rate (new and used vehicles mixed, medium confidence). These are category proxies, never the return of the business, and they are shown as a range that is wide on purpose: only the owner's own monthly numbers could say which proxy is closer. The points scale is a policy choice, not a percentage of risk.

Not collected: a Car Resale return series (v3 and the risk-progress records add public category proxies, not business data), return histories for lending and P2P platforms, regimes older than the 60-month window, and pairwise correlation between individual holdings.

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
        observed = [pair['observations'] for pair in scenario['pairs']
                    if pair['kind'] in ('measured', 'category')]
        print(' ', key, scenario['status'], dict(kinds), 'observations:', (min(observed), max(observed)) if observed else None)
    print('  assessment flags:', {k: v for k, v in record['assessment'].items() if isinstance(v, bool)})
print('risk_unknown keys:', sorted((records.get('allocation_score_v2') or {}).get('risk_unknown', {})))
for name in ('risk_progress_v2', 'risk_progress_v1'):
    progress = records.get(name)
    if progress is None:
        print(name, 'absent')
    else:
        print(name, 'status:', progress['status'], '| warnings:', progress['warnings'])
```

Next data worth collecting, in priority order:

1. A Car Resale monthly series. It is the only way to replace the R = 1 assumption in v3, the CPRT/KMX/OPLN basket assumption in `risk_progress_v2`, the older proxy scenarios and the 0.25 / 0.75 assumption in v2. The methodology doc and `docs/car-deal-ledger.md` require dated inventory, cost and proceeds records; the record types live in `src/portfolio_ledger/contract.py`.
2. Monthly return histories for the crypto lending and P2P platforms, to replace the HYG proxy.

## 7. Commands

```bash
# Enrich a copy of a dated snapshot (new file; --config and --cache-dir default to data/)
just holy-grail --snapshot data/snapshots/combined_data_<date>_<ts>.json \
  --output data/derived_snapshots/<new>.json --offline
# optional: --previous-snapshot PATH for attribution
# optional: --car-category PATH (a frozen block) also derives the v3 record; omitted means no v3
# optional: --car-proxies PATH (a frozen car_proxies_v2 or v3 block) derives risk_progress_v2 offline from it (nothing is collected) and risk_progress_v1; omitted means no proxy block and risk_progress_v2 is written as unavailable when the car business has a weight

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
- Never fall back from an invalid v2 record to v1 or a previous result, or from an invalid or unavailable `risk_progress_v2` record to v3, v2 or `risk_progress_v1`. Only an explicitly `unavailable` v3 record (no `risk_progress_v2` present) passes to v2, with a warning.
- Two optional frozen blocks feed the sibling records: `data/car_category/block_latest.json` (v3, absent means no v3 record) and `data/car_category/proxies_latest.json` (auxiliary price-index series and `risk_progress_v1`). The headline basket is collected by normal collection and needs no manual file; an absent proxies file only makes the comparison incomplete. `just car-category build` and `just car-proxies build` refuse to overwrite an existing output path.
- Rebuild the car-category block and the proxies file every month, after the new month's source data is published (the collected basket refreshes itself on each normal run; re-creating a JSON from an old CSV does not make a series current, check the last month). A block is accepted only while its newest month (every series, for the legacy proxy block) is at most one month behind the snapshot's completed month (`max_index_lag_months` in `car.category.METHOD`, `max_lag_months` in `car.risk_proxies.METHOD`). A stale or invalid v3 block (including a `car_category_v1` block) gives an `unavailable` v3 record and the view shows the v2 numbers with a warning. A stale or invalid legacy proxy block shows the `risk_progress_v1` car scenarios as `unavailable` (`invalid_car_proxies_block`); for `risk_progress_v2` a stale auxiliary series only makes the comparison incomplete, while a stale or missing basket makes the headline unavailable. The Ukrstat CPI is published around the 10th of the next month, like Manheim.
- `just risk-progress` validates the saved v2 by replay, changes no snapshot, fetches nothing and never writes Sheets; `--out` writes a new file only, outside the automatic snapshot directories.
- `what_if.py` and `concentration_v1.py` (in `analytics/holy_grail/`) stay on v2.
- Adding a series to `car.risk_proxies.PROXIES` changes the block method: add a new block version and keep the old one, or every saved record that embeds an older block stops replaying.
- The market-context note needs the snapshot's timezone-aware `saved_at_utc`; without it the note is unavailable while the score still renders. A foreign cell note at the target is a conflict (`SheetConflictError` in the full writer, `ValueError` in the scoped one).
- The Sheets writer edits only its owned region and refuses on conflict or insufficient grid space. After a write error, read back before any retry.
- Frozen-record validation replays from saved histories and the saved configuration, never from today's config. Changing a profile does not change an old record.
- Do not copy score formulas or concentration limits here or into `AGENTS.md`; link the methodology heading. The data-sufficiency constants in section 6 mirror the code: re-check them when `analytics/` changes.
