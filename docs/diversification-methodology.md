# Portfolio diversification indicators

> Reader's guide: the current base method is "Capital diversification v2", with
> "Concentration safeguards beside the score" and "Offline what-if scenarios"
> under it (near the end of this file). Optional sibling records follow it:
> "Capital diversification v3 (car-category pairs)" for the car-business pairs.
> The headline for new snapshots is "Risk progress v3 (`risk_progress_v3`)", the
> individual-investor score with private streams; "Risk progress v2
> (`risk_progress_v2`)" follows it and stays in the details. The
> older "Risk progress (`risk_progress_v1`)" and "Car-business scenarios
> (`car_proxies`)" follow it as the last sections. Public car-market context and
> the category evidence are in `docs/car-resale-market-context.md` and
> `docs/car-flip-category-evidence.md`. "Historical capital-weighted score (v1)",
> "Count and interpretation", "Ten-check policy", "Hypothetical stress policy"
> and "Simple Holy Grail indicator (v1)" describe frozen historical records.
> "Private evidence and collection" also covers the retired calculators' inputs,
> but the `diversification.exposures` record format it defines is still read by
> v2 for risk facts.

## Historical capital-weighted score (v1)

The following v1 description applies only to existing historical records. New
production enrichment calculates v2, documented below.

`DIVERSIFICATION_DATA.allocation_score`, version `capital_diversification_v1`,
answers how invested capital is spread across economic groups and equity sectors.
More means greater diversity in this model. It is not a risk-adjusted return,
variance, literal count of independent factors, or an official Dalio rating.
Cash is outside the score and remains visible as a percentage of full NAV.

With invested weights p, positive-clipped pair correlations r, conditional GICS
sector shares s and sector breadth b=(1-sum(s^2))/(1-1/11):
`D=2*sum(p_g*p_h*(1-r_gh)); B=sum(p_g^2*b_g); score=clip(A*D+25*B,0,100)`.
Unknown sector mass goes to the largest known sector. Unknown pairs use r=1.
Ticker/account splits and shared HYG lending proxies cannot create groups.
Treasury groups are 0-1y (SHV), >1-10y (IEF), >10y (TLT).

The calibration embedded in historical v1 records uses October 2021 through
September 2026 and the agreed six equal blocks: US equities;
other equities (EFA/MCHI); Treasuries (SHV/TLT); gold; commodities; Car Resale.
The coefficient is frozen, including for subsequent quarters and sensitivity.
Car Resale has assumed correlations .25/.75 to public groups; these are not
observed business returns or crisis forecasts. US used-car CPI is not used.
Published factsheet "Other" and cash sectors remain unknown conservatively.
Single-company sectors in `economic_profiles_v1.json` are reviewed economic
classifications using the GICS vocabulary, not a licensed official GICS feed.
KWEB has a confirmed China market profile but no verified quarter-end sector
breakdown; it earns no invented sector breadth.

Each pair uses its own real overlapping months in the fixed last-60 calendar grid,
minimum 36. Store count and last month per pair; never fill missing returns.
36-59 observations, lagged histories, cached balances or unknown sectors produce
a provisional result. No hidden quality multiplier is applied. Unknown capital
above 5%, or maximum missing-pair influence `2*A*sum(p_g*p_h)` above 5 score
points, makes the main score unavailable. No invested assets: not applicable.

The capital score follows the explicit Cash exclusion: typed Cash ledger rows
`debt` (MY_DEBT personal liability) and `manual_reconciliation` remain outside its
scope with a visible warning. They are not automatically brokerage financing.
Negative broker/investment cash, negative position values/quantities and declared
leveraged/nonlinear positions still block the score. Legacy diagnostics retain
their stricter borrowing treatment. NAV and every financial amount stay intact.
Reconciliation uses max($1, NAV*1e-6); invested weights normalize to the reconciled
position sum. No phantom unknown asset is created for tolerated rounding.

Private `holy_grail_config.json` enables the feature with an `allocation` object.
Historical records embed their calibration and profiles. `allocation.profiles`
contained exact dated private confirmations (e.g. the individual Treasury and
identity-bound Car Resale). Unknown instruments require explicit profiles;
regional exposure is not inferred from currency, listing venue or broker bucket.
Historical v1 records already contain this block. New enrichment calculates v2
and preserves existing historical analytics; it does not regenerate v1.
Normal pipeline enrichment collects unique histories once before persistence.
HTML/Sheets display the same saved result; output rendering neither fetches nor
recalculates it. Integrity validation checks frozen inputs; an explicit replay
validation independently recomputes from the saved histories, not current config.

Display floors the score, snapping only floating noise within 1e-8 of an integer.
0-49: concentrated; 50-79: partly diversified; 80-100: well diversified within the
model. Reference 100 is a practical threshold, not a theoretical maximum.
Sheets writes display_score/100 with 0% format to B10. The other four summary
rows contain conclusion, largest group, business sensitivity and date/Cash.
Scoped updates preserve outside cells/formats/groups, backup before mutation,
read back after timeout and never blindly repeat a write. Generated reports and
private data are excluded from the PR. Live readiness requires actual rendering
and production readback; synthetic tests are not production proof.

The current v2 Sheets builder reserves A10 for the shared summary - fourteen
rows today, more when concentration safeguards extend it. When
benchmark rows would overlap, it places the intact performance panel below the
summary. Details start below every populated panel, so their row group cannot
hide unrelated holdings or income. Typed allocation_score cells use 0% formatting.
The standalone historical writer uses the same saved view and checks the
snapshot envelope date against the indicator before authentication or writing.


The following count, policy, and indicator sections describe historical saved
records only; their original calculators are retired. The previous headline was
the independent `DIVERSIFICATION_DATA.indicator` described in
"Simple Holy Grail indicator (v1)" below. The ten-check policy sections document
legacy diagnostics and do not gate the current headline.

This is our policy for long-term USD resilience, not Dalio's proprietary method,
a forecast of independence, or an investment-attractiveness score.

## Count and interpretation

`risk_equivalent_streams_v1`: `DR = sum(w_i * sigma_i) / sqrt(wᵀΣw)`;
`N_equivalent = DR²`; volatility reduction = `100 * (1 - 1/DR)`.
Weights use exposure value / reconciled total portfolio value. Sample covariance
and volatilities use identical observations, adjusted monthly USD returns and
60 completed calendar months. The latest 36-month comparison uses the same
exposures and valuation-date weights. Missing observations are not zero returns.
36–59 common observations are provisional; below 36 withholds the count.

Identical instruments, histories and shared proxy exposures are combined.
ETF constituents are not extra owned streams. Negative correlations retain
hedging benefits: two equal-risk exposures at -0.90 can yield 20 equivalents.
The output reports modeled exposure count and flags hedge-driven counts.
15/20 independent equal-risk streams yield 15/20; 15 at correlation 0.50 yield
1.875. There is no automatic “Holy Grail achieved” claim. Compare thresholds
before display rounding; 14.9996 displays `<15`, not `15.00`.

Legacy policy only: Cash adds no streams. Only documented USD cash without unsecured dependencies
and identified USD Treasury holdings with <=365 days remaining are analytical
reserves. Stablecoins remain subject to issuer/platform risk, even if the
financial pipeline calls them cash. Financial classifications never change.
All confirmed reserves: zero streams, no applicable score. Zero/effectively zero
variance withholds the count. Unsupported shorts, borrowing, leverage or
nonlinear exposure make the assessment unavailable.

DR² interpretation: [TOBAM dashboard, July 2015](https://www.tobam.fr/wp-content/uploads/2015/08/TOBAM-Diversification-Dashboard-July-2015.pdf).
Legacy `holy_grail_progress_v1` used inverse squared-correlation concentration
weighted by absolute Euler risk contributions. It remains stored separately;
its values and percentage-to-15 headline must not be mixed into new-method trends.

## Ten-check policy

`diversification_policy_v1` used the defaults below as editable private policy
inputs, not Dalio's thresholds or the user's personal loss limits.

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

Every check saves value, threshold, pass/fail/unknown and reason. The bounds are
`10 * passed` through `10 * (passed + unknown)`. Four passes, three failures,
three unknowns give 40–70/100. A point score requires all ten resolved. All
unknown gives “Недостатньо даних”, with 0–100 in diagnostics. No score bands
are automatically labeled good. Family, issuer, breadth and counterparty
failures remain visible beside the score. Expected-return reviews are separate.

Statistical checks (family, breadth, stability) require 60 common observations,
>=99% of non-reserve value with suitable histories, no material weak-proxy or
stale valuation limitation. Material means >=1% of total value by default.
Otherwise subset statistics remain provisional and these checks are unknown.
Known value establishes a lower bound; unclassified value enlarges the upper.
Pass only when the upper bound meets the threshold; fail when the lower breaches
it. Material stale valuations currently block all value-based checks
conservatively. Invalid totals or reconciliation failure invalidate the result.

Confidence describes input evidence, not prediction: high if all checks resolved
without material flags; medium if >=8 resolved without material proxy/valuation
flags; low otherwise. Reserve share is separate: cash can improve stress losses
without fixing concentration among risky holdings.

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

Nominal government: `-rate_duration * nominal_yield_change`.
Inflation-linked: `-rate_duration * real_yield_change`.
Corporate credit: add `-spread_duration * spread_change`.
Use documented effective-date duration in years, shocks as decimal yield changes.
Missing duration is unknown, never inferred from “Bonds”. Floor losses at 100%.
First-order duration omits convexity/nonlinearity, particularly for large shocks.

Counterparty/depeg tests lose 100% of each unsecured dependency group, reduced
only by documented protection/recovery in the exposed fraction. One position
may depend on both a platform and stablecoin issuer; test groups separately,
never sum their losses against the same principal. The largest loss is reported.
Local stress loses 30% of car inventory and 20% of explicit non-USD monetary
exposure, applying each position once at the larger applicable loss.
Listing currency alone is not economic FX exposure. Unknown bounded exposure
uses 0–100% loss without assumed hedging gains. Scenario losses may be negative
if documented gains exceed losses. They are hypothetical, not forecasts.

## Private evidence and collection

Extend ignored `data/holy_grail_config.json`, retaining existing `mappings`
and `qualifications`. Optional `diversification` contains `exposures`, `policy`
and `cash_components`. Exposure keys are canonical IDs (for example `ib:IHYG`)
or `category:<name>` for facts genuinely shared by that category.
Index-keyed entries (`crypto_lending:0`, `p2p:0`, `other_assets:0`) must also
contain a matching `source_identity`: `{"account": "...", "asset": "..."}` for
lending, `{"account": "..."}` for P2P, or `{"asset_id": "..."}` for cars.
This applies to per-position mappings, qualifications and risk evidence. After
source rows move, mismatched entries are ignored, leaving default weak proxies
and unknown facts until the records are rebound. Entries without a stable source
identity cannot establish position-specific evidence; family records remain valid.

Each record needs non-empty `source`, `effective_from` (and optional
`effective_to`) plus `reviewed_at` ISO date. Future reviews are rejected;
retrospective factual reviews are allowed and the replay is labeled retrospective.
Dated issuer look-through, duration, currency and redemption evidence must be
appropriate for the valuation date. A review field alone cannot establish proxy
suitability or approve investment rationale.

Fields: `stress_class`, `currency`, `maturity`, `rate_duration`, `spread_duration`,
`issuer_weights` (corporate issuer -> fraction, including fund overlaps),
`corporate_issuer_applicable: false` only with sourced exemption,
`counterparty_complete`, `counterparty_groups` (dependency -> unsecured loss
fraction), `liquidation_days`, `fx_monetary` boolean. Supported stress classes
are the table classes (`equity`, `gold`, `silver`, `commodities`, `crypto`,
`stablecoin_lending`, `p2p`, `car_inventory`, `stablecoin_cash`, `usd_cash`)
plus `treasury_reserve`, `nominal_government`, `inflation_linked`,
`corporate_credit`. `leveraged` or `nonlinear_risk` flags reject assessment.

Cash children partition existing NAV, never add it. `cash_equivalent:<asset>`
uses canonical Cash_Equivalents. Optional `cash_components` specify a canonical
Breakdown key with `excludes_cash_equivalents: true`; only use demonstrably
disjoint components. Unidentified remainder is `cash:unclassified`, not safe USD.
Over-allocation fails the quality assessment while preserving normal reporting.
Negative source cash balances, including broker cash and cash breakdown accounts,
make both analytics estimates unavailable even when total net cash is positive.
Reconciliation allows the source total's $1 display precision. After reconciliation,
analytical percentages use the unrounded component sum; saved financial totals
are preserved. Discrepancies beyond the allowed tolerance remain invalid.

Do not infer returns from business carrying values. Car resale requires dated
inventory/cost/proceeds/turnover records (see `docs/car-deal-ledger.md`).
HYG and used-car CPI are weak sensitivity proxies until substantive fit is
established; defaults, redemption, depeg and Ukraine operating risks remain
omitted. Do not manufacture residual returns.

Actual listing currency, quote units and historical FX are handled by the
existing shared collector; do not add dividends again to adjusted histories.

Historical `DIVERSIFICATION_DATA` records contain count/policy versions, score
bounds, ten checks, confidence, coverage/reserves, scenarios, dates,
qualifications and input/config/history/policy fingerprints. Reports and Sheets
render the saved records. Invalid or mismatched blocks withhold results. Never
reuse a changed-input score. Private data/evidence remain ignored; public views
whitelist generic labels, percentages and counts. No trades or automatic
reallocation are included.

Historical enrichment uses `just holy-grail --snapshot ... --output ... --offline`
and an explicit HTML `--after` path. Originals/latest pointers remain unchanged.
Exclude post-period observations and current holdings. Revised retrieved series
are retrospective; observation dates do not imply publication-date availability.


## Simple Holy Grail indicator (v1)

`DIVERSIFICATION_DATA.indicator` was the primary risk-equivalent count, independent
of the ten-check score. Reports and Sheets render the frozen saved block; new
enrichment no longer calculates it.
HYG is a disclosed lending/P2P proxy; US used-car CPI is a disclosed Car Resale
valuation proxy, not actual business return. Compare the direct-only count on
the identical monthly observations. The 36-month comparison requires all 36
calendar observations ending at the primary history end. Never zero-fill gaps.

All exposures have exactly one role: direct, model, confirmed short US Treasury
reserve, Cash outside the count, or uncovered. Percentages use canonical NAV,
with reconciliation tolerance max(1 USD, NAV * 1e-6). Cash stablecoins are not
confirmed safe reserves. Named Treasury confirmations are private, dated, and
expire at documented maturity or the confirmed <=365-day upper bound. Never
infer Treasury status from the generic Bonds category.

Current portfolio treatment: owned US Treasuries participate as assets. An
identified ETF uses its own adjusted USD history. A confirmed individual Treasury
with <=1 year remaining uses a disclosed SHV (0-1 year Treasury) total-return
proxy when a full individual-security history is unavailable. The exact-position
mapping has `valid_from`/`valid_until` dates and must be refreshed after its
confirmed maturity bound. Invalid/expired mappings are not applied and remain
visible as limitations. No generic Bonds override is used.

Maturity/duration exposures remain distinct: short bills are not replaced with
TLT (20+ year Treasury), intermediate notes, high yield or a generic bond series.
Direct ETFs keep their own tickers and covariance histories; grouping only
combines identical instruments/histories. SHV represents a rolling ETF sleeve,
not the precise duration, coupon, costs or hold-to-maturity payoff of the owned
bond. Short Treasuries can contribute little to DR-squared because their
volatility is small, even when their capital allocation is large. Inclusion never
means adding an automatic +1. The optional reserve role is retained for reading
earlier saved configurations; the current confirmed holding is mapped as an asset.

The headline is N equivalents / reference 15–20, rounded to one decimal (below
15 must not round up to 15). Proxy/default/illiquidity omissions, cached balances,
coverage, model notes, history date and sample length remain visible. A count
above the number of exposures is hedge-driven, not a literal business count.
All Cash/reserves yields not-applicable, never an achieved-diversification claim.
Old blocks remain readable as prior models; malformed new blocks never fall
back to old scores. Frozen fingerprints do not consult today's configuration.

Adding v2 to a historical snapshot preserves originals/latest pointers and financial fields:

```bash
just holy-grail --snapshot SOURCE --output NEW_DERIVED_PATH --config PRIVATE_CONFIG --offline
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --year 2026 --quarter 3 --after NEW_DERIVED_PATH
just holy-grail-sheet --snapshot NEW_DERIVED_PATH --spreadsheet-id ID --sheet-id GID --dry-run
just holy-grail-sheet --snapshot NEW_DERIVED_PATH --spreadsheet-id ID --sheet-id GID --apply
```

The sheet command verifies the snapshot date against the selected tab title,
backs up the bounded grid, checks for concurrent changes, and only edits
A10:B14 and owned marker-based Details. It never deletes/recreates worksheets
or rows. It refuses insufficient grid space and conflicts. Repeated writes
replace only owned groups; foreign data/groups keep Details expanded. On write
errors it reads back before any retry. Values, number format, groups and
outside-scope state must match before delivery is reported verified.

Ungrouped Details require an explicit `Holy Grail - End` boundary. Populated
legacy sections without a group/end marker are refused rather than claimed as
owned. Readback verifies final row visibility as well as group metadata.
Unavailable new results retain the indicator layout and replace stale counts.

## Capital diversification v2

`capital_diversification_v2` is the base method calculated for every new snapshot
(the optional v3 record below is derived from it, never a replacement of it).
An `allocation` object enables it, and omitting `method_version` selects v2.
Without the object, diversification enrichment is disabled. An explicit v1 or
unknown method is unavailable; a present but invalid v2 result never falls
back to v1. v2 displays integer points out of 100, not a percentage. Cash is
excluded from invested weights and shown separately as a share of full NAV.

v2 is a group-level asset-class breadth metric: it rewards spreading invested
capital across uncorrelated economic groups and across the eleven equity
sectors. It does not see issuer-level or thesis-level concentration by
construction - two issuers in the same group score exactly as their combined
weight. That verdict therefore needs safeguards beside the score, not inside
it; see the concentration block below. The historical 15-20 independent
economic streams target stays an aspiration, not a reached state, and is not
mixed into v2 trends.

The model aggregates dated holdings into canonical economic groups, retaining
unknown invested amounts in the denominator. For weights `p` and correlations
`rho`, the similarity matrix has diagonal 1 and off-diagonal
`max(0, rho)**2`. Let `N = 1/(p.T @ Z @ p)` and `T = clip((N-1)/5,0,1)`.
With total equity weight `E` and global eleven-sector breadth `b`, the score is
`100*T + 25*min(E*b, 1-T)`. Six equally weighted uncorrelated groups anchor
100. The score is not portfolio variance, a return forecast, a protection
probability or an official Dalio rating. Unknown equity-sector capital is
assigned to the largest known sector; no known sectors gives zero breadth.

The main scenario uses 60 completed monthly USD return observations and a
business correlation assumption of 0.25. The other tests use 0.75 and a
complete 36-month window. Missing pairs are conservatively assigned correlation
1; a separate recalculation using zero bounds their model effect. Unknown
invested weight above 5%, or a missing-pair effect above five points, makes the
scenario unavailable. Alternative scenarios do not replace an unavailable main
result. Category changes across available scenarios are reported as dependence
on assumptions or period, and the range is not a confidence interval.

Because breadth is grouped, the score can rise while a named holding weight
grows: measured on the frozen Q3 inputs, 52.35 -> 59.60 -> 63.48 as the China
equity share goes 0 -> 19.5% -> 50% at a measured near-average China
correlation of about 0.185. This is by design, and the concentration limits
below, not the headline number, govern that verdict.

Saved inputs include dated profiles, source histories, method and group
representatives, evidence-review cutoff and fingerprints. Replay rebuilds
holdings, scenarios and reviewed risk facts from saved inputs, without fetching
market data. Previous-v2 attribution separates market-relationship and
position/profile changes using unrounded values; a missing or incompatible
previous basis leaves the current result usable. Prior source fingerprints are
references whose original files are not independently verified during replay.
The main result remains provisional when balance or sector evidence is partial.
Public output contains only whitelisted group and risk summaries, never private
holdings, source confirmations or account identifiers.

### Concentration safeguards beside the score

`DIVERSIFICATION_DATA.concentration_v1` adds the issuer and thesis verdict the
score cannot see; the block keeps its historical save key and the recorded
`version` field (concentration_v2) gates the contract. Limits come from private
`allocation.concentration_limits` on stricter defaults (largest issuer <=5% of
equities and <=2% of NAV, top-4 <=20% of equities, broad-market core >=50%,
China <=10%, named thesis clusters <=10%); cluster membership from
`allocation.linked_theses`. Every issuer above a limit records its own breach
with the subject in the key - `issuer_pct_equities:<issuer>` and
`issuer_pct_nav:<issuer>` (theses keep `thesis_pct_equities:<name>`) - so the
block names every concentrated holding, not only the largest one.
`largest_issuer` and `top4_issuers` remain plain facts beside an
`issuers_over_limit` list carrying id and both shares for each over-limit
issuer, any issuer-keyed breach raises `issuer_limit_breached`, and rendered
rows carry an issuer's two denominators under one row. The limits, theses,
decisions and decision-settings keys stay frozen into the saved configuration
fingerprint, so replay uses the same input on every read.

Recorded `allocation.concentration_decisions` entries shaped
`{id: {limit, subject (optional), decision: accept|reduce|exit, reason,
decided_at, review_by, max_value (optional), min_value (core floor)}}` resolve
a breach only through subject binding: a record with `subject` acts on the
exact `limit:subject` breach key, a legacy record without one only on the
exact full breach key - old fully-qualified thesis records keep their verdict,
a bare `issuer_pct_equities` key can never match a prefixed issuer breach. The
record acts while `decided_at` is on or before the block's as-of date, that
date is on or before `review_by`, `review_by - decided_at` stays within
`max_review_days` (constant 120; private
`allocation.concentration_decision_settings` = `{'max_review_days': N}` may
override it, and anything but a finite positive override fails the
configuration), and the current value still fits the recorded bound: at most
`max_value`, at least `min_value` for the core floor. A position that grows
past its accepted bound expires its own resolution and needs a fresh record.
An incomplete or out-of-horizon record is invalid: it resolves nothing, its id
appears as an `invalid_decision_record:<id>` warning (deduped, sorted, first
three), one bad record never takes the block down - the breach stays
unresolved, the summary counts it, and unresolved ones lead the rendered rows.

Broad index funds declare dated `holdings` in their profile - the declared
issuers and each one's share of the fund, `coverage`, and
`max_other_issuer_share` (no larger than the smallest listed share) as the
upper bound on any unlisted issuer's share - so the underlying companies are
measured instead of charging a whole index fund to one issuer, and an exposure
held directly and through a fund lands on one issuer instead of two. The
uncovered fraction goes to the `unknown_lookthrough_pct_equities` fact, never
spread over members. Holdings undated or older than 90 days are unverified:
the fund falls back to a single ticker issuer and keeps the
`unknown_issuer_lookthrough` warning. On a fresh list the unlisted tail warns
only where `max_other_issuer_share` times the fund's equity share could still
clear the issuer limit; incomplete coverage by itself is not a warning.
A profile may also assert `core: true`, which counts the position into the
broad-market core bucket (the >=50% line). A diversified holding company with
a declared, fresh look-through (Berkshire via its SEC 13F quarterly filing)
qualifies as core and its own ticker stops being an issuer for the per-issuer
limits; the look-through window is the same 90 days, and stale or missing
declared holdings degrade the position back to a plain ticker issuer with a
warning while the core credit stays - so `core: true` is only switched on
together with fresh declared holdings.

A stock-category position without a profile is not dropped from the facts: in
the equity buckets the extraction emits (`Stocks`, `China Stocks` - a second
stock bucket beside `Stocks`, also holding ETFs - and `REIT`, included as a
conservative, revertable owner call) it counts as one issuer at its ticker on
its full equity value, in both the equities numerator and the denominator; a
new profileless stock is exactly the concentrated bet the safeguards must
catch first. It gets no thesis membership, core credit, country or
look-through, the counted share surfaces as the `unprofiled_pct_equities`
fact, and an `unprofiled_positions` warning names the ids (first three).
Unprofiled positions in the non-equity categories (`Bonds`, `Precious
Metals`, `Commodities`, `Short Selling`) only raise the same warning and never
gain invented issuer facts.

The safeguards render beside the headline score as rows or bullets, never as
a second big number - including when the v2 score is unavailable or not
applicable - and the summary counts all breaches and names the unresolved
ones. The section hides only when the record carries no readable block (no
block saved, a malformed one, or a saved block under an earlier contract
version): the contract version is bumped to `concentration_v2`, saved
`concentration_v1`-versioned blocks from before the bump degrade silently -
they render exactly like records without the block, are never re-read under
the new semantics and are never re-derived from current config, while the key
itself stays `concentration_v1`. A same-version block that fails independent
replay degrades to a single unavailable row instead of showing its verdicts,
and the offline what-if runs its before/after states through the same
subject-bound eligibility - its per-issuer view lists every issuer over a
limit with both denominators, breach flags and decision state, and a missing
or old-version block reads as absent there too.

### Offline what-if scenarios

The enrichment CLI accepts repeatable `--what-if ID=+USD` deltas and prints a
before/after comparison without changing anything:

```bash
just holy-grail --what-if ib:VOO=+20000 --offline
just holy-grail --what-if ib:9988=-5000 --what-if ib:GOOG=+5000 --offline
```

Each delta moves one position and is funded from Cash (the net total returns
to it); the run works on a temporary copy of the newest saved snapshot, or of
the explicitly passed `--snapshot`, re-runs the same offline enrichment on
that copy, and prints per-limit value, breach and decision state plus the v2
score for both states. It writes no files, fetches no data and places no
orders. Unknown or unprofiled ids exit with status 2 before any mutation, and
missing offline history degrades the after state to unavailable.

## Capital diversification v3 (car-category pairs)

`capital_diversification_v3` is the v2 formula with one change: the
`car_business` pairs are no longer the fixed 0.25 assumption but come from a
public category index. v2 stays sealed, is still calculated for every snapshot
and remains the source record; v3 is a sibling record
`DIVERSIFICATION_DATA.allocation_score_v3` derived from the saved v2 record plus
a frozen `car_category_v2` block. Weights, sectors, all non-car pair
correlations and the 0.75 stress scenario are copied from v2. `concentration_v1`
and the offline what-if stay on v2 and are not migrated. No block supplied
means no v3 record.

**What the car pairs are.** The Manheim Used Vehicle Value Index (US wholesale
prices, seasonally adjusted, monthly since 1997) is a public proxy for the price
of the inventory of "buy damaged, repair, resell". For each group the pair is
`R * rho(index, group)` with the index loading fixed at `R = 1`. `R = 1` is a
conditional scenario assumption: the business inherits the standardized index's
price channel (and its residual is uncorrelated with the group). It is not a
bound on the business. Deal-level noise would lower the loading, which can be
calibrated only from the owner's own dated deals (`docs/car-deal-ledger.md`),
while financing, liquidity, repair, FX, customs, tax and war channels are not in
the index and are not bounded. The pair kind is `category`: it is a category
proxy, never a measurement of the business, and it never infers business
returns from carrying values or the past resale.

**Measures per group** (all on the frozen block). These are three different
quantities with different samples, not repeated measurements of one: the
same-window monthly correlation; the group against the index one month later
(price lags); and the correlation inside the worst-quintile months of US
equities over the full index history since 1997 (at least 20 months), whose
sample ignores the window. `cat_point` is `R` times the largest of the three.
`cat_upper90` is `R` times the largest of the three per-measure Fisher upper
endpoints (z = 1.645, a nominal two-sided 90% or one-sided 95% endpoint for each
single estimate). The two envelopes are chosen separately, so the upper endpoint
can come from a different measure and sample than the point; the saved measures
keep `selected`/`n` and `upper_selected`/`upper_n`, and each category pair keeps
its `sample`. The endpoint is not a block bootstrap: it ignores serial
dependence, overlapping months and the selection of the maximum, and ten groups
are taken at once. It is therefore neither a calibrated confidence interval for
the portfolio score nor a bound on the business, and the spread between
scenarios is a sensitivity range, not an interval. A group with no usable
measure gets a missing pair, r = 1, and the v2 rule that a missing-pair effect
above five points makes the scenario unavailable.

**Scenarios.** `m60`/`m36` x `cat_point`, `cat_upper90`, and `r075` (the v2
assumption, unchanged). The headline is `m60_cat_point`
(`HEADLINE` in `analytics/holy_grail/allocation_score_v3.py`, a judgment call: the wider
`cat_upper90` and the stress stay visible in the scenario spread).

**Gates.** The block must carry a matching fingerprint and method, a cutoff that
is the completed month of `as_of_date` or the month before it (Manheim publishes
about a week into the next month; the lag is flagged `category_index_lagged`),
never later (no look-ahead), finite month-end series (the index series ending
exactly at the cutoff, no series beyond it), and at least 120 index returns. A rejected or stale block yields an explicit
`unavailable` v3 record (`invalid_car_category_block`) and the view then shows the
v2 assumption numbers labelled as assumptions (the tab's conclusion cell ends with
`Припущення v2: блок категорії авто недоступний`); a present v3 record that fails
replay renders as unavailable and never falls back to v2 or v1. Replay
recomputes everything offline from the saved v2 record and the embedded block.

**Regression.** With constant pairs 0.25 and 0.75 the v3 pair substitution
reproduces the saved v2 scenario scores to 1e-8. The price-channel group
correlations with the index are weak in the data checked so far (below 0.30 at
the selected measure), so for this channel the 0.25 base is consistent with
public data while 0.75 is far above anything it shows. The block method is
`car_category_v2`; a `car_category_v1` block is rejected as invalid. Concrete
scores of a real snapshot belong in the ignored `data/`, not here.

**Limits.** One index, one channel; `R` unknown; the 60-month window holds
essentially one rate-shock regime; 2008-era coverage is missing for China,
emerging markets, crypto and EUR high yield; Manheim history is revised (raw file
sha256 is recorded) and Cox is an interested party; the stress measure uses the
same long-history sample in the 60 and 36-month scenarios, so the window
sensitivity of the category scenarios is understated; US and EU data say nothing
about Ukrainian customs, VAT, FX or war channels. The refresh is monthly, not
quarterly: a block is accepted only while its last month is at most one month
behind the completed month of the snapshot (`max_index_lag_months` in
`analytics/holy_grail/car/category.py`), so a block ending in September serves snapshots
through 29 November and is rejected from 30 November. Rebuild the block each
month after Manheim publishes (about a week into the next month; `just
car-category build ...`), copy it to `data/car_category/block_latest.json`, then
run the normal pipeline. A stale block gives the explicit `unavailable` v3
record and the v2 assumption numbers with a warning (see Gates above).

## Risk progress v3 (`risk_progress_v3`)

The headline for new snapshots: one score from 0 to 100 for an individual,
non-accredited, long-only investor (no shorts, no leverage, no hedge-fund
strategies). It keeps the Holy Grail idea and the formula of
`risk_progress_v2`, but it sets the target at what such an investor can reach
with effort, and it counts the assets held outside the broker. The record is a
sibling derived from the same saved, replayed `capital_diversification_v2`
record and frozen car proxy block (`analytics/holy_grail/risk_progress_v3.py`),
saved as `DIVERSIFICATION_DATA.risk_progress_v3`. `risk_progress_v2` (100 = 15
streams, invested assets only) is still derived and shown in the details.

**Goal (owner decision, 2026-11-07).** What this score aims for; check later
changes against it:

- Useful to an individual, non-accredited investor with up to about $1M in the
  US and Ukraine: 100 is reachable with effort, but not trivial. A simple
  liquid portfolio stays well below it.
- Long only: no shorts, no leverage, no hedge-fund strategies.
- Close to the Holy Grail idea: many independent return streams, scored with
  the v2 formula, with the target at 7 streams instead of 15.
- Assets held outside the broker count. Property, land, Ukrainian government
  bonds and deposits, and P2P loans are modeled from public parameters.
  Infrastructure, private equity, private credit and timber count through
  listed stand-ins.
- Location counts. Each private asset has a country and, optionally, a city.
  The model treats assets in one city as more closely linked than assets in
  different cities or countries. Countries beyond the US and Ukraine are
  supported, so a model portfolio can diversify globally.
- Simple: obscure classes (carbon, collectibles, royalties and similar) are
  left out, and a primary residence is excluded.

```
DR = sum(w_i * sigma_i) / sqrt(wᵀ Σ w)      N_effective = DR²
score = clip(100 * (1 - 1/DR) / (1 - 1/sqrt(7)), 0, 100)
```

| streams | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| points | 0 | 47 | 68 | 80 | 89 | 95 | 100 |

The display rules are those of v2: 100 only at 7.0 equivalent streams or more;
otherwise the headline is capped at 99 and the detail at 99.9.

**Why 7.** In 2026-11 research, long-only portfolios reached about 2.5-3.2
effective streams out of sample with liquid assets, and about 5 with private
assets under central literature assumptions, so 15 streams was out of reach and
the score did not guide decisions. With 7, the extended individual menu below
reaches 100 at its best weights, while a typical liquid portfolio stays near 60.

**Universe and weights.** The invested part of the v2 record plus the declared
private streams. Capital weights are value over that universe, applied to the
whole window like v2. Cash stays outside, except deposits declared from Cash
(see below). Balances and totals are never changed.

**Streams.**

- Measured: a v2 group (its representative history), the car business (the
  CPRT/KMX/OPLN basket of the frozen block, as in v2), and listed proxy baskets
  for private classes an individual reaches through public vehicles
  (equal-weight monthly returns, all names required):
  `infrastructure` BIP+BEP, `private_equity` BN+KKR, `private_credit_funds`
  BIZD, `timberland` WOOD. Proxy streams carry listed-equity beta, so they earn
  little diversification credit: that is the honest measurement of the proxy,
  not of the asset.
- Modeled private streams, one per (class, country, location):

  ```
  r = βᵀF + σ_res * (sqrt(s_c) g_country + sqrt(s_k) h_class,country + sqrt(s_l) k_location)
  ```

  `F` are the `equity_us` (SPY), `treasury_medium` (IEF) and `commodities`
  (DBC) representatives, plus `EURUSD=X` only for rows that declare
  `corr_fx_eur` (EUR beta 0 otherwise). `β` follows from the row's correlations
  with `F` and its central volatility (`β = Σ_F⁻¹ (σ_F ⊙ ρ) vol`, with `ρ`
  scaled down when it would explain more than 95% of the variance), and
  `σ_res² = vol² - βᵀ Σ_F β`. `g`, `h` and `k` are independent unit factors with
  residual-variance shares `s_c + s_k + s_l = 1`. There is no idiosyncratic
  term, so splitting one holding into several entries never adds a stream. The
  same location across classes shares `k`; different cities of one country share
  `g` and `h`; countries are linked only through `F` (and the UA link). US and
  `other` rows have no country factor; without a location (or with
  `diversified`) `s_l` folds into `s_k`. Locations are compared after collapsing
  whitespace and case.
- UA link: the Ukrainian country factor is tied to the measured Ukrainian
  streams (the car business, only with a reviewed `business_geography` of
  Ukraine, and Ukrainian proxy holdings):
  `g_UA = ρ e/σ_e + sqrt(1-ρ²) u_UA`, where `e` is their value-weighted
  residual against the other measured columns and `ρ = car_link_rho`. With the
  car business's geography unreviewed, the link applies in the adverse scenario
  only, with a warning.

**Covariance.** The measured columns (the v2 groups, the car basket, the proxy
baskets and the factors) are shrunk jointly with the v2 Ledoit-Wolf estimator.
`Σ = A blockdiag(Σ_shrunk, I) Aᵀ`, which is positive semidefinite by
construction. With no private streams declared, `A` only selects the v2 groups,
and DR equals the `risk_progress_v2` DR exactly.

**Scenarios.** The central parameters give the headline. Favorable uses the low
values of every correlation, residual-share triplet and `car_link_rho`; adverse
uses the high values. A separate ×0.5/×2 sensitivity scales the private
volatilities (DR is not monotone in volatility). Neither is a confidence
interval. "Внесок приватних потоків" is sequential on the same window and block:
the v2 groups alone (reclassified positions put back), then plus the modeled
streams, then plus the proxies (the headline). Its starting point can differ
slightly from the score without private streams, because the factor and proxy
columns change the joint shrinkage.

**Parameters.** `analytics/models/private_streams_v1.json` holds public
literature and index values only, with sources and an access note for a
non-accredited investor for every row. Its fingerprint is part of the method,
and the parameters a record used are embedded in it. Changing any value needs a
new file and method version, and the boundary shows "Змінено методику". Rows
(class:country):

- `residential_re` US, UA, PL, DE, ES, PT, AE, GE
- `commercial_re` US, UA, DE, ES, PL
- `farmland` US, UA
- `development_land` US, UA
- `ovdp_deposits_uah` UA (the only row that may come from Cash)
- `ua_sovereign_usd` UA (USD OVDP and Eurobonds)
- `p2p_loans` US, UA, other

USD cash, including USD deposits in Ukrainian banks, stays cash. Polish
farmland is left out because only farmers may buy it.

**Private declaration** (`data/holy_grail_config.json -> private_streams`,
frozen inside the v2 configuration; keys only here):

- `entries[]`:
  - required: `id`, `class`, `country`, `value_usd`, `valuation_as_of`
  - optional: `location`, `currency`, `debt_usd`, `nav_source` (`outside` or
    `cash`), `held_from`, `valuation_source`, `reviewed_at`,
    `primary_residence`
- `reclassify`: `{position_id: {class, country, location?, source_identity?}}`
  moves an itemized v2 position out of its group (for example P2P out of the
  HYG proxy, or Ukrainian Eurobonds held at a broker). A positional id
  (`p2p:i`) needs the position's `source_identity`.

Rules:

- A primary residence is excluded and counted.
- `debt_usd > 0` gives unavailable (`unsupported_leverage`).
- `held_from` after the snapshot excludes the entry.
- `nav_source: cash` is allowed only on cash-eligible rows, and their sum must
  not exceed the v2 Cash (`cash_entries_exceed_cash`).
- A valuation older than 12 months makes the record provisional.
- An unknown key, class or country, or a bad reclassification, gives
  unavailable (`invalid_private_streams`, `class_not_in_model`,
  `invalid_reclassify`). Nothing is dropped silently.
- A declared class without a usable series gives unavailable (`no_history`);
  the factor and proxy histories are collected with the v2 histories only when
  private streams are declared.

**Calibration (public data, the 60 months to 2026-10; parameters frozen by
sha256 before any score was read, never tuned).** The reference portfolios:

- R1: 60/40 SPY/IEF.
- R2: 8 liquid assets at equal weight.
- R3: 12 liquid groups at equal risk.
- R4: an individual reference at equal risk (property at least 6%, every other
  stream at least 2%, every stream at most 25%). Liquid core; US rental in one
  metro; UA apartment, commercial premises and farmland in three locations;
  USD OVDP; P2P; infrastructure proxy; car basket.
- R5: R4 with all UA privates in one city.
- R6: R4 without US property.
- R7: the UBS 2026 US family-office average.
- R8: R4 plus residential property in PL, ES and AE (one Iberian country only).

| portfolio | points | streams |
|---|---|---|
| R1 | 15.0 | 1.22 |
| R2 | 59.6 | 2.53 |
| R3 | 59.4 | 2.51 |
| R4 | 83.6 (adverse 66.2, favorable 100) | 4.34 |
| R5 | 80.8 | 4.04 |
| R6 | 80.5 | 4.01 |
| R7 | 34.8 | 1.63 |
| R8 | 87.4 (adverse 68.2, favorable 100) | 4.80 |

Bands:

- The fixed bands for R0, R1, R2, R3, R6 and R7 hold, and so does the
  revision's band R8 >= R4.
- Two bands of the first calibration failed: R4 >= 85 and a one-city penalty of
  at least 5. The owner kept the target of 7 and accepted both values as
  landmarks.

Best long-only weights with a 25% cap (information only): the reference menu
reaches 89.7. A 30-stream individual menu reaches 100 (7.1 streams, adverse
77.7), and adding global property reaches 100 (8.2 streams, adverse 80.2).

**Coverage of a 120-item asset list.**

| Treatment | Items |
|---|---|
| Measured v2 groups | equities of any style, region, sector or size; listed REITs, infrastructure companies, PE managers and BDCs held as stocks; bonds, bills and money-market funds; metals and commodities; crypto |
| Modeled private streams | residential and commercial property (fractional and non-traded REITs as their class with location `diversified`), farmland, development land, UAH deposits and OVDP, USD OVDP and Ukrainian Eurobonds, P2P loans |
| Measured listed proxies | infrastructure; private equity, venture and pre-IPO; retail private credit funds; timberland |
| Out of scope | cash, US bank deposits, repos and stablecoins; strategies and contracts (no shorts, leverage or hedge-fund strategies) |
| Not in this version (`class_not_in_model`) | collectibles, royalties and IP, litigation finance, cat bonds, carbon, shipping leasing, operating agricultural businesses, own business other than the car business, tokenized RWAs, NFTs |

**Limits.**

- Ukrainian parameters under war conditions rest on thin data (asking prices
  since 2021, judgement for commercial property, P2P, Eurobond correlations and
  `car_link_rho`), so the scenario range is wide.
- `residential_re:GE`, `commercial_re:PL` and `residential_re:AE` rest on thin
  or judgemental series.
- ES and PT residuals share a cycle that the independent country factors do
  not see.
- Declared values are appraisals.
- The 60-month window is one regime.

The score is a modelled effect of diversification under a product scale. It is
not a grade, a forecast or a measurement of any property or business.

## Risk progress v2 (`risk_progress_v2`)

The headline for snapshots saved before `risk_progress_v3` (and a detail row after it): one score from 0 to 100 for the whole invested
part of the portfolio, answering how much of the modelled diversification effect
behind the Holy Grail idea the current mix shows. It is a sibling derived from a
saved, replayed `capital_diversification_v2` record and a frozen car proxy block
(`analytics/holy_grail/risk_progress.py`), saved as
`DIVERSIFICATION_DATA.risk_progress_v2`. v2 and v3 stay calculated and are
shown in the details. Cash is outside the score and shown separately.

```
standalone = sum(w_i * sigma_i)          sigma_p = sqrt(wᵀ Σ w)
DR = standalone / sigma_p                N_effective = DR²
benefit = 1 - 1/DR                       target_benefit = 1 - 1/sqrt(15)
score = clip(100 * benefit / target_benefit, 0, 100)
```

`w_i` is the weight of group `i` in the invested part, `sigma_i` the standard
deviation of the monthly returns of its representative and `Σ` the shrunk
sample covariance of all groups on the same complete months (see "Covariance
estimate" below; `sigma_i` is the square root of its diagonal, which equals the
plain sample variance with ddof 1). The weights of the
current snapshot are applied to the whole window: the result is a conditional
estimate of the risk structure of today's portfolio on the history of its
representatives, not a reconstruction of past positions or returns. The base of
the comparison is the same assets with the same weights and volatilities at full
positive correlation; it is not the S&P 500, cash or the portfolio's actual risk
on some date. Monthly versus annual volatility units do not change DR.

**Covariance estimate.** With 15 or so groups and at most 60 monthly rows the
plain sample covariance is noisy, so `Σ` is estimated with the Ledoit-Wolf
(2003) shrinkage toward a constant-correlation target (Ledoit and Wolf,
"Improved estimation of the covariance matrix of stock returns with an
application to portfolio selection", Journal of Empirical Finance, 2003;
"Honey, I shrunk the sample covariance matrix", Journal of Portfolio
Management, 2004). The sample matrix `S` (moments divided by the number of
months `T`) is combined with `F`, which keeps every group's own variance and
gives every pair the average sample correlation `r`, as
`Σ = (δ F + (1 - δ) S) * T / (T - 1)`. The intensity `δ` in [0, 1] is the analytic Ledoit-Wolf value
`clip(κ / T, 0, 1)`, recomputed for each window and frame (the 60-month and
36-month windows, the volatility multipliers and the representative comparison
each re-estimate on their own sample); `δ = 0` when the target equals the
sample, and with fewer than two groups no shrinkage applies. The final factor
`T / (T - 1)` keeps the usual ddof-1 scale, so displayed volatilities keep their
meaning; DR does not depend on that common factor. The target keeps each
`sigma_i` and the result stays positive semidefinite. Shrinkage lowers the
estimation noise of correlations; it moves extreme pairs (including hedge-like
negative ones) toward the average, so it can raise or lower the score. It does
not remove model risk and is not a forecast. The window record stores the
target, the intensity and the average correlation, and replay recomputes them;
a change of the estimator changes the method fingerprint, so records saved with
an earlier estimator render as "Недоступно" until recalculated.

**Scale.** 100 means the effect of 15 equal-risk independent streams (about a
74.18% volatility reduction in that model). It is a product policy, not a
Dalio rating or an official scale, and not a promise of an 80% lower future
risk; the text never says the Holy Grail is "achieved". Anchors:

| Equivalent independent streams | Score |
|---:|---:|
| 1 | 0 |
| 2 | 39.484063 |
| 3 | 56.976152 |
| 6 | 79.772287 |
| 15 | 100 |

The anchors follow from the formula alone (`DR = sqrt(N)` for `N` equal-risk
independent streams) and do not depend on the covariance estimator.

`N_effective` is the number of identical independent streams with the same
modelled volatility effect, not a count of independent and profitable
businesses. Covariance alone does not prove statistical independence or
resilience in a crisis. A value above the number of groups is a hedge result
(`hedge_driven_count`). A higher score does not necessarily mean a lower
absolute volatility, so the annual modelled portfolio volatility
(`100 * sqrt(12) * sigma_p`) is stored and shown beside it; a score raised only
by changing the assumed volatility of the car business is not an investment
improvement.

**Inputs and window.** Every group with a positive invested weight is included;
weights must be finite, non-negative and sum to 1 (tolerance 1e-8). The main
window is the last 60 calendar months up to the last completed month; the
calendar index is built before gaps are dropped and older months are never
borrowed to replace missing ones. The covariance matrix is computed on the
common complete rows. 36-59 common observations make the result `provisional`,
fewer than 36 make it `unavailable`. Every main series and the last common
month must end no earlier than one month before the cutoff: a one-month lag is
`provisional` with a warning, a larger lag is `unavailable` even if enough older
months exist. A positive weight without a usable series (including `unknown`)
makes the score `unavailable`; the group is never dropped silently and the
remainder is never rescaled. A provisional parent v2 stays provisional: the
quality of the inputs is shown beside the model, never hidden by a long
history. The 36-month window is a diagnostic and never replaces the main one.

**Car business.** There is no return series for the business. The score uses the
monthly total return of the equal-weight basket CPRT, KMX and OPLN (all three
required, adjusted prices converted to USD, no forward fill) as a labelled
working assumption and an owner decision; it is not shown as a measurement of
the business, nor as conservative or a lower bound. The basket is collected
automatically in normal collection (existing price provider and cache) and
frozen in the block `car_proxies_v3`; offline recalculation accepts a
`car_proxies_v2` block. The score does not average the correlations of other
channels into the covariance matrix.

**Risk contribution.** For every positive group on the main window:
`risk_share_i = w_i (Σ w)_i / sigma_p²`, the Euler share of the modelled
portfolio volatility (equal to its share of the variance). It can be negative
for a hedge and is never clipped; the shares sum to 1 (tolerance 1e-8). It is
not a probability of loss, a share of a possible maximum loss or the full risk of
a private business. Short Treasuries can have a small share and still lower the
absolute volatility, so a small share does not make them useless.

**Details stored beside the score.**

- Worst modelled months of the available window: the six months with the lowest
  modelled portfolio return `wᵀ r_t` (ties: earlier date first), their mean and
  the mean contribution `w_i r_i,t` of every group over them. Six months are 10%
  of a 60-month window; with 36-59 observations the rule stays six and the
  result provisional. The score can rise when a crisis month leaves the window,
  with no decision of the investor. The 36-month window differs by market
  history, not by portfolio.
- Car-business write-off: `weight_pct_nav x {0.5, 1.0}` as arithmetic of a
  share of NAV, with the stated assumptions that all other assets are unchanged
  and extra liabilities, collateral losses and taxes are not counted. It is not
  a probability or forecast; business-failure statistics are not used. Not shown
  when the car weight is zero.
- Sensitivity to the volatility of the car series: the main series multiplied by
  0.5, 1.0 and 2.0 with all weights, other series and the common months of the
  main scenario unchanged; for each the series volatility, DR, score, car risk
  share and portfolio volatility. It scales the whole series and keeps its
  correlations, so it does not reproduce repair, liquidity or failure risk, and it
  does not change the headline.
- Sensitivity to the representative of the car business: the main basket
  replaced by Manheim, BLS used cars or AUTO1 on a common sample with the other
  groups, shown with the sample size. It is not a calibrated model of the
  business (a low-volatility price index does not mean a low-risk reseller) and
  is kept apart from the volatility sensitivity; the two are never merged into
  one "honest range" or a confidence interval of the true score. An incomplete
  comparison (a missing, stale or short auxiliary series) never changes or blocks
  the headline.
- The Ukrstat CPI stays in the proxy block as context; it mixes new and used
  vehicles and is not part of the headline or of the four-scenario comparison.
- A monthly change of a price ratio (for example the Ukrainian USD index over
  Manheim) is, at most, an experimental indicator of price conditions. It is not
  a margin, a return on invested capital or a business return, it is not in the
  covariance, and no synthetic business return is built from it.
- Qualitative environment map (reference only): for each group the growth and
  inflation environments in which that class is usually favoured in an All
  Weather style framework. It has no percentages, thresholds or sums of
  contributions, and the text never speaks of "protection". Bridgewater describes
  the reaction of assets to growth and inflation relative to expectations
  ([The All Weather Story](https://www.bridgewater.com/research-and-insights/the-all-weather-story));
  this map does not measure that reaction, only part of its cells follow the
  text and the rest is common practice or an owner decision. Measuring
  sensitivity to growth and inflation shocks needs measured data and is a later
  step.

**Statuses and gates.** `modeled`, `provisional`, `unavailable`,
`not_applicable` (no invested part). Unavailable and not-applicable records carry
null numbers, never 0. A missing basket, a corrupt block or a positive weight
without a series gives `unavailable`; the record is still written. A stale or
short auxiliary series only makes the comparison incomplete. The integrity of the
whole block (version, method, fingerprint, calendar, no future months) is judged
separately from the freshness of each series. Replay recomputes everything
offline from the saved v2 and the embedded block (floats with an absolute
tolerance of 1e-8, integers, strings and flags exactly); a record that does not
replay renders as "Недоступно" and never falls back to v3, v2 or
`risk_progress_v1`. A fingerprint proves the consistency of stored content, not
the correctness of the external source. A valid headline is not blocked by a
corrupt v3 or `risk_progress_v1` sibling, which is marked unavailable in its own
detail row.

**Unavailable by design.** A valid record whose status is `unavailable` (the
basket was not collected, a data outage, an offline run without a current
cache, or `just holy-grail` without `--car-proxies`) shows only the method, the
status with its reason, the date and the safeguard rows. No other number
appears in its place, the replayed `capital_diversification_v2` or v3 included,
so a collection failure blanks the diversification section until the next
successful run. This follows the no-fallback rule and is intended.

**Display.** The compact headline is an integer with an approximation sign:
`min(99, floor(score))` until the target of 15 streams is reached, then 100; the
details use one decimal rounded down, capped at 99.9 before the target. The
first summary row is the integer score as a number (formatted as "N зі 100" in
Sheets); the scale anchor and the equivalent-stream count are in the conclusion
note and the detail rows. The summary also shows the two largest
positive modelled risk contributions as "group: share of capital -> share of
risk", and the car-business assumption; then the data line (date, retrospective
flag, concrete quality reason) and cash outside the score. Model assumptions and
data quality are explained separately. A score is compared only inside the same
method; across methods the view says "Змінено методику" instead of a trend.
Concentration warnings (`concentration_v1`) stay visible and are not replaced by
the score.

**Limits.** The basket is not calibrated to the business; the 60-month window
holds essentially one rate-shock regime; one representative stands for each
group; vintages of revised indexes are known only where recorded, so a
historical recalculation is marked retrospective (the block-date rule is enforced on replay, but a
caller-asserted flag is an assertion that replay can neither prove nor disprove); the score says nothing about
expected return, quality of the holdings, liquidity or protection in every
environment. Covariance shrinkage reduces the estimation noise of 15 or so
groups on at most 60 months, not the model risk: the intensity is itself
estimated from the same short sample. A listed basket cannot see the private
business's own leverage and inventory financing, currency and country risk,
illiquidity or key-person risk; the write-off rows are only a coarse tail check.
The score counts any low-correlation stream, profitable or not, and no
return-quality layer is measured; sensitivity to growth and inflation surprises
is not measured either (the environment map is qualitative). Calibrating the car
series from the business's own monthly results is possible only once enough
months exist. Definition of DR and its reading as equivalent independent streams:
Choueifaty, Froidure and Reynier, "Properties of the most diversified
portfolio" (2013); the 0-100 transformation is this product's policy.

## Risk progress (`risk_progress_v1`)

A separate method that asks a different question from the capital score: how
many independent, equal-risk return streams does the current mix behave like.
It is a sibling derived from a saved, replayed `capital_diversification_v2`
record (`analytics/holy_grail/risk_progress.py`) and is never mixed into v2/v3
or `risk_progress_v2` trends. It is the older sibling, superseded as the headline
by `risk_progress_v2` and still readable in saved records and the details. It is saved beside v2 and v3 only when a frozen car proxy block is
supplied (`car_proxies`, see "Car-business scenarios"): the dated worksheet
then shows one extra summary row, "Ризиковий прогрес", after the scenario
spread and a paragraph in the conclusion note (when no `risk_progress_v2`
record is present; otherwise it appears in the details of the headline view).
Without a block nothing is saved and every view is unchanged. It revives the formula of the retired
`risk_equivalent_streams_v1` on a different basis (frozen v2 group histories
instead of position series).

```
DR = sum(w_i * sigma_i) / sqrt(wᵀΣw)      N_DR = DR²      volatility reduction = 100 * (1 - 1/DR)
progress = 100 * clip((N_DR - 1) / (15 - 1), 0, 1)
```

- Streams are the v2 groups that have a return history (one representative
  series each); weights are the v2 invested weights, used as they are (DR does
  not depend on a common scale). Σ is the sample covariance (ddof 1) of the
  monthly returns on the common months only; missing months are never filled
  with zeros. Raw Ledoit-Wolf is deliberately not used: on real data it
  inflated the volatility of the shortest Treasury group many times and made the
  count depend on duplicating a stream, which the sample covariance does not.
- Windows: 60 completed months (headline) and the latest 36 (comparison).
  `modeled` needs every month of the window up to the last completed month;
  36-59 common months are `provisional`; fewer than 36, a non-finite or
  non-positive-semidefinite covariance, or zero volatility is an explicit
  `unavailable` with a reason, never a number. A count above the number of
  streams is flagged `hedge_driven_count` (negative correlations can exceed
  the stream count).
- The scale is a policy choice: the target of 15 streams maps linearly to 100
  (15 equal-risk uncorrelated streams cut modeled volatility by 74.18%).
  It is not a percentage of risk. The display is rounded down to one decimal
  and reads 100.0 only when the target is reached. The CLI prints a
  25-stream reference only as a sensitivity, outside the saved record.
- Scope of the headline: only groups with a return history. `car_business` has
  none and is excluded and reported (share of invested capital and NAV); it is
  never replaced by a proxy in the headline, and appears only in the labeled
  scenarios below. Cash is outside the metric. The record carries
  `partial_scope_excluded_weight` while anything is excluded, so the headline
  describes the covered part of the invested capital, not the whole portfolio.
- What it does not say: it measures risk balance of today's weights over past
  months (a retrospective view of the current mix), not the quality of the
  holdings or an expected return after costs, and one ETF stands for each
  group. Equal risk across streams does not make the return attractive, so a
  high count is not an automatic "Holy Grail achieved".
- The record stores per-window counts, the diversification ratio, variance
  shares and annualized volatilities per group, coverage, the method and its
  fingerprint, and the identifiers of the v2 record it was derived from.
  `validate_saved_risk_progress_v1` replays the v2 record and recomputes the
  whole result from its frozen histories (and the embedded proxy block).

```bash
just risk-progress --snapshot data/snapshots/combined_data_<date>_<timestamp>.json [--car-proxies PATH] [--json] [--out NEW_FILE]
```

The command validates the saved v2 record by replay before showing a number,
changes no snapshot, fetches nothing and never writes Sheets. `--out` writes a
new file only, outside the automatic snapshot directories. `--car-proxies`
defaults to `data/car_category/proxies_latest.json` when that file exists.

### Car-business scenarios (`car_proxies`)

Public data cannot measure the owner's own business. A scenario answers a
narrower question: if the business behaved like this public series, would it
correlate with the rest of the portfolio, and how would the count change. The
answer is an assumption, shown as a range, never the headline.

- Proxies (`analytics/holy_grail/car/risk_proxies.py`): Manheim Used Vehicle Value Index
  (US wholesale), BLS CPI used cars and trucks, seasonally adjusted (US retail),
  AUTO1 Group Price Index (EU wholesale; read from a web page, medium
  confidence) and the equal-weight total return of CPRT, KMX and OPLN (listed
  remarketers, priced like equities; all three names are required, other CSV
  columns are ignored, and a CSV missing a name leaves the proxy out as
  `missing_basket_names`; the names are part of the block method). A Eurostat
  France series was dropped: it ends in 2025 and is smoothed.
- Block `car_proxies_v2` adds the Ukrstat national CPI "Купівля транспортних
  засобів" (COICOP 07.1, index to the previous month, SDMX dataflow
  `DF_PRICE_CHANGE_CONSUMER_GOODS_SERVICE`; the car sub-items have codes but no
  published national data), converted to USD as
  `index / 100 x rate(t-1) / rate(t) - 1` with the NBU monthly mean of the
  official daily UAH per USD rates. It mixes new and used vehicles bought by
  households (medium confidence). `just car-proxies fetch-ukraine --raw DIR
  --as-of DATE` downloads both raw files into the raw directory (network, never
  overwrites); without them the series is left out of the block as
  `source_unreadable`. `car_proxies_v1` blocks embedded in saved records still
  validate.
- Frozen block: `just car-proxies build --raw DIR --proxy-csv CSV --as-of DATE
  --out data/car_category/proxies_<date>.json` converts each series to monthly
  simple returns, trims it to the last completed month before the snapshot
  date, keeps the latest 120 months and records the SHA-256 of every raw file.
  It runs offline and refuses to overwrite. `validate_block` rejects a changed
  value, method or series name, data after the cutoff (look-ahead), a series
  more than one month stale and fewer than 36 months. Copy the block to
  `data/car_category/proxies_latest.json` for `just run` (or pass
  `--car-proxies PATH` to `just holy-grail`); the folder is git-ignored.
  Rebuild the block monthly, after the series publish: every series must end
  within one month of the completed month of the snapshot, so a block whose
  oldest series ends in September serves snapshots through 29 November; from
  30 November the record keeps the headline and shows the scenarios as
  unavailable (`invalid_car_proxies_block`).
- Scenario: the car business is added as one more stream carrying the proxy's
  returns at its unchanged v2 weight, with the same common-month rule on the
  60-month window. Each scenario reports the count, the points, the change of
  the count against the covered part on the same months as the scenario (a
  proxy shorter than the headline sample is compared with the covered-only
  count on its own months, `baseline_streams`, so a change of sample is not
  read as an effect), the correlation of the proxy with the
  covered portfolio return and with US equities, its annual volatility, a
  relation class by absolute correlation with the covered portfolio (below
  0.25 not correlated, 0.25 to below 0.75 moderately, 0.75 and above
  correlated) and the effect (adds or reduces diversification).
- Reading the range: price indexes move far less than a leveraged inventory
  business and barely correlate with the other groups, so they raise the count;
  the listed basket moves like equities and lowers it. The range is wide on
  purpose. Which one is closer to the real business needs the owner's own
  monthly history (not available).
- The record embeds a copy of the block. An invalid or missing block makes only
  the scenarios unavailable (`invalid_car_proxies_block`); the headline stays.
  The same kind of block feeds `risk_progress_v2` (offline as `car_proxies_v2`;
  normal collection builds `car_proxies_v3` with the basket collected
  automatically and these series imported as auxiliary, see "Risk progress v2").
- Worksheet row: `<points> зі 100 · <count> з 15 потоків · покрито <share> ·
  з автобізнесом <low>-<high> (припущення)`. The count is rounded down to one
  decimal like the points. A record that does not replay shows "Недоступно" and
  no number.
