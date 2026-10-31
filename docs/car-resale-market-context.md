# Car resale market context

The diversification score uses its existing business-correlation scenarios. Public car-market data is separate context, not a business return, profit forecast, or measured correlation.

`analytics.car_resale_market.build_context(cutoff, observations)` freezes a manually collected one-time dataset. Add the returned object as `CAR_RESALE_MARKET_CONTEXT` in the `data` object of a separate derived combined-data snapshot; do not modify the original snapshot or its sealed `allocation_score_v2`. The cutoff is the source snapshot's timezone-aware `saved_at_utc`, not the time of enrichment. Private snapshots stay under ignored `data/`.

Each observation needs `id`, `label`, `value` (a number or null), `unit`, `period`, ISO `period_end`, ISO `published`, an HTTPS `url`, and `limitation`. A range may include numeric `upper`. For a comparison in the same series, add `previous`, `previous_period`, `previous_published`, and HTTPS `previous_url`; the builder derives `change_pct`. A publication date without time must be earlier than the snapshot date. Include precise timezone-aware publication timestamps for sources published on the cutoff date. Record unavailable data with a null value and explain the limitation.

The frozen block includes a version, cutoff, observations and fingerprint. The view validates and replays it before rendering the source-dated note. Missing, altered or invalid context is shown as unavailable. Collection is manual; no automatic updates or assumptions about the next snapshot are made.

Generated notes end with the portfolio note marker. The Sheets writer only replaces or clears notes bearing that marker within its recorded owned range; a different note at the target is a conflict. It also recognizes notes from the earlier marker-first format. Existing full-sheet writes remain subject to their usual preflight, and a separate live refresh is required to validate the entire production flow.
