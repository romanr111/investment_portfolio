# Holy Grail / diversification reference

Load this for any task on the diversification score, asset correlation, concentration limits, the what-if CLI, the car-category tracker (v3), the risk-progress headline (`risk_progress_v3` with private streams; `risk_progress_v2` before it) and its car proxy block, or the saved `DIVERSIFICATION_DATA` record.

This is a map, not the methodology. Formulas, thresholds and policy live in `docs/diversification-methodology.md`, which wins on any conflict; the goal the headline serves is in `docs/diversification-goal.md`. Link to its headings by name, not by line number. The repo is public: never put holdings, weights, amounts, scores or account ids from `data/` into tracked files.

## 1. What exists

| Layer | Status | Answers |
|---|---|---|
| `capital_diversification_v2` (`DIVERSIFICATION_DATA.allocation_score_v2`) | Current base method, calculated for new snapshots and sealed. | How invested capital is spread across uncorrelated economic groups, plus equity-sector breadth. |
| `capital_diversification_v3` (`DIVERSIFICATION_DATA.allocation_score_v3`) | Optional sibling of v2; present only with a frozen car-category block. | The v2 score with Car Resale pairs from a public used-vehicle price index instead of the fixed 0.25. A category proxy, not a measurement. |
| `risk_progress_v3` (`DIVERSIFICATION_DATA.risk_progress_v3`) | Current headline for new snapshots, from the same saved v2 and frozen car proxy block plus the public `analytics/models/private_streams_v1.json`. | The v2 DR formula for a long-only individual investor with 100 = 7 equal-risk independent streams, over invested capital plus declared private streams: modeled (class, country, location) streams from public parameters, plus listed proxy baskets for infrastructure, private equity, private credit and timberland. Central parameters give the headline; favorable/adverse vary dependence only. Details: scenario range, private gain, risk by source, locations, replayed v2 market details. Section "Risk progress v3" of the methodology. |
| `risk_progress_v2` (`DIVERSIFICATION_DATA.risk_progress_v2`) | Headline of snapshots saved before `risk_progress_v3` (a detail row after it), from the saved v2 and a frozen car proxy block (`car_proxies_v3` normal collection, `car_proxies_v2` offline). | One 0-100 score over all invested weights: the diversification ratio DR of the group representatives (car business through the labelled CPRT/KMX/OPLN basket) on a shrunk sample covariance. Points normalize the volatility-reduction benefit so 100 is the effect of 15 equal-risk independent streams; DR-squared is only the explanatory equivalent-stream count, not a linear scale. Estimator, anchors and limits: `docs/diversification-methodology.md`, section "Risk progress v2". Details: risk by group, worst months, a write-off scenario, environment map, volatility sensitivity, proxy comparison. A modelled effect of diversification, not a grade, forecast or measurement of the business. |
| `risk_progress_v1` (`DIVERSIFICATION_DATA.risk_progress_v1`) | Older optional sibling of v2, kept for its records and details, written only with a frozen `car_proxies_v1` or `car_proxies_v2` block. Not part of the capital score or the headline. | How many independent equal-risk streams (DR-squared, target 15) the covered portfolio behaves like, as points out of 100. Progress, not a grade. Revives the retired risk-equivalent formula on frozen v2 group histories. |
| `concentration_v1` (`DIVERSIFICATION_DATA.concentration_v1`; the `version` field inside is `concentration_v2`) | Current. Rendered beside the score. | Issuer, thesis, country and core-bucket limits, which v2 cannot see. |
| v1 capital score, risk-equivalent count and DR-squared, ten-check policy, simple indicator | Frozen. Rendered only from records that already contain them. | Historical comparisons. Never trend them against v2. |
| `analytics/dalio/dalio_holy_grail.py` | Separate standalone analyzer (`main.py --run-dalio-analysis`, `python3 -m analytics.dalio.dalio_holy_grail --help`). Not part of the saved score. | Independent risk sources (README "Dalio Holy Grail Analyzer"). |

"How correlated are my assets with each other" is answered by the `pairs` inside the v2 scenarios (the v3 scenarios copy every non-car pair from v2). Those are correlations between economic groups, not between individual holdings.

## 2. Data flow

Module names are relative to `analytics/holy_grail/` (see section 3). Production code outside the package imports only `analytics.holy_grail.api`.

1. `DataSource.get_combined_data` (`src/data_source.py`) builds the combined data and calls `enrich.enrich_combined_data`.
2. `exposures.extract_exposures` turns positions into exposures; `allocation_inputs.allocation_history_requests` lists the group representatives needed.
3. `market_history.collect_return_history` fetches daily prices (yfinance), cached under `data/holy_grail_history`; `market_history.monthly_usd_returns` converts them to monthly USD returns.
4. `allocation_v2_inputs.calculate_allocation_score_v2` maps positions to groups with `allocation_inputs.profile_for`, then calls `allocation_score_v2.evaluate_scenarios` and `score_components_v2`.
5. When a frozen car-category block is passed, `allocation_score_v3.derive_allocation_score_v3(v2, block)` builds the sibling record from the saved v2. The argument is `car_category=` on `enrich_combined_data`/`enrich_snapshot_file` and `--car-category` on the CLI; `DataSource` passes `car.category.load_block()` from `data/car_category/block_latest.json` (None when absent). Omitted means no v3.
6. `risk_progress.derive_risk_progress_v2(v2, proxies)` derives `risk_progress_v2` (the market-part record) from the saved v2 and a frozen proxy block (`derive_risk_progress_v1` still derives the older sibling from a v1/v2 block). Normal collection (`DataSource`, `collect_car_basket=True` on `enrich_combined_data`) fetches the CPRT/KMX/OPLN basket through the existing price seam and cache when the car business has a positive weight, freezes it as `car_proxies_v3` and imports the auxiliary price-index series from `car.risk_proxies.load_block()` (`data/car_category/proxies_latest.json`, optional). An explicit `car_proxies=` block (and `--car-proxies`) is used verbatim, with no collection: the offline/historical path. The record is written even when inputs fail, as `unavailable` with a reason; it is never silently absent. `risk_progress_v3.derive_risk_progress_v3(v2, proxies)` derives the headline `risk_progress_v3` beside it; its `private_streams` declarations live in the config (frozen in `v2.configuration.extraction_settings`), and `risk_progress_v3.history_needs(settings)` adds the factor groups, `EURUSD=X` and proxy tickers to `allocation_history_requests` only when private streams are declared, so v2 stores and seals them with its histories.
7. `concentration_v1.build_block` and `match_decisions` build the concentration block from the same frozen inputs (it stays on v2).
8. All results are saved under `DIVERSIFICATION_DATA` in the combined-data snapshot (`data/snapshots/combined_data_*.json`).
9. `views.diversification.saved_diversification_view` selects the public view. A saved v2 record always goes through `views.allocation.allocation_view_v2(data, expected_date, saved_at_utc)` (older records use their own views), which replay-validates v2 and every present sibling against their own frozen inputs. The view never fetches data or reads today's config.
   - `risk_progress_v3` present (`views/risk_progress_v3.py`): it decides the headline first, with the same rules and the same summary labels and order as the `risk_progress_v2` view (the Sheets writer owns rows by label). Private streams appear as class, country and a numbered location; never location names or USD amounts.
   - Otherwise `risk_progress_v2` present (`views/risk_progress_v2.py`): it decides the headline before any other gate. Valid, the summary shows the score as a bare number, the two largest modelled risk contributions and the car-business proxy assumption; the scale anchor and the rest live in the drivers, conclusion note and detail rows; failing replay, the headline is "Недоступно" and the view never falls back to capital v2, capital v3 or `risk_progress_v1`. A corrupt v3 or `risk_progress_v1` sibling is marked unavailable in its own detail row and does not block a valid headline.
   - No `risk_progress_v2` key (older snapshots): the capital view uses `allocation_score_v3` when it replays; an explicitly `unavailable` capital v3 falls back to capital v2 with a warning and a suffix in the conclusion cell, while a v3 that fails replay renders unavailable. A valid `risk_progress_v1` adds the summary row "Ризиковий прогрес" and a paragraph in the conclusion note; failing replay, the row shows "Недоступно".
   - The note under the conclusion comes from `car.resale_market.conclusion_note` (frozen `CAR_RESALE_MARKET_CONTEXT`).
10. The view feeds Google Sheets (`src/google_sheets/insights_tables.py`; scoped writer `analytics/holy_grail/delivery/sheet.py`) and the quarterly HTML (`portfolio_yic_reports/generate_quarterly_report.py`). Both deliver the conclusion as an owned cell note (`car.resale_market.NOTE_MARKER`, tested by `is_owned_note`); a foreign note is a conflict.

Historical snapshots take a different entry: `enrich.enrich_snapshot_file` (via `just holy-grail`) enriches a copy and writes a new derived file.

## 3. Module map (`analytics/holy_grail/`)

Production code outside the package imports only `api.py`; tests import internals. Everything else is internal and may move.

| Module | Role |
|---|---|
| `api.py` | Outside import surface: `enrich_combined_data`, `saved_diversification_view`, `saved_progress_view`, `load_car_category_block`, `load_car_proxies_block`, `is_owned_note`. |
| `paths.py` | `REPO_ROOT`, `DATA_DIR`, `CONFIG_PATH`, `CACHE_DIR`, the two car block paths, `PROFILE_PATH` and `PRIVATE_MODEL_PATH`. Modules take locations here, not from `__file__`. |
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
| `allocation_score_v3.py` | `derive_allocation_score_v3` (sibling record from saved v2 plus a frozen block), `validate_saved_allocation_v3` (full replay), `HEADLINE`, `METHOD_V3`. |
| `concentration_v1.py` | Issuer, thesis, core and country facts, limits, decision matching, saved-block validation. |
| `what_if.py` | Offline before/after on a copied snapshot (`run`). |
| `risk_progress.py` | `derive_risk_progress_v2` / `validate_saved_risk_progress_v2` (the market-part record and full replay) and the unchanged `derive_risk_progress_v1` / `validate_saved_risk_progress_v1`, plus the offline CLI (`just risk-progress`, v1). Imported by `enrich` and the views. |
| `views/diversification.py` | `saved_diversification_view`: dispatch to a saved record's public view. |
| `views/allocation.py` | Public whitelist views (`allocation_view_v2` for v2, v3, the older risk-progress row and headline dispatch; `allocation_view` for v1) and the concentration section. |
| `risk_progress_v3.py` | `derive_risk_progress_v3` / `validate_saved_risk_progress_v3` (individual-investor headline and full replay against the tracked model), `load_model`, `history_needs`, `METHOD_V3`. Reuses the v2 window, shrinkage, car basket and DR helpers. |
| `views/risk_progress_v3.py` | `risk_progress_v3_view`: headline view for v3 records (generic private labels, scenario range, private gain, risk by source, replayed v2 market details); formats saved values only. |
| `views/risk_progress_v2.py` | `risk_progress_v2_view`: the `risk_progress_v2` view (headline for snapshots saved before v3; score, three headline lines, details, qualitative environment map). Formats saved values only. |
| `views/common.py` | `empty_view`: the unavailable view every renderer falls back to. |
| `delivery/sheet.py` | Scoped, readback-verified Sheets writer for the saved view (`just holy-grail-sheet`). |
| `car/category.py` | `build_block`, `validate_block`, `load_block`, `METHOD`, `group_measures` (three correlation measures per group). A leaf: imports no score module. |
| `car/tracker_cli.py` | Tracker CLI `build` / `report` (`just car-category`); the only car module that imports both the v2 and v3 score modules. |
| `car/category_data.py` | Offline parsers and sha256 manifest for public used-vehicle datasets (including Ukrstat vehicle CPI and NBU USD rates). `fetch_raw`, `fetch_ukraine` and `long_group_returns` are the only network entry points, called explicitly. |
| `car/crisis_test.py` | H1-H3 crisis test of the index against the groups (`just car-crisis`); write-up in `docs/car-flip-category-evidence.md`. |
| `car/industry_proxy.py` | One retrospective check of the car business against a listed industry basket (`just car-proxy`). Equity beta, not a measurement of the business. |
| `car/resale_market.py` | `build_context`, `validated_context`, `conclusion_note`, `NOTE_MARKER`, `is_owned_note`: frozen public market context shown beside the score, not part of it. |
| `car/risk_proxies.py` | `build_block`, `validate_block`, `load_block`, `METHOD`, `METHODS`: the frozen car proxy block of public used-vehicle series (`just car-proxies build` / `report` / `fetch-ukraine`). `car_proxies_v2` is the offline block; embedded `car_proxies_v1` blocks still validate. `inspect_block`, `build_block_v3` and `car/proxy_collection.py` build and check the `car_proxies_v3` block of normal collection (block integrity and series freshness are judged separately). |
| `legacy/allocation_v1.py` | Frozen `capital_diversification_v1`: score, calibration, `validate_saved_allocation`. |
| `legacy/quality.py` | Frozen ten-check summary: `COUNT_VERSION`, `POLICY_VERSION`, `CHECK_IDS`, `summarize_checks`. |
| `legacy/progress_view.py` | `saved_progress_view` and `CONSTRAINT_LABELS` for the retired `holy_grail_progress_v1` record. |
| `legacy/indicator.py`, `legacy/indicator_view.py` | Validation and public view of the frozen simple indicator. |

Rules, checked by reading imports (a scan of the package finds no cycle, even through function-level imports):

- Nothing outside `views/`, `api.py` and `legacy/` imports `legacy/`.
- Leaf modules (`fingerprint`, `paths`, `correlation`, `exposures`, `market_history`, `evidence`, `views/common`, `car/category`) import none of their consumers. Do not add a function-level import to dodge a cycle: move the shared piece into a leaf.
- A name used by another module is public: no leading underscore. The one exception is the v3 headline view reusing the private formatting helpers of the v2 view; keep that set explicit.

Outside the package: `analytics/dalio/dalio_holy_grail.py` (standalone Dalio analyzer, section 1), `analytics/risk_analyzer.py` (standalone heuristic 1-10 per-asset risk scorer, `PortfolioRiskAnalyzer`; not imported by the pipeline) and `analytics/models/economic_profiles_v1.json` (profiles, section 4).

The group list and each group's representative ticker live in `analytics/holy_grail/allocation_inputs.py` (`GROUPS`). Read them there instead of copying them into prose.

## 4. Inputs and local artifacts

- Public profiles: `analytics/models/economic_profiles_v1.json` (dated economic profiles, sector shares, optional fund `holdings`). Its `core: true` flag is also used by the quarterly report's core/satellite split.
- Private config: `data/holy_grail_config.json`. Top-level keys: `schema_version`, `mappings`, `qualifications`, `indicator`, `allocation` (`profiles`, `method_version`, optional `concentration_limits`, `linked_theses`, `concentration_decisions`), optional `private_streams` (`entries`, `reclassify`; see the method v3 record below) and optional `diversification`. Current code reads only `diversification.exposures` (v2 risk facts); `policy` and `cash_components` belong to retired ten-check calculators. See "Private evidence and collection" in the methodology doc.
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

- Result: `status` (`modeled`, `provisional`, `unavailable`, `not_applicable`), `reason`, `progress_points` (full precision), `progress_display` (`headline` integer, `detail` one decimal rounded down), `warnings`, `retrospective`, `data_vintage`. Numeric headline fields are null unless the status is modeled or provisional. `windows`: `m60` (headline) and `m36` (diagnostic), each with `effective_streams`, `diversification_ratio`, `capital_weights`, `risk_share` (Euler share, may be negative, sums to 1), `annual_volatility_pct` by group and `annual_portfolio_volatility_pct`.
- `coverage` (all positive invested groups, the car proxy, cash outside), `sensitivity` (`proxy_comparison` over four representatives and `volatility` multipliers, kept apart), `stress` (worst modelled months and the car-business write-off scenario), `car_proxies` and `car_proxies_fingerprint` (the embedded frozen block), `source_v2`, `method`, `method_fingerprint`, `result_fingerprint`.

`DIVERSIFICATION_DATA.risk_progress_v3` (structure only):

- Result fields as in `risk_progress_v2` (`status`, `reason`, `progress_points`, `progress_display`, `warnings`, `retrospective`, `data_vintage`), `method` (with the model path, version and parameters fingerprint), `model` (the parameters used), `source_v2`, `car_proxies` and its fingerprint. Failure reasons may carry the cause after a colon (`private_model_invalid:<Error>`, `invalid_inputs:<Exception>`).
- `private`: `declared`, `entries`, `reclassified`, `excluded` counts. `coverage`: v2 invested and cash shares, `cash_source_pct_nav` (the part of the cash share that entered the score through cash-sourced deposits), `universe_over_invested`, private, modeled and proxy shares of the universe, `reclassified_pct_invested`, `streams` (`id`, `kind` (`listed`, `car_business`, `proxy` or `private:<country>`), `cls`, `country`, `location`, `weight_pct_universe`; class, country and location are null for measured and proxy streams) and `car_proxy`. `locations`: distinct locations per country. `windows` (`m60` headline, `m36` diagnostic; stream ids are v2 groups, `proxy:<class>` and `private:<class>:<country>:<location>`), `scenarios` (`favorable`, `central`, `adverse`, volatility x0.5/x2, `range`), `private_gain` (base, with modeled, full; sequential points), `sources` (capital and risk by source, loadings of modeled streams).
- Private declaration keys (`data/holy_grail_config.json -> private_streams`): `entries[]` with `id`, `class`, `country`, `value_usd`, `valuation_as_of` and optional `location`, `currency`, `debt_usd`, `nav_source` (`outside` or `cash`), `held_from`, `valuation_source`, `reviewed_at`, `primary_residence`; `reclassify` `{position_id: {class, country, location?, source_identity?}}`. Evidence kinds: modeled streams are `modeled` (public parameters), proxy streams are `proxy` (the listed basket, not the asset), measured streams are `measured` (v2 group representatives).

`DIVERSIFICATION_DATA.risk_progress_v1` (structure only):

- Result: `status` (`modeled`, `provisional`, `unavailable`), `progress_points`, `progress_display`, `warnings` (for example `partial_scope_excluded_weight`). `windows`: `m60` (headline) and `m36` (comparison), each with `status` and `effective_streams`. `coverage`: `covered` and `excluded` groups (excluded rows carry a `reason`), `covered_pct_invested`, `excluded_pct_invested`, cash share. `method` (including `target_streams`), `source_v2` (identifiers of the v2 it was derived from), `method_fingerprint`, `result_fingerprint`.
- `car_scenarios` (only when a block was supplied): `status`, `reason` (`invalid_car_proxies_block` when the block fails), `range` (`low_display`, `high_display`), `car_weight_pct_invested`, and `items` by proxy (`manheim_wholesale`, `bls_used_retail`, `auto1_wholesale_eu`, `listed_remarketers`, and `ukraine_vehicle_cpi` with a v2 block), each with `effective_streams`, `baseline_streams` (the covered-only count on the scenario's own months), `delta_streams` (their difference), `progress_display`, `correlation_covered`, `relation`, `effect`.

## 6. Evidence status and data sufficiency

What the score rests on, by `kind` of pair:

- `measured`: group-representative ETF monthly USD returns, a 60-month window ending at the last completed month (36-month alternative), at least 36 real overlapping months per pair, no zero-filling.
- `modeled`: in v2 (and in the v3 `r075` stress scenario) pairs involving the Car Resale business use an assumed correlation (0.25 main, 0.75 sensitivity). There is no observed business return series.
- `category`: v3 only. A Car Resale pair taken as R x rho(group, public used-vehicle price index) with R fixed at 1. Per group the largest of three measures (same-window monthly, a one-month price lag, equity-stress months since 1997); their samples differ, so each pair stores its `sample` and `observations`. A price-channel assumption, not a measurement or bound.
- `missing`: fewer than 36 overlapping months, zero variance, or a history that failed to load (the run then sets the `history_collection_incomplete` flag). Treated as correlation 1; `coverage.missing_pair_max_points` bounds the effect. A missing-pair effect above 5 points makes that scenario unavailable (`insufficient_pair_coverage`). Unknown invested weight above 5% makes the whole result unavailable (`insufficient_coverage`).

Where assumptions enter besides the business pairs:

- Crypto lending and P2P default to the `credit_hy_usd` group (HYG representative) through the category model in `profile_for`, unless a dated profile overrides it. Their pairs show as `measured` because HYG's history is real, so `kind` does not flag the proxy; proxy-mapped positions carry `kind: proxy`.
- A confirmed short individual Treasury uses a dated private mapping to the SHV group.
- Single stocks collapse into their group representative; correlation between two holdings in the same group is not measured.
- Sector breadth comes from reviewed profiles, not live data. Unknown equity-sector weight goes to the largest known sector.

All three risk-progress records rest on saved v2 group histories. `risk_progress_v2` includes every positive invested weight: `car_business` enters through the equal-weight monthly total return of CPRT, KMX and OPLN (all three required, no forward fill), labelled a proxy and an owner assumption, never a measurement; Manheim, BLS and AUTO1 (with the basket) are comparison context, never the v2 headline, and the Ukrstat CPI stays context only. At least 36 common months (36-59 provisional) and a last month at most one behind are required; a positive weight without a usable series makes the record unavailable rather than dropping the group. `retrospective=True` is asserted at derivation; replay enforces the block-date rule but cannot verify the assertion. `risk_progress_v1` covers only groups with a return history: `car_business` has none, is excluded and reported (`partial_scope_excluded_weight`), and enters only as labelled scenarios from the frozen block: Manheim (US wholesale), BLS used-car CPI (US retail), AUTO1 (EU wholesale, scraped, medium confidence), the equal-weight CPRT/KMX/OPLN basket (equity-like) and, with a `car_proxies_v2` block, the Ukrstat national CPI "purchase of vehicles" in USD at the NBU monthly mean (new and used mixed, medium confidence). These are category proxies, never the business return, shown as a deliberately wide range; only the owner's monthly numbers could say which is closer. `risk_progress_v3` adds declared private streams to the same base: modeled class/country rows from the public `private_streams_v1.json` (`kind: modeled`) and listed proxy baskets for infrastructure, private equity, private credit and timberland (`kind: proxy`, a market series standing in for the asset, not the asset itself). Its favorable/adverse scenarios move dependence only; replay validates the tracked model and the embedded block. The points scale is a policy choice, not a percentage of risk.

Not collected: a Car Resale return series, lending/P2P histories, pre-60-month regimes, holding-level correlations.

Reading the result:

- `assessment.business_dependent` is true when the category differs between the Car Resale scenarios of the same window (v2: 0.25 vs 0.75; v3: `cat_point`, `cat_upper90`, `r075`). Read the min/max range, not only the headline.
- In v3 the headline is `m60_cat_point` (`HEADLINE`, a judgment call). `cat_upper90` uses nominal per-estimate Fisher endpoints: a sensitivity, not a confidence interval for the score.
- Sampling noise: near zero correlation the standard error is about 0.13 at n=60 and about 0.17 at n=36, so small differences between pairs are noise.

Check data sufficiency on any snapshot (prints counts, flags and aggregate unknown shares; no holdings or scores):

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
for name in ('risk_progress_v3', 'risk_progress_v2', 'risk_progress_v1'):
    progress = records.get(name)
    if progress is None:
        print(name, 'absent')
    else:
        print(name, 'status:', progress['status'], '| warnings:', progress['warnings'])
```

Next data worth collecting: a Car Resale monthly series (the only way to replace the R = 1 assumption in v3, the CPRT/KMX/OPLN basket assumption in `risk_progress_v2`, the older proxy scenarios and the 0.25 / 0.75 assumption in v2; `docs/car-deal-ledger.md` and the methodology require dated inventory, cost and proceeds records, types in `src/portfolio_ledger/contract.py`), then monthly return histories for crypto lending and P2P to replace the HYG proxy.

## 7. Commands

Flags and commands: `.agents/references/commands.md` is authoritative for `just holy-grail`, `just risk-progress`, `just holy-grail-sheet`, the car-category tracker and the proxy block. Constraints that matter here: a derived output is always a new file, `just holy-grail` never fetches positions or writes Sheets, and `--offline` uses cached history only.

Car-category tracker (`just car-category build|report`, `just car-crisis`, `just car-proxy`) and the proxy block (`just car-proxies build|report`): flags are in `.agents/references/commands.md`, section "Car-category tracker (method v3)" and the `just risk-progress` and `just car-proxies` bullets.

Report rendering from a derived snapshot: `generate_quarterly_report.py --after PATH` (see the `quarterly-report` skill section "Holy Grail saved-data enrichment"). Walkthrough and constraints: methodology doc sections "Offline what-if scenarios" and "Simple Holy Grail indicator (v1)" (replay and scoped delivery).

## 8. Gotchas

- A missing `data/holy_grail_config.json`, or one without `allocation`, silently produces no v2 block. A malformed config produces `unavailable` (`invalid_allocation_config`; a wrong `method_version` gives `invalid_method_version`). The `portfolio-sync` preflight exists for this; run it before any live write.
- The derived output path must be new, outside the source directory and outside `data/snapshots/`, and never `combined_data_latest.json` or `final_data.json`.
- `--offline` uses cached public history only. A series missing from the cache sets `history_collection_incomplete` and its pairs become `missing`, which leaves scenarios provisional or unavailable.
- Never fall back from an invalid v2 record to v1 or a previous result, or from an invalid or unavailable `risk_progress_v2` record to `risk_progress_v3`, capital v2 or `risk_progress_v1`. Only an explicitly `unavailable` capital v3 record (`allocation_score_v3`, in snapshots without `risk_progress_v2`) passes to capital v2, with a warning.
- Two optional frozen blocks feed the sibling records: `data/car_category/block_latest.json` (`allocation_score_v3`; absent means no record) and `data/car_category/proxies_latest.json` (auxiliary price-index series and `risk_progress_v1`). The headline basket needs no manual file; an absent proxies file only makes the comparison incomplete. `just car-category build` and `just car-proxies build` refuse to overwrite an existing output path.
- Rebuild the car-category block and the proxies file every month, after the new month's source data is published (the collected basket refreshes on each normal run; re-creating a JSON from an old CSV does not make a series current, so check the last month). A block is accepted only while its newest month (every series, for the legacy proxy block) is at most one month behind the snapshot's completed month (`max_index_lag_months` in `car.category.METHOD`, `max_lag_months` in `car.risk_proxies.METHOD`). A stale or invalid car-category block (including `car_category_v1`) gives an `unavailable` `allocation_score_v3` record and the view shows capital v2 with a warning. A stale or invalid legacy proxy block shows the `risk_progress_v1` car scenarios as `unavailable` (`invalid_car_proxies_block`); for `risk_progress_v2` a stale auxiliary series only makes the comparison incomplete, while a stale or missing basket makes that record unavailable. The Ukrstat CPI is published around the 10th of the next month, like Manheim.
- `just risk-progress` validates the saved v2 by replay, changes no snapshot, fetches nothing and never writes Sheets; `--out` writes a new file only, outside the automatic snapshot directories. `what_if.py` and `concentration_v1.py` stay on v2.
- Adding a series to `car.risk_proxies.PROXIES` changes the block method: add a new block version and keep the old one, or every saved record that embeds an older block stops replaying.
- The market-context note needs the snapshot's timezone-aware `saved_at_utc`; without it the note is unavailable while the score renders. A foreign cell note is a conflict (`SheetConflictError` full writer, `ValueError` scoped). The Sheets writer edits only its owned region and refuses on conflict or insufficient grid space; after a write error, read back before any retry.
- Frozen-record validation replays from saved histories and the saved configuration, never from today's config. Changing a profile does not change an old record.
- Do not copy score formulas or concentration limits here or into `AGENTS.md`; link the methodology heading. The data-sufficiency constants in section 6 mirror the code: re-check them when `analytics/` changes.
