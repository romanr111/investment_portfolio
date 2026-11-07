# Diversification goal

Owner decision, 2026-11-07. What the headline score `risk_progress_v3` aims
for; check later changes against it. Formulas, parameters and limits:
[diversification-methodology.md](diversification-methodology.md), section
"Risk progress v3".

## Goal

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

## Why 7 streams

In 2026-11 research, long-only portfolios reached about 2.5-3.2 effective
streams out of sample with liquid assets, and about 5 with private assets under
central literature assumptions, so 15 streams was out of reach and the score
did not guide decisions. With 7, a 30-stream individual menu reaches 100 at its
best weights, while a typical liquid portfolio stays near 60 (calibration on
public data, 60 months to 2026-10).
