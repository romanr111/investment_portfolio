# Car deal ledger (phase 2 input)

One local CSV, `data/car_deals.csv` (git-ignored like every `data/` file).
One row per deal. Log **open deals at purchase** (dropping unsold cars would
hide the bad outcomes); set `sale_date` when the car leaves.

Goal: collect complete, dated deal records so that the owner's own outcomes can
later be compared with the category price index used by the correlation tracker
(`analytics/car_category.py`, where the index loading R in
`rho(business, group) = R * rho(index, group)` is fixed at 1 as a scenario
assumption). No deal count unlocks calibration automatically: it needs dated
evidence that includes unsold cars and failed deals, and an independent
validation. Back-filling deals from memory without dates adds noise, not data -
log as they happen. The single past resale may be entered, but it is one point.

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

Derived, never stored: all-in cost, `roi_pct = (sale − all-in cost) / all-in cost`
(return on invested cost), `net_margin_pct = (sale − all-in cost) / sale` (margin on
revenue; both are before income tax unless the costs include it), holding days.
Turnover (cycles per year) is a third, separate quantity.

Phase 2, exploratory only (not a readiness gate): compare each deal's `roi_pct`
with the category price-index change between its purchase and sale months.
That is a deal-horizon relation, not the monthly loading R. Overlapping holding
periods and omitted unsold or losing deals bias it, and adjusted R² can be small or
negative, so no square root is taken. Report any estimate as indicative with an
interval, and do not replace R = 1 without an independent validation.