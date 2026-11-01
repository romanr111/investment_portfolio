# Car deal ledger (phase 2 input)

One local CSV, `data/car_deals.csv` (git-ignored like every `data/` file).
One row per deal. Log **open deals at purchase** (dropping unsold cars would
hide the bad outcomes); set `sale_date` when the car leaves.

Goal: once the closed-deal count reaches about **15–20**, the car-business
correlation tracker (`analytics/car_category.py`) can be calibrated: the share of
the category price index that your own deals actually capture (R in
`rho(business, group) = R * rho(index, group)`), which is fixed at 1 until then. Back-
filling deals from memory without dates adds noise, not data — log as they
happen. The single past resale may be entered, but it is one point.

## Columns

| Field | Unit | Why |
| --- | --- | --- |
| `deal_id` | text | Key. |
| `vehicle_class` | ICE / hybrid / EV | Tax regimes differ, notably EV VAT from 2026. Keep regimes apart. |
| `purchase_date` | ISO date | Starts the holding period for driver changes. |
| `sale_date` | ISO date, blank while open | Ends it. |
| `purchase_price_usd` | USD | Cost base. |
| `auction_fees_usd` | USD | All-in landed cost, split so a cost shock can be attributed. |
| `freight_usd` | USD | Freight leg. |
| `customs_taxes_usd` | USD | Customs and taxes leg. |
| `repair_usd` | USD | Repair leg. |
| `other_costs_usd` | USD | Rest of the cost. |
| `sale_price_usd` | USD | Proceeds. |
| `sale_currency` | text | Separates a price move from an FX move. |
| `fx_uah_per_usd_at_sale` | rate | Blank if paid in USD. |
| `damage_class` | light / medium / heavy | The main source of deal-specific noise. |

Derived, never stored: all-in cost, `margin_pct = (sale − all-in cost) / all-in cost`, holding days.

Phase 2 estimator (blocked until ~15 closed deals): regress `margin_pct` on
the category price-index change between each deal's purchase and sale months;
the square root of adjusted R² estimates R, the share of your deal outcomes
that the index explains. Report it as indicative, with an interval.