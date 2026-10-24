# Diversification quality and risk-equivalent streams

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

Cash adds no streams. Only documented USD cash without unsecured dependencies
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
