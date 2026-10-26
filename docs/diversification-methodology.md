# Portfolio diversification indicators

## Capital-weighted score (current main indicator)

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

Frozen calibration in `analytics/models/capital_diversification_v1.json` uses
October 2021 through September 2026 and the agreed six equal blocks: US equities;
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
The default calibration and public profiles are shipped; `allocation.profiles`
contains exact dated private confirmations (e.g. the individual Treasury and
identity-bound Car Resale). Unknown instruments require explicit profiles;
regional exposure is not inferred from currency, listing venue or broker bucket.
Historical replay adds this block while preserving older saved analytics.
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

The current v2 Sheets builder reserves A10:B14 for the shared summary. When
benchmark rows would overlap, it places the intact performance panel below the
summary. Details start below every populated panel, so their row group cannot
hide unrelated holdings or income. Typed allocation_score cells use 0% formatting.
The standalone historical writer uses the same saved view and checks the
snapshot envelope date against the indicator before authentication or writing.


Current headline: the independent `DIVERSIFICATION_DATA.indicator` described in
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

`diversification_policy_v1` defaults below are editable private policy inputs,
not Dalio's thresholds or the user's personal loss limits.

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
inventory/cost/proceeds/turnover records. HYG and used-car CPI are weak sensitivity
proxies until substantive fit is established; defaults, redemption, depeg and
Ukraine operating risks remain omitted. Do not manufacture residual returns.
Actual listing currency, quote units and historical FX are handled by the
existing shared collector; do not add dividends again to adjusted histories.

New `DIVERSIFICATION_DATA` saves count/policy versions, score bounds, ten checks,
confidence, coverage/reserves, scenarios, dates, qualifications and input/config/
history/policy fingerprints. The pipeline calculates before persistence and
reuses one bounded history collection. Both outputs only render saved data.
Invalid or mismatched new blocks withhold results. Never reuse a changed-input
score. Private data/evidence remain ignored; public views whitelist generic
labels, percentages and counts. No trades or automatic reallocation are included.

Historical enrichment uses `just holy-grail --snapshot ... --output ... --offline`
and an explicit HTML `--after` path. Originals/latest pointers remain unchanged.
Exclude post-period observations and current holdings. Revised retrieved series
are retrospective; observation dates do not imply publication-date availability.


## Simple Holy Grail indicator (v1)

`DIVERSIFICATION_DATA.indicator` is the primary risk-equivalent count. It is
independent of the old ten-check score. The pipeline reuses the same collected
monthly USD histories; reports and Sheets only render the frozen saved block.
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

Historical replay preserves originals/latest pointers and financial fields:

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
