# Portfolio diversification indicators

> Reader's guide: "Capital diversification v2" is the base method, with
> "Concentration safeguards" and "Offline what-if scenarios" beside it and
> "Capital diversification v3 (car-category pairs)" as its sibling. The headline
> is "Risk progress v3 (`risk_progress_v3`)" with "Risk progress v2
> (`risk_progress_v2`)" in the details. Public car context:
> `docs/car-resale-market-context.md`, `docs/car-flip-category-evidence.md`.
> Historical sections describe frozen records; "Private evidence and collection"
> defines the exposures format still read by v2.

## Historical capital-weighted score (v1)

The following v1 description applies only to existing historical records; new
enrichment calculates v2, below. `DIVERSIFICATION_DATA.allocation_score`, version
`capital_diversification_v1`, answers how invested capital is spread across
economic groups and equity sectors; more means greater diversity in this model.
Cash is outside the score and shown as a share of full NAV.

With invested weights p, positive-clipped pair correlations r, conditional GICS
sector shares s and breadth b=(1-sum(s^2))/(1-1/11):
`D=2*sum(p_g*p_h*(1-r_gh)); B=sum(p_g^2*b_g); score=clip(A*D+25*B,0,100)`.
Unknown sector mass goes to the largest known sector; unknown pairs use r=1;
ticker/account splits and shared HYG lending proxies cannot create groups.
Treasury groups are 0-1y (SHV), >1-10y (IEF), >10y (TLT).

The historical v1 calibration uses October 2021 through September 2026 and six
equal blocks: US equities; other equities (EFA/MCHI); Treasuries (SHV/TLT); gold;
commodities; Car Resale. The coefficient is frozen for later quarters and
sensitivity. Car Resale uses assumed correlations .25/.75 to public groups, not
observed business returns or crisis forecasts; US used-car CPI is not used.
Single-company sectors in `economic_profiles_v1.json` are reviewed GICS-vocabulary
classifications, not a licensed feed; each dated profile, including KWEB's
complete one (`as_of_date: 2026-09-30`), supplies its own breadth.

Each pair uses its own real overlapping months in the fixed last-60 calendar
grid, minimum 36; store count and last month per pair and never fill missing
returns. 36-59 observations, lagged histories, cached balances or unknown
sectors make the result provisional, with no hidden quality multiplier. Unknown
capital above 5%, or missing-pair influence `2*A*sum(p_g*p_h)` above 5 score
points, makes the main score unavailable; no invested assets is not applicable.

The score follows the explicit Cash exclusion: typed Cash ledger rows `debt`
(MY_DEBT personal liability) and `manual_reconciliation` stay outside with a
visible warning; they are not automatic brokerage financing. Negative broker
cash, negative position values or quantities and declared leveraged/nonlinear
positions still block the score; legacy diagnostics keep stricter borrowing
treatment. Reconciliation uses max($1, NAV*1e-6); invested weights normalize to the reconciled
sum with no phantom asset for tolerated rounding, and NAV stays intact.

Private `holy_grail_config.json` enables the feature with an `allocation` object;
historical records embed their calibration and profiles, and `allocation.profiles`
held dated private confirmations (individual Treasury, identity-bound Car Resale).
Unknown instruments need explicit profiles; region is never inferred from currency,
venue or broker bucket. New enrichment calculates v2 and preserves historical
analytics; HTML/Sheets render the saved result without fetching, and replay
recomputes from saved histories, not current config.

Display floors the score, snapping floating noise within 1e-8 of an integer.
100 is a practical threshold, not a maximum. The historical v1 Sheets writer
puts display_score/100 in B10 with 0% format. Scoped updates preserve outside
cells/formats/groups, back up before mutation, read back after timeout and never
blindly repeat a write.

The count, policy and indicator sections below describe historical records only;
their calculators are retired, the previous headline was
`DIVERSIFICATION_DATA.indicator`, and this is a long-term USD resilience policy -
not Dalio's method, a forecast of independence or an attractiveness score.

## Count and interpretation

`risk_equivalent_streams_v1`: `DR = sum(w_i * sigma_i) / sqrt(wᵀΣw)`;
`N_equivalent = DR²`; volatility reduction = `100 * (1 - 1/DR)`. Weights are
exposure value / reconciled total; covariance and volatilities use identical
observations, adjusted monthly USD returns and 60 completed months. The latest
36-month comparison uses the same exposures and valuation-date weights. Missing
observations are not zero returns; 36–59 common observations are provisional,
below 36 withholds the count.

Identical instruments, histories and shared proxies are combined (ETF constituents
are not extra streams). Negative correlations retain hedging benefits; output shows
the modeled exposure count and hedge-driven flags, and thresholds are compared
before display rounding, so 14.9996 displays `<15`.

Legacy policy only: Cash adds no streams. Documented USD cash without unsecured
dependencies and identified USD Treasuries with <=365 days remaining are
analytical reserves; stablecoins keep issuer/platform risk even when called cash,
and classifications never change. All-confirmed reserves give zero streams and
no score; zero variance withholds the count, and unsupported shorts, borrowing,
leverage or nonlinear exposure make the assessment unavailable. DR² interpretation:
[TOBAM dashboard, July 2015](https://www.tobam.fr/wp-content/uploads/2015/08/TOBAM-Diversification-Dashboard-July-2015.pdf).
Legacy `holy_grail_progress_v1` (inverse squared-correlation concentration,
Euler-weighted) stays separate and never mixes into new trends.

## Ten-check policy

Editable private defaults (`diversification_policy_v1`), not Dalio's thresholds or personal loss limits.

| Check | Pass threshold |
|---|---|
| Risk-family concentration | Largest absolute variance contribution <=40% |
| Corporate issuer, including fund overlaps | Largest issuer <=10% of NAV |
| Statistical breadth | DR² >=15 and >=15 distinct modeled exposures |
| Stability | Latest36 / primary60 count >=75% |
| Recession stress | Loss <=20% |
| Inflation/rates stress | Loss <=20% |
| Liquidity/crypto stress | Worse of the two losses <=20% |
| Counterparty/depeg | Largest dependency-group failure loss <=5% |
| Local business/FX | Loss <=10% |
| Illiquidity | Value requiring >30 days to realize <=20% |

Every check saves value, threshold, pass/fail/unknown and reason; the bound is
`10 * passed` to `10 * (passed + unknown)`, and all ten must resolve for a point
score. All unknown gives "Недостатньо даних" (0–100); no band is labelled good,
and family, issuer, breadth and counterparty failures stay visible.

Statistical checks (family, breadth, stability) need 60 common observations and
>=99% of non-reserve value with suitable histories and no material weak-proxy or
stale valuation limitation (material >=1% by default); otherwise subset statistics
stay provisional and the checks unknown. Known value lowers the bound, unclassified
value raises it; material stale valuations block value-based checks, and invalid or
unreconciled totals invalidate the result.

Confidence describes input evidence, not prediction: high with no material flags,
medium if >=8 checks resolve without proxy or valuation flags, else low. Reserve
share is separate; cash improves stress losses, not concentration.

## Hypothetical stress policy

One-step valuation shocks, without income accrual or probability claims:

| Class | Recession | Inflation/rates | Market liquidity | Crypto crash |
|---|---:|---:|---:|---:|
| Equities, including China | -30% | -20% | -45% | -10% |
| Gold | +5% | +10% | -10% | 0% |
| Silver | -20% | +10% | -30% | 0% |
| Broad commodities | -25% | +20% | -35% | 0% |
| Crypto coins | -50% | -30% | -70% | -70% |
| Stablecoin lending | -20% | -10% | -35% | -20% |
| P2P lending | -20% | -10% | -35% | 0% |
| Car inventory | -25% | -15% | -35% | 0% |
| Stablecoin cash balances | 0% | 0% | -20% | -20% |
| True USD cash | 0% | 0% | 0% | 0% |

| Scenario | Nominal yield | Real yield | Credit spread |
|---|---:|---:|---:|
| Recession | -200bp | -100bp | +600bp |
| Inflation/rates | +300bp | +150bp | +200bp |
| Market liquidity | +100bp | +100bp | +800bp |
| Crypto crash | 0bp | 0bp | +100bp |

Nominal government: `-rate_duration * nominal_yield_change`; inflation-linked:
`-rate_duration * real_yield_change`; corporate credit adds
`-spread_duration * spread_change` (effective-date duration in years, decimal
changes). Missing duration is unknown, never inferred from "Bonds". Losses floor
at 100%; duration omits convexity.

Counterparty/depeg tests lose 100% of each unsecured dependency group, reduced only
by documented protection/recovery; overlapping dependencies are tested per group
and never summed against the same principal, and the largest loss is reported.
Local stress loses 30% of car inventory and 20% of explicit non-USD monetary
exposure, each position once at the larger loss. Listing currency is not economic
FX exposure; unknown bounded exposure uses 0–100% loss, and negative scenario
losses require documented gains.

## Private evidence and collection

Extend ignored `data/holy_grail_config.json`, keeping `mappings` and
`qualifications`. Optional `diversification` holds `exposures`, `policy` and
`cash_components`. Exposure keys are canonical IDs (`ib:IHYG`) or
`category:<name>` for shared facts; index-keyed entries (`crypto_lending:0`,
`p2p:0`, `other_assets:0`) also need a matching `source_identity`
(`account`/`asset`/`asset_id` per kind) for mappings, qualifications and risk
evidence. After source rows move, mismatched entries are ignored, leaving default
weak proxies and unknown facts; no stable identity, no position-specific evidence.

Each record needs non-empty `source`, `effective_from` (optional `effective_to`)
and `reviewed_at`; future reviews are rejected, retrospective factual reviews are
allowed and labelled, but a review field alone cannot establish proxy suitability.
Fields: `stress_class`, `currency`, `maturity`, `rate_duration`,
`spread_duration`, `issuer_weights` (corporate issuer -> fraction, with fund
overlaps), `corporate_issuer_applicable: false` only with sourced exemption,
`counterparty_complete`, `counterparty_groups` (dependency -> unsecured loss
fraction), `liquidation_days`, `fx_monetary`. Stress classes: `equity`, `gold`,
`silver`, `commodities`, `crypto`, `stablecoin_lending`, `p2p`, `car_inventory`,
`stablecoin_cash`, `usd_cash`, `treasury_reserve`, `nominal_government`,
`inflation_linked`, `corporate_credit`; `leveraged`/`nonlinear_risk` reject.

Cash children partition existing NAV, never add it. `cash_equivalent:<asset>`
uses canonical Cash_Equivalents; optional `cash_components` name a canonical
Breakdown key with `excludes_cash_equivalents: true` and disjoint components only.
The remainder is `cash:unclassified`, not safe USD; over-allocation fails quality
but preserves reporting. Negative source cash balances make both analytics
estimates unavailable even with positive net cash. Reconciliation allows the
source total's $1 precision; percentages use the unrounded component sum with
saved totals intact.

Do not infer returns from carrying values. Car resale requires dated
inventory/cost/proceeds/turnover records (`docs/car-deal-ledger.md`); HYG and
used-car CPI are weak proxies until substantive fit, defaults, redemption, depeg
and Ukraine operating risks stay omitted, and residual returns are never
manufactured. Listing currency, quote units and FX use the shared collector;
dividends are not added again to adjusted histories.

Historical `DIVERSIFICATION_DATA` records hold count/policy versions, score
bounds, ten checks, confidence, coverage/reserves, scenarios, dates,
qualifications and fingerprints; reports and Sheets render saved records, while
invalid or mismatched blocks withhold results and a changed-input score is never
reused. Private evidence stays ignored; public views whitelist labels, percentages
and counts, and there are no trades or automatic reallocation. Historical
enrichment uses `just holy-grail --snapshot ... --output ... --offline` and an
explicit HTML `--after`; originals and latest pointers stay unchanged. Exclude
post-period observations and current holdings; revised series are retrospective,
and observation dates do not imply publication availability.

## Simple Holy Grail indicator (v1)

`DIVERSIFICATION_DATA.indicator` was the primary risk-equivalent count, frozen
and rendered by reports and Sheets; new enrichment no longer calculates it. HYG
is a disclosed lending/P2P proxy, US used-car CPI a car-resale valuation proxy
(not business return). The count compares identical monthly observations; the
36-month comparison needs all 36 calendar observations, never zero-filled.

All exposures have one role: direct, model, confirmed short US Treasury reserve,
Cash outside the count, or uncovered. Percentages use canonical NAV (tolerance
max(1 USD, NAV * 1e-6)); stablecoins are not safe reserves. Treasury confirmations
are private, dated and expire at documented maturity or the confirmed <=365-day
bound; status is never inferred from generic Bonds.

Owned US Treasuries participate as assets; an identified ETF uses its own adjusted
USD history. A confirmed individual Treasury with <=1 year remaining uses a
disclosed SHV total-return proxy without full history; `valid_from`/`valid_until`
refresh after the confirmed maturity bound, invalid or expired mappings are not
applied, and there is no generic Bonds override. Maturity exposures stay distinct:
short bills are not replaced with TLT (20+ year Treasury), intermediate notes,
high yield or a generic bond series. Direct ETFs keep their own tickers and
histories; only identical instruments are grouped. Short Treasuries can
contribute little to DR-squared (small volatility, large capital); inclusion never
adds +1.

N equivalents / reference 15–20 is the headline, one decimal, below 15 never
rounding up. Proxy, default, illiquidity, coverage, model and sample notes stay
visible; a count above the number of exposures is hedge-driven, not literal. All-
Cash/reserves is not-applicable, never "achieved". Old blocks stay readable;
malformed new blocks never fall back to old scores.

Adding v2 to a historical snapshot preserves originals/latest pointers and financial fields:

```bash
just holy-grail --snapshot SOURCE --output NEW_DERIVED_PATH --config PRIVATE_CONFIG --offline
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --year 2026 --quarter 3 --after NEW_DERIVED_PATH
just holy-grail-sheet --snapshot NEW_DERIVED_PATH --spreadsheet-id ID --sheet-id GID --dry-run  # then --apply
```

The sheet command checks the snapshot date against the tab title, backs up the
bounded grid, detects concurrent changes and edits only the owned summary block
and marker-based Details, formatting scores as `NUMBER, 0" зі 100"`. It never
deletes or recreates worksheets or rows, refuses insufficient space or conflicts,
replaces only owned groups, and verifies values, format, groups and outside-scope
state after readback.

Ungrouped Details require an explicit `Holy Grail - End` boundary; populated
legacy sections without one are refused.

## Capital diversification v2

`capital_diversification_v2` is the base method for every new snapshot (the
optional v3 record below derives from it, never replaces it). An `allocation`
object enables it; omitting `method_version` selects v2, without the object
enrichment is disabled, and an explicit v1 or unknown method is unavailable. An
invalid v2 never falls back to v1. v2 displays integer points out of 100, with
cash excluded from invested weights and shown separately.

v2 is group-level asset-class breadth: it rewards spreading invested capital
across uncorrelated economic groups and the eleven equity sectors. It cannot see
issuer or thesis concentration - two issuers in one group score as their combined
weight - so the concentration block below, not the score, gives that verdict.
Because breadth is grouped, the score can rise while a named holding grows; the
limits govern. The historical 15-20 stream target stays an aspiration and is not
mixed into v2 trends.

The model aggregates dated holdings into canonical economic groups, retaining
unknown invested amounts in the denominator. For weights `p` and correlations
`rho`, the similarity matrix has diagonal 1 and off-diagonal `max(0, rho)**2`;
`N = 1/(p.T @ Z @ p)`, `T = clip((N-1)/5,0,1)`. With total equity weight `E` and
eleven-sector breadth `b`, the score is `100*T + 25*min(E*b, 1-T)`. Six equally
weighted uncorrelated groups anchor 100; the score is not variance, a forecast,
a protection probability or an official Dalio rating. Unknown equity-sector
capital goes to the largest known sector; no known sectors gives zero breadth.

The main scenario uses 60 completed monthly USD returns and a business
correlation assumption of 0.25; other tests use 0.75 and a complete 36-month
window. Missing pairs get correlation 1; a separate recalculation with zero
bounds their model effect. Unknown invested weight above 5%, or a missing-pair
effect above five points, makes the scenario unavailable; alternatives never
replace an unavailable main result. Category changes across scenarios are
reported as dependence on assumptions or period, not a confidence interval.

Saved inputs include dated profiles, source histories, method and group
representatives, evidence-review cutoff and fingerprints; replay rebuilds
holdings, scenarios and reviewed risk facts without fetching market data.
Previous-v2 attribution separates market-relationship and position/profile
changes using unrounded values; a missing or incompatible previous basis leaves
the result usable. The result stays provisional when balance or sector evidence is
partial. Public output contains only whitelisted group and risk summaries, never
private holdings, confirmations or account identifiers.

### Concentration safeguards beside the score

`DIVERSIFICATION_DATA.concentration_v1` adds the issuer and thesis verdict the
score cannot see; the historical save key stays and the recorded `version`
(`concentration_v2`) gates the contract. Limits come from private
`allocation.concentration_limits` on stricter defaults (largest issuer <=5% of
equities and <=2% of NAV, top-4 <=20% of equities, core >=50%, China <=10%,
thesis clusters <=10%); membership from `allocation.linked_theses`. Each
over-limit issuer records a breach keyed by subject -
`issuer_pct_equities:<issuer>`, `issuer_pct_nav:<issuer>` (theses:
`thesis_pct_equities:<name>`). `largest_issuer` and `top4_issuers` stay plain
facts beside `issuers_over_limit` (id and both shares); any issuer-keyed breach
raises `issuer_limit_breached`; one row carries both denominators. Limits,
theses, decisions and settings freeze into the saved configuration fingerprint.

Recorded `allocation.concentration_decisions` entries shaped
`{id: {limit, subject (optional), decision: accept|reduce|exit, reason,
decided_at, review_by, max_value (optional), min_value (core floor)}}` resolve
a breach only by subject binding: a record with `subject` acts on the exact
`limit:subject` breach key, a legacy record without one only on the exact full
breach key; old fully qualified thesis records keep their verdict, a bare
`issuer_pct_equities` key never matches a prefixed issuer breach. It acts while
`decided_at <= as_of <= review_by` and `review_by - decided_at` stays within
`max_review_days` (constant 120; `allocation.concentration_decision_settings`
may override, but a non-finite or non-positive override fails the
configuration), and the current value fits the bound (`max_value`; `min_value`
for the core floor). A position that grows past its accepted bound expires its
resolution. An incomplete or out-of-horizon record resolves nothing and appears
as an `invalid_decision_record:<id>` warning (deduped, sorted, first three); one
bad record never takes the block down: the breach stays unresolved, is counted,
and leads the rows.

Broad index funds declare dated `holdings` - issuers and fund shares, `coverage`,
and `max_other_issuer_share` (no larger than the smallest listed share) as the
upper bound on any unlisted issuer - so underlying companies are measured and
direct plus fund exposure lands on one issuer. The uncovered fraction goes to
`unknown_lookthrough_pct_equities`, never spread over members. Undated holdings
or ones older than 90 days are unverified: the fund falls back to one ticker
issuer and keeps `unknown_issuer_lookthrough`; the unlisted tail warns only where
`max_other_issuer_share` times the fund's equity share could clear the issuer
limit, and incomplete coverage alone is no warning. A profile may assert
`core: true` (core bucket >=50%); a diversified holding company with declared,
fresh look-through (Berkshire via its SEC 13F filing) qualifies as core, its
ticker stops being an issuer, and stale holdings degrade it to a plain ticker
issuer with a warning while core credit stays.

A stock-category position without a profile is not dropped: in the equity buckets
(`Stocks`, `China Stocks` - a second stock bucket, also holding ETFs - and `REIT`,
a conservative, revertable owner call) it counts as one issuer at its ticker on
full equity value, in numerator and denominator. It gets no thesis membership, core
credit, country or look-through; the share surfaces as `unprofiled_pct_equities`,
and `unprofiled_positions` names the ids (first three). Unprofiled non-equity
positions (`Bonds`, `Precious Metals`, `Commodities`, `Short Selling`) only raise
the warning and gain no invented issuer facts.

The safeguards render beside the headline as rows or bullets, never a second big
number, including when v2 is unavailable or not applicable; the summary counts
all breaches and names unresolved ones. The section hides only with no readable
block (none, malformed, or an earlier contract): `concentration_v2` is current,
and saved `concentration_v1`-versioned blocks degrade silently - rendered like
records without the block, never re-read under new semantics or re-derived from
current config. A same-version block that fails replay degrades to one unavailable
row. What-if runs both states through the same subject-bound eligibility, lists
every issuer over a limit with both denominators, breach flags and decision state,
and reads a missing or old-version block as absent.

### Offline what-if scenarios

Repeatable `--what-if ID=+USD` deltas print a before/after comparison:

```bash
just holy-grail --what-if ID_A=+20000 --what-if ID_B=-5000 --offline
```

Each delta moves one position, funded from Cash (the net total returns to it). It
runs on a temporary copy of the newest saved snapshot or the passed `--snapshot`,
re-runs the same offline enrichment, and prints per-limit value, breach and
decision state plus the v2 score for both states. It writes no files, fetches no
data and places no orders; unknown or unprofiled ids exit with status 2; missing
offline history makes the after state unavailable.

## Capital diversification v3 (car-category pairs)

`capital_diversification_v3` is the v2 formula with one change: `car_business`
pairs come from a public category index, not the fixed 0.25 assumption. v2 stays
sealed as the source; v3 is a sibling `allocation_score_v3` in
`DIVERSIFICATION_DATA`, copying weights, sectors, non-car pairs and the 0.75
stress scenario from the saved v2 record and a frozen `car_category_v2` block.
`concentration_v1` and what-if stay on v2 - no block, no v3.

**What the car pairs are.** The Manheim Used Vehicle Value Index (US wholesale,
seasonally adjusted, monthly since 1997) proxies the inventory price of "buy
damaged, repair, resell". Each group's pair is `R * rho(index, group)` with
`R = 1`: a conditional assumption that the business inherits the index's price
channel, not a bound. Deal-level noise would lower the loading, calibratable only
from dated deals (`docs/car-deal-ledger.md`); financing, liquidity, repair, FX,
customs, tax and war sit outside the index, unbounded. The pair kind is `category`:
a category proxy, never a measurement or inference from carrying values.

**Measures per group** (all on the frozen block): same-window monthly
correlation; the group against the index one month later (price lags); and the
correlation inside the worst-quintile months of US equities over the full index
history since 1997 (at least 20 months). `cat_point` is `R` times the largest of
the three; `cat_upper90` uses the largest per-measure Fisher upper endpoint
(`z = 1.645`, two-sided 90%). Envelopes are chosen separately, so the upper can
come from another measure and sample; saved measures keep `selected`/`n`,
`upper_selected`/`upper_n` and the pair's `sample`. The endpoint ignores serial
dependence, overlapping months and selection across ten groups: neither a
portfolio confidence interval nor a business bound. A group with no usable
measure gets a missing pair `r = 1`; a missing-pair effect above five points makes
the scenario unavailable (v2 rule).

**Scenarios.** `m60`/`m36` x `cat_point`, `cat_upper90` and `r075` (the v2
assumption); the headline is `m60_cat_point` (`HEADLINE` in
`analytics/holy_grail/allocation_score_v3.py`; wider `cat_upper90` and stress
stay visible in the spread).

**Gates.** The block needs a matching fingerprint and method; a cutoff equal to
the completed month of `as_of_date` or the month before (a lag is flagged
`category_index_lagged`), never later (no look-ahead); finite month-end series
ending exactly at the cutoff; at least 120 index returns. A rejected or stale
block yields an `unavailable` v3 record (`invalid_car_category_block`); the view
then shows the v2 assumption numbers labelled as assumptions (`Припущення v2:
блок категорії авто недоступний`). A record that fails replay renders unavailable,
never falling back to v2 or v1; replay recomputes offline from the saved v2 record
and block.

**Regression.** With constant pairs 0.25 and 0.75, v3 pair substitution
reproduces the saved v2 scenarios to 1e-8. The block method is `car_category_v2`;
`car_category_v1` is rejected. Snapshot scores belong in ignored `data/`, not here.

**Limits.** One index, one channel; `R` unknown; the 60-month window holds
essentially one rate-shock regime; 2008-era coverage is missing for China,
emerging markets, crypto and EUR high yield; Manheim history is revised (raw file
sha256 recorded) and Cox is an interested party; the stress measure uses the same
long-history sample in both window scenarios, understating window sensitivity; US
and EU data say nothing about Ukrainian customs, VAT, FX or war. The refresh is
monthly: a block is accepted only while its last month is at most one month behind
the snapshot's completed month (`max_index_lag_months` in
`analytics/holy_grail/car/category.py`). Rebuild monthly after Manheim publishes
(`just car-category build ...`), copy to `data/car_category/block_latest.json`,
then run the pipeline.

## Risk progress v3 (`risk_progress_v3`)

The headline for new snapshots: one score from 0 to 100 for an individual,
non-accredited, long-only investor. It keeps the Holy Grail idea and the
`risk_progress_v2` formula but with target 7 and assets outside the broker. It
is a sibling from the replayed `capital_diversification_v2` record and frozen
car block (`analytics/holy_grail/risk_progress_v3.py`), saved as
`DIVERSIFICATION_DATA.risk_progress_v3`; `risk_progress_v2` (100 = 15 streams,
invested only) stays in the details.

**Goal.** What the score aims for and why the target is 7:
[diversification-goal.md](diversification-goal.md).

```
DR = sum(w_i * sigma_i) / sqrt(wᵀ Σ w)      N_effective = DR²
score = clip(100 * (1 - 1/DR) / (1 - 1/sqrt(7)), 0, 100)
```

| streams | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| points | 0 | 47 | 68 | 80 | 89 | 95 | 100 |

The display rules are those of v2: 100 only at 7.0 equivalent streams or more;
otherwise the headline is capped at 99 and the detail at 99.9.

**Universe and weights.** The invested part of the v2 record plus declared private
streams, weighted by value and applied to the whole window like v2. Cash stays
outside except deposits declared from Cash; the cash line shows the v2 cash share
net of those deposits, with the full v2 share on a separate row. Balances and
totals are never changed.

**Streams.**

- Measured: a v2 group (its representative history), the car business
  (CPRT/KMX/OPLN basket of the frozen block, as in v2), and equal-weight,
  all-names-required proxy baskets: `infrastructure` BIP+BEP, `private_equity`
  BN+KKR, `private_credit_funds` BIZD, `timberland` WOOD. Proxies carry
  listed-equity beta and earn little diversification credit.
- Modeled private streams, one per (class, country, location):

  ```
  r = βᵀF + σ_res * (sqrt(s_c) g_country + sqrt(s_k) h_class,country + sqrt(s_l) k_location)
  ```

  `F` are the `equity_us` (SPY), `treasury_medium` (IEF) and `commodities` (DBC)
  representatives, plus `EURUSD=X` for rows declaring `corr_fx_eur`.
  `β = Σ_F⁻¹ (σ_F ⊙ ρ) vol`, with `ρ` scaled down when it would explain more
  than 95% of the variance, and `σ_res² = vol² - βᵀ Σ_F β`. `g`, `h` and `k` are
  independent unit factors with shares `s_c + s_k + s_l = 1`; there is no
  idiosyncratic term, so splitting one holding never adds a stream. One location
  across classes shares `k`; different cities of one country share `g` and `h`;
  countries are linked only through `F` (and the UA link). US and `other` rows
  have no country factor; without a location (or with `diversified` or `-`) `s_l`
  folds into `s_k`; locations are normalized (whitespace, case).
- UA link: the Ukrainian country factor is tied to the measured Ukrainian
  streams (the car business, only with a reviewed `business_geography` of
  Ukraine, and Ukrainian proxy holdings): `g_UA = ρ e/σ_e + sqrt(1-ρ²) u_UA`,
  where `e` is their value-weighted residual against the other measured columns
  and `ρ = car_link_rho`. With the car business's geography unreviewed, the link
  applies in the adverse scenario only, with a warning.

**Covariance.** The measured columns (v2 groups, car basket, proxy baskets and
factors) are shrunk jointly with the v2 Ledoit-Wolf estimator.
`Σ = A blockdiag(Σ_shrunk, I) Aᵀ`, positive semidefinite by construction. With no
private streams, `A` selects only the v2 groups and DR equals v2 exactly.

**Scenarios.** The central parameters give the headline; favorable uses the low
values of every correlation, residual-share triplet and `car_link_rho`, adverse
the high values. A separate ×0.5/×2 sensitivity scales private volatilities (DR
is not monotone in volatility); neither is a confidence interval. "Внесок
приватних потоків" is sequential on the same window and block: v2 groups alone
(reclassified positions put back), modeled streams, then proxies (the headline).

**Parameters.** `analytics/models/private_streams_v1.json` holds public
literature and index values only, with sources and a non-accredited access note
per row. A fingerprint of behaviour-bearing values only
(`parameters_fingerprint`) is embedded; descriptions, sources, access notes, proxy
labels and the changelog stay outside. A row accepts only `vol_annual`,
`share_scenarios`, `cash_eligible`, `corr_equity`, `corr_bonds`, `corr_commodity`,
`corr_fx_eur`, `basis`, `sources`, `access_non_accredited`, `notes`
(`MODEL_ROW_KEYS`); any other key or malformed row raises
`ValueError('model_rows')`. A behaviour-bearing change needs a new file and
method version, and the boundary shows "Змінено методику". Rows (class:country):
`residential_re` US, UA, PL, DE, ES, PT, AE, GE; `commercial_re` US, UA, DE, ES,
PL; `farmland` US, UA; `development_land` US, UA; `ovdp_deposits_uah` UA (the only
Cash-eligible row); `ua_sovereign_usd` UA (USD OVDP and Eurobonds); `p2p_loans`
US, UA, other. Polish farmland is excluded (farmer-only).

**Private declaration** (`data/holy_grail_config.json -> private_streams`,
frozen in the v2 configuration; keys only here). `entries[]` requires `id`,
`class`, `country`, `value_usd`, `valuation_as_of`; optional: `location`,
`currency`, `debt_usd`, `nav_source` (`outside`/`cash`), `held_from`,
`valuation_source`, `reviewed_at`, `primary_residence`. `reclassify` maps
`{position_id: {class, country, location?, source_identity?}}` to move an itemized
v2 position out of its group (P2P out of the HYG proxy, broker-held Ukrainian
Eurobonds); a positional id (`p2p:i`) needs the position's `source_identity`.

- A primary residence is excluded and counted.
- `debt_usd > 0` gives `unsupported_leverage`; `held_from` after the snapshot
  excludes the entry. `nav_source: cash` is allowed only on cash-eligible rows
  and must not exceed v2 Cash in total (`cash_entries_exceed_cash`).
- A valuation older than 12 months makes the record provisional.
- An unknown key, class or country, or a bad reclassification, gives unavailable
  (`invalid_private_streams`, `class_not_in_model`, `invalid_reclassify`);
  nothing is dropped silently.
- A declared class without a usable series gives unavailable (`no_history`);
  factor and proxy histories load only when private streams are declared.
- A missing or unreadable parameter file gives unavailable with its cause
  (`private_model_invalid:<Error>`); an unexpected failure does the same
  (`invalid_inputs:<Exception>`). A sealed record replays only when the same
  failure reproduces.

**Calibration (public data, 60 months to 2026-10; parameters frozen by sha256
before any score was read, never tuned).** Target 7 was calibrated on
representative long-only portfolios; the anchor table gives the scale points.
This is a policy check, not a forecast, and scores stay in ignored `data/`.

**Coverage of a 120-item asset list.**

| Treatment | Items |
|---|---|
| Measured v2 groups | equities of any style, region, sector or size; listed REITs, infrastructure companies, PE managers and BDCs held as stocks; bonds, bills and money-market funds; metals and commodities; crypto |
| Modeled private streams | residential and commercial property (fractional and non-traded REITs as their class with location `diversified`), farmland, development land, UAH deposits and OVDP, USD OVDP and Ukrainian Eurobonds, P2P loans |
| Measured listed proxies | infrastructure; private equity, venture and pre-IPO; retail private credit funds; timberland |
| Out of scope / not in this version (`class_not_in_model`) | cash, US bank deposits, repos and stablecoins; strategies and contracts (no shorts, leverage or hedge-fund strategies); collectibles, royalties and IP, litigation finance, cat bonds, carbon, shipping leasing, operating agricultural businesses, own business other than the car business, tokenized RWAs, NFTs |

**Limits.** Ukrainian parameters under war conditions rest on thin data (asking
prices since 2021, judgement for commercial property, P2P, Eurobond correlations
and `car_link_rho`), so the scenario range is wide. `residential_re:GE`,
`commercial_re:PL` and `residential_re:AE` rest on thin or judgemental series.
Declared values are appraisals; the 60-month window is one regime. Moving a
stream between locations is not a ranking - in an equity-heavy portfolio, moving
a Ukrainian stream to the US can add more diversification than moving it to
another Ukrainian city. Geography is a pairwise link structure, not a score; the
score is a modelled effect under a product scale, not a grade, forecast or
measurement of any property or business.

## Risk progress v2 (`risk_progress_v2`)

The headline for snapshots saved before `risk_progress_v3` (a detail row after
it): one score from 0 to 100 for the invested part, answering how much of the
modelled diversification effect behind the Holy Grail idea the current mix
shows. It is a sibling from a saved, replayed `capital_diversification_v2`
record and frozen car proxy block (`analytics/holy_grail/risk_progress.py`),
saved as `DIVERSIFICATION_DATA.risk_progress_v2`; v2 and v3 stay calculated and
shown in details. Cash is outside and shown separately.

```
standalone = sum(w_i * sigma_i)          sigma_p = sqrt(wᵀ Σ w)
DR = standalone / sigma_p                N_effective = DR²
benefit = 1 - 1/DR                       target_benefit = 1 - 1/sqrt(15)
score = clip(100 * benefit / target_benefit, 0, 100)
```

`w_i` is group `i`'s invested weight, `sigma_i` the monthly standard deviation of
its representative, `Σ` the shrunk sample covariance on common complete months
(diagonal = plain sample variance, ddof 1). Current weights apply to the whole
window: a conditional estimate of today's risk structure on the representatives'
history, not past positions or returns. The comparison base is the same assets at
full positive correlation, not the S&P 500, cash or actual risk on a date;
monthly versus annual units do not change DR.

**Covariance estimate.** With about 15 groups and at most 60 monthly rows the
plain sample covariance is noisy, so `Σ` uses Ledoit-Wolf shrinkage toward a
constant-correlation target (Journal of Empirical Finance 2003; Journal of
Portfolio Management 2004). The sample matrix `S` (moments divided by `T`)
combines with `F`, which keeps each group's variance and gives every pair the
average sample correlation `r`: `Σ = (δ F + (1 - δ) S) * T / (T - 1)`. The
intensity `δ` in [0, 1] is `clip(κ / T, 0, 1)`, recomputed for each window and
frame (60 and 36 months, volatility multipliers, representative comparison);
`δ = 0` when target equals sample, and under two groups no shrinkage applies.
The factor `T / (T - 1)` keeps the ddof-1 scale, so displayed volatilities keep
their meaning; DR does not depend on it. The target keeps each `sigma_i` and the
result stays positive semidefinite. Shrinkage lowers correlation noise but pulls
extreme pairs (including hedge-like negative ones) toward the average, so it can
raise or lower the score. The record stores target, intensity and average
correlation; a changed estimator changes the fingerprint, so older records
render "Недоступно".

**Scale.** 100 means the effect of 15 equal-risk independent streams (about a
74.18% volatility reduction in that model): a product policy, not a Dalio rating
or a promise of lower future risk. The text never says the Holy Grail is
"achieved". Anchors follow from the formula alone (`DR = sqrt(N)` for `N`
equal-risk independent streams), independent of the estimator:
1 -> 0, 2 -> 39.484063, 3 -> 56.976152, 6 -> 79.772287, 15 -> 100.

`N_effective` is the number of identical independent streams with the same
modelled volatility effect, not a count of independent profitable businesses.
Covariance alone does not prove independence or crisis resilience. A value
above the number of groups is a hedge result (`hedge_driven_count`). A higher
score does not necessarily mean lower absolute volatility, so annual modelled
portfolio volatility (`100 * sqrt(12) * sigma_p`) is shown beside it; a score
raised only by the assumed car-business volatility is not an improvement.

**Inputs and window.** Every group with a positive invested weight is included;
weights must be finite, non-negative and sum to 1 (tolerance 1e-8). The main
window is the last 60 calendar months up to the last completed month; the
calendar index is built before gaps are dropped, older months are never
borrowed, and covariance uses common complete rows. 36-59 observations make the
result `provisional`, fewer than 36 `unavailable`. Every main series and the
last common month must end no earlier than one month before the cutoff: a
one-month lag is `provisional` with a warning, a larger lag `unavailable`. A
positive weight without a usable series (including `unknown`) makes the score
`unavailable`; no silent drop or rescale, and a provisional parent stays
provisional. The 36-month window is a diagnostic and never replaces the main.

**Car business.** There is no return series for the business. The score uses the
monthly total return of the equal-weight CPRT/KMX/OPLN basket (all three
required, adjusted prices in USD, no forward fill) as a labelled working
assumption and owner decision - not a measurement, conservative or a lower
bound. The basket is frozen in `car_proxies_v3`; offline recalculation accepts
`car_proxies_v2`. Other channels are not averaged into the covariance.

**Risk contribution.** For every positive group on the main window:
`risk_share_i = w_i (Σ w)_i / sigma_p²`, the Euler share of modelled portfolio
volatility (its share of variance); it can be negative for a hedge and is never
clipped, and shares sum to 1 (tolerance 1e-8). It is not a probability or share
of maximum loss: short Treasuries can have a small share and still lower
absolute volatility.

**Details stored beside the score.**

- Worst modelled months: the six lowest `wᵀ r_t` months (ties: earlier first),
  their mean and each group's mean `w_i r_i,t` contribution; with 36-59
  observations the rule stays six (provisional).
- Car-business write-off: `weight_pct_nav x {0.5, 1.0}` as arithmetic, with all
  other assets unchanged and extra liabilities, collateral losses and taxes
  ignored. Not a probability or forecast; not shown when car weight is zero.
- Car-series volatility sensitivity: x0.5, x1.0, x2.0 with weights, other series
  and common months unchanged; reports series volatility, DR, score, car risk
  share and portfolio volatility. Scaling the whole series keeps correlations,
  so it is not repair, liquidity or failure risk; the headline is unchanged.
- Car-representative sensitivity: Manheim, BLS used cars or AUTO1 on a common
  sample, with sample size; not a calibrated model of the business, and kept
  apart from the volatility sensitivity - the two are never merged into one
  "honest range" or confidence interval. An incomplete comparison never changes
  or blocks the headline.
- Context only, outside the headline, scenarios and covariance: the Ukrstat CPI
  mixes new and used vehicles, a monthly price ratio is an experimental indicator,
  and the qualitative environment map has no percentages or thresholds.

**Statuses and gates.** `modeled`, `provisional`, `unavailable`,
`not_applicable` (no invested part); unavailable and not-applicable records carry
null numbers, never 0. A missing basket, corrupt block or positive weight without
a series gives `unavailable`, but the record is still written; a stale or short
auxiliary series only makes the comparison incomplete. Block integrity (version,
method, fingerprint, calendar, no future months) is judged separately from series
freshness. Replay recomputes offline from the saved v2 and block (floats absolute
tolerance 1e-8, integers, strings and flags exact); a non-replaying record renders
"Недоступно" and never falls back to v3, v2 or `risk_progress_v1`. A fingerprint
proves stored-content consistency, not source correctness; a corrupt sibling stays
unavailable in its own row without blocking a valid headline. A valid `unavailable`
record (basket not collected, data outage, offline run without a current cache, or
`just holy-grail` without `--car-proxies`) shows only method, status with reason,
date and safeguard rows; no other number appears, the replayed v2 or v3 included,
until the next successful run.

**Display.** The compact headline is an integer with an approximation sign:
`min(99, floor(score))` until 15 streams, then 100; details use one decimal
rounded down, capped at 99.9 before the target. The summary row shows the integer
score ("N зі 100" in Sheets); the scale anchor and equivalent streams sit in the
conclusion note. It also shows the two largest positive modelled risk
contributions as "group: share of capital -> share of risk", the car assumption,
the data line (date, retrospective flag, quality reason) and cash outside the
score. A score is compared only inside the same method ("Змінено методику" across
methods); concentration warnings (`concentration_v1`) stay visible.

**Limits.** The basket is not calibrated to the business; the 60-month window
holds essentially one rate-shock regime; one representative stands for each
group; revised-index vintages are known only where recorded, so a historical
recalculation is marked retrospective (the block-date rule is enforced on replay,
but a caller-asserted flag is not provable). The score says nothing about expected
return, holding quality, liquidity or all-weather protection. Shrinkage reduces
estimation noise for about 15 groups on at most 60 months, not model risk: the
intensity comes from the same short sample. A listed basket cannot see the
private business's leverage, inventory financing, currency, country, illiquidity
or key-person risk; write-off rows are a coarse tail check. The score counts any
low-correlation stream, profitable or not; no return-quality layer or
growth/inflation sensitivity is measured. Definition of DR: Choueifaty, Froidure
and Reynier, "Properties of the most diversified portfolio" (2013); the 0-100
scale is this product's policy.

## Risk progress (`risk_progress_v1`)

A separate method: how many independent, equal-risk return streams the current
mix behaves like. A sibling of a saved, replayed `capital_diversification_v2`
record (`analytics/holy_grail/risk_progress.py`), never mixed into v2/v3 or
`risk_progress_v2` trends; superseded as headline by `risk_progress_v2` but still
readable in saved records and details. It is saved only with a frozen car proxy
block (`car_proxies`); without one nothing is saved and views are unchanged. It
revives `risk_equivalent_streams_v1` on frozen v2 group histories, not position
series.

```
DR = sum(w_i * sigma_i) / sqrt(wᵀΣw)      N_DR = DR²      volatility reduction = 100 * (1 - 1/DR)
progress = 100 * clip((N_DR - 1) / (15 - 1), 0, 1)
```

- Streams are v2 groups with a return history (one representative each) at the
  v2 invested weights (DR does not depend on a common scale). Σ is the sample
  covariance (ddof 1) on common months only; missing months are never zero-filled.
  Raw Ledoit-Wolf is deliberately not used: it inflated the shortest Treasury
  group's volatility and made the count depend on duplicating a stream.
- Windows: 60 completed months (headline) and the latest 36 (comparison).
  `modeled` needs every month up to the last completed month; 36-59 common
  months are `provisional`; fewer than 36, a non-finite or non-PSD covariance,
  or zero volatility is an explicit `unavailable` with a reason, never a
  number. A count above the number of streams is `hedge_driven_count`.
- The scale is a policy choice: 15 streams maps linearly to 100 (equal-risk
  uncorrelated streams cut modeled volatility by 74.18%), not a percentage of
  risk; the display rounds down to one decimal and reads 100.0 only at target.
- Scope: only groups with a return history. `car_business` has none, is excluded
  and reported (share of invested capital and NAV), never replaced by a proxy in
  the headline and appears only in labelled scenarios. Cash is outside;
  `partial_scope_excluded_weight` marks the covered part, not the whole portfolio.
- What it does not say: it measures the risk balance of today's weights over
  past months, not holding quality or expected return after costs, and one ETF
  stands for each group. A high count is not "Holy Grail achieved".
- The record stores per-window counts, DR, variance shares, annualized volatilities,
  coverage, method, fingerprint and v2 ids; `validate_saved_risk_progress_v1`
  replays the v2 record and recomputes from its frozen histories and proxy block.

```bash
just risk-progress --snapshot data/snapshots/combined_data_<date>_<timestamp>.json [--car-proxies PATH] [--json] [--out NEW_FILE]
```

The command validates the saved v2 record by replay before showing a number,
changes no snapshot, fetches nothing and never writes Sheets. `--out` writes a
new file only, outside the automatic snapshot directories. `--car-proxies`
defaults to `data/car_category/proxies_latest.json` when it exists.

### Car-business scenarios (`car_proxies`)

Public data cannot measure the owner's business. A scenario asks how the count
would change if the business behaved like this public series. The answer is an
assumption, shown as a range, never the headline.

- Proxies (`analytics/holy_grail/car/risk_proxies.py`): Manheim Used Vehicle
  Value Index (US wholesale); BLS CPI used cars and trucks (US retail); AUTO1
  Group Price Index (EU wholesale; medium confidence); and the equal-weight
  total return of CPRT, KMX and OPLN (listed remarketers; all three names
  required, a CSV missing one leaves the proxy out as `missing_basket_names`).
- Block `car_proxies_v2` adds the Ukrstat national CPI "Купівля транспортних
  засобів" (COICOP 07.1; the car sub-items have codes but no published national
  data), converted to USD as `index / 100 x rate(t-1) / rate(t) - 1` with the
  NBU monthly mean of official daily UAH per USD rates; it mixes new and used
  vehicles bought by households (medium confidence). `just car-proxies
  fetch-ukraine --raw DIR --as-of DATE` downloads both raw files (network,
  never overwrites); without them the series is left out as
  `source_unreadable`. `car_proxies_v1` blocks still validate.
- Frozen block: `just car-proxies build --raw DIR --proxy-csv CSV --as-of DATE
  --out data/car_category/proxies_<date>.json` converts each series to monthly
  simple returns, trims it to the last completed month, keeps 120 months and
  records the SHA-256 of every raw file. `validate_block` rejects a changed
  value, method or name, look-ahead, a series more than one month stale and
  fewer than 36 months. Copy to `data/car_category/proxies_latest.json` for
  `just run` (or pass `--car-proxies PATH`); the folder is git-ignored. Rebuild
  monthly; a stale block shows `invalid_car_proxies_block` and the headline stays.
- Scenario: the car business is one more stream carrying the proxy's returns at
  its unchanged v2 weight, with the same common-month rule on the 60-month
  window. It reports the count, the points, the change against the covered part
  on the same months (`baseline_streams`, so a sample change is not an effect),
  the correlation with the covered portfolio and with US equities, annual
  volatility, a relation class by absolute correlation (below 0.25 not
  correlated, 0.25 to below 0.75 moderately, 0.75 and above correlated) and the
  effect (adds or reduces diversification).
- Reading the range: price indexes move far less than a leveraged inventory
  business and barely correlate with other groups, so they raise the count; the
  listed basket moves like equities and lowers it. Which is closer needs the
  owner's own monthly history (not available).
- The record embeds the block. An invalid or missing block makes only the
  scenarios unavailable; the headline stays. The same block feeds
  `risk_progress_v2` (offline `car_proxies_v2`; normal collection builds
  `car_proxies_v3`, see "Risk progress v2").
