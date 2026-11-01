"""Bound the car-business correlation from public drivers, outside the sealed score.

Diagnostic only ("bounded, unmeasured"): a group's correlation with the car
business cannot exceed that group's multiple correlation with the public
drivers, so no business return history is needed. Nothing here writes into
`DIVERSIFICATION_DATA`, `METHOD`, or any saved record; output goes to stdout
and an optional sidecar JSON under `data/`.

Two bounds per group (plan step 4): the physical panel (used-vehicle CPI +
USD/UAH) gives the low bound; adding the listed auto-remarketing equities
gives the conservative high bound, at the cost of equity beta.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.allocation_score import correlation_map, history_frame
from analytics.allocation_score_v2 import score_components_v2
from analytics.allocation_v2_inputs import _group_history

MIN_COMPLETE_MONTHS = 48
# Median 90th-percentile bound under no true relation (plan's throwaway runs):
NULL_FLOOR = {(60, 2): 0.30, (60, 4): 0.40, (120, 2): 0.21}


def _null_floor(n: int, k: int) -> float:
    documented = NULL_FLOOR.get((n, k))
    if documented is not None:
        return documented
    base = 0.30 if k <= 2 else 0.40
    return base * min(1.0, 60.0 / n)


def _multiple_r(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float]:
    """Plain R², adjusted R² and the multiple-correlation bound R."""
    n, k = x.shape[0], x.shape[1] - 1
    design = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    denom = n - k - 1
    if denom <= 0:
        raise ValueError("not enough months for the driver count")
    # Plan formula (single correction): R_g = sqrt(max(0, 1-(1-R²_g)(n-1)/(n-k-1)))
    adjusted = 1.0 - (1.0 - r_squared) * (n - 1) / denom
    bound = math.sqrt(max(0.0, adjusted))
    return r_squared, adjusted, bound


def driver_bound(group_returns, drivers, *, n_boot: int = 1000, seed: int = 261042) -> dict:
    """Multiple-correlation upper bound of one group against the driver panel.

    Inputs align on shared month-ends; months with any missing value drop.
    Below `MIN_COMPLETE_MONTHS` complete months the result is unavailable with
    a reason — never zero-filled. Inputs are never mutated.
    """
    group = pd.Series(group_returns, dtype=float).dropna()
    group.index = pd.to_datetime(group.index).tz_localize(None).normalize()
    panel = pd.DataFrame(drivers, dtype=float).copy()
    panel.index = pd.to_datetime(panel.index).tz_localize(None).normalize()
    shared = pd.concat([group.rename("group"), panel], axis=1, join="inner").sort_index()
    complete = shared.loc[~shared.index.duplicated()].dropna()
    n, k = complete.shape[0], panel.shape[1]
    drivers_named = [c for c in panel.columns if c != "group"]
    if n < MIN_COMPLETE_MONTHS or n <= k + 1:
        return {"status": "unavailable", "reason": "insufficient_complete_months",
                "n": int(n), "k": int(k), "min_required": MIN_COMPLETE_MONTHS,
                "drivers": drivers_named,
                "warning": "bound holds only for a complete driver list"}
    y = complete["group"].to_numpy(dtype=float)
    x = complete[drivers_named].to_numpy(dtype=float)
    r_squared, adjusted, bound = _multiple_r(y, x)
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot, dtype=float)
    for draw in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            draws[draw] = _multiple_r(y[idx], x[idx])[2]
        except ValueError:
            draws[draw] = bound
    return {"status": "ok", "n": int(n), "k": int(k),
            "r_squared": round(r_squared, 6), "adjusted_r_squared": round(adjusted, 6),
            "bound": round(bound, 6),
            "bound_median": round(float(np.median(draws)), 6),
            "bound_p90": round(float(np.percentile(draws, 90)), 6),
            "null_floor": round(_null_floor(n, k), 6), "drivers": drivers_named,
            "warning": "bound holds only for a complete driver list"}


def score_range(v2_record: dict, bounds: dict) -> dict:
    """Rebuild the v2 score with every car pair fixed at 0, then at the bounds.

    `bounds` maps a bound label ('zero', 'low', 'high') to a scalar applied to
    every `(group, car_business)` pair, or to a per-group dict of scalars. The
    saved `m60_r025` and `m60_r075` scores travel through unchanged for the
    comparison row. Setting every car pair to the scenario assumption (0.25)
    reproduces the saved `m60_r025` score exactly, which is the plumbing check.
    """
    if not isinstance(v2_record, dict) or v2_record.get("status") == "unavailable":
        raise ValueError("v2 record unavailable")
    scenario = (v2_record.get("scenarios") or {}).get("m60_r025")
    if not isinstance(scenario, dict) or scenario.get("score") is None:
        raise ValueError("m60_r025 scenario missing")
    weights = {g["id"]: float(g["weight"]) for g in v2_record.get("groups", [])}
    if weights.get("car_business", 0.0) <= 0:
        raise ValueError("car_business weight is zero in this record")
    sectors = {g: s for g, s in (v2_record.get("sectors") or {}).items() if g in weights}
    base_pairs = [p for p in scenario.get("pairs", [])
                  if isinstance(p, dict) and p.get("correlation") is not None]

    def rebuilt(value_by_group: dict) -> float:
        correlations = correlation_map(base_pairs)
        for pair in base_pairs:
            left, right = pair["left"], pair["right"]
            if "car_business" not in (left, right):
                continue
            other = right if left == "car_business" else left
            value = value_by_group.get(other, value_by_group.get("*"))
            if value is None:
                continue
            rho = float(value)
            correlations[(left, right)] = rho
            correlations[(right, left)] = rho
        return score_components_v2(weights, correlations, sectors)["score"]

    def value_map(label: str) -> dict:
        specification = bounds.get(label)
        if isinstance(specification, dict):
            return specification
        return {"*": specification}

    out = {"scenario": "m60_r025", "saved_m60_r025": scenario["score"],
           "saved_m60_r075": ((v2_record.get("scenarios") or {}).get("m60_r075") or {}).get("score"),
           "note": "bounded, unmeasured"}
    for label in ("zero", "low", "high"):
        if label in bounds:
            out[label] = rebuilt(value_map(label))
    return out


def _as_payload(histories):
    """Saved records store the dict payload; tolerate a JSON string too."""
    if isinstance(histories, str):
        return json.loads(histories)
    return histories


def load_v2_record(snapshot_path: str) -> dict:
    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    record = (data.get("DIVERSIFICATION_DATA") or {}).get("allocation_score_v2")
    if not isinstance(record, dict):
        raise ValueError("snapshot has no DIVERSIFICATION_DATA.allocation_score_v2 record")
    return record


def _group_bound(group_returns, panel_full, panel_physical) -> dict:
    full = driver_bound(group_returns, panel_full)
    physical = driver_bound(group_returns, panel_physical)
    if full.get("status") != "ok":
        return full
    merged = dict(full)
    merged["low"] = None if physical.get("status") != "ok" else physical["bound_p90"]
    merged["high"] = full["bound_p90"]
    merged["physical"] = {k: physical.get(k) for k in ("status", "n", "k", "bound", "bound_p90")}
    merged["warning"] = "bound holds only for a complete driver list"
    return merged


def run(snapshot_path: str, cache_dir: str, *, include_listed: bool = True,
        allow_network: bool = True, output_path: str | None = None,
        panel_frame=None) -> dict:
    """End-to-end diagnostic: driver panel, per-group bounds, score range."""
    from analytics.car_business_drivers import LISTED_DRIVERS, PHYSICAL_DRIVERS, collect_driver_panel

    record = load_v2_record(snapshot_path)
    weights = {g["id"]: float(g["weight"]) for g in record.get("groups", [])}
    if weights.get("car_business", 0.0) <= 0:
        raise ValueError("car_business weight is zero in this snapshot; nothing to bound")
    definitions = (record.get("method_definition") or {}).get("group_definitions") or {}
    group_returns = _group_history(history_frame(_as_payload(record.get("histories") or {})), weights, definitions)
    if panel_frame is None:
        panel_frame = collect_driver_panel(record.get("as_of_date") or "2026-10-31",
                                           cache_dir=cache_dir, allow_network=allow_network,
                                           include_listed=include_listed)
    physical_columns = [e["series"] for e in PHYSICAL_DRIVERS if e["series"] in panel_frame.columns]
    full_columns = [c for c in panel_frame.columns
                    if c in physical_columns or not include_listed or c in {e["series"] for e in LISTED_DRIVERS}]
    rows, low_map, high_map = [], {}, {}
    for group, weight in sorted(weights.items()):
        if group == "car_business" or weight <= 0:
            continue
        if group not in group_returns.columns:
            rows.append({"group": group, "weight": weight, "status": "unavailable",
                         "reason": "no saved history for this group"})
            continue
        merged = _group_bound(group_returns[group], panel_frame[full_columns], panel_frame[physical_columns])
        merged.update(group=group, weight=weight)
        rows.append(merged)
        if merged.get("status") == "ok" and merged.get("low") is not None:
            low_map[group] = merged["low"]
            high_map[group] = merged["high"]
    report = {"as_of_date": record.get("as_of_date"), "groups": rows,
              "drivers": list(panel_frame.columns), "flags": panel_frame.attrs.get("flags", []),
              "note": "bounded, unmeasured",
              "floor_legend": {"60m/2d": 0.30, "60m/4d": 0.40,
                               "holds only for a complete driver list": True}}
    if low_map and high_map:
        report["range"] = score_range(record, {"zero": 0.0, "low": low_map, "high": high_map})
    else:
        report["range"] = {"note": "no group bounds available"}
    if output_path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def print_table(report: dict) -> str:
    lines = ["# Car-business correlation bound — bounded, unmeasured",
             f"as of {report.get('as_of_date')} · drivers: {', '.join(report.get('drivers', []))}",
             "Bound holds only if the driver list is complete. Floors (median p90, no true relation): ~0.30 at 60m/2 drivers, ~0.40 at 60m/4."]
    rng = report.get("range") or {}
    if rng.get("saved_m60_r025") is not None:
        lines.append(f"Saved scores: m60_r025={rng['saved_m60_r025']} m60_r075={rng.get('saved_m60_r075')}")
        for label in ("zero", "low", "high"):
            if label in rng:
                lines.append(f"Score with car pairs at {label}: {rng[label]}")
    for row in report.get("groups", []):
        if row.get("status") != "ok":
            lines.append(f"- {row.get('group')} (w={row.get('weight')}): UNAVAILABLE ({row.get('reason')}, n={row.get('n')})")
            continue
        lines.append(
            f"- {row.get('group')} (w={row.get('weight')}): n={row['n']} k={row['k']} "
            f"R²={row['r_squared']} adjR²={row['adjusted_r_squared']} · "
            f"low={row.get('low')} high={row['high']} (median {row['bound_median']}, floor {row['null_floor']})")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Car-business correlation bound (bounded, unmeasured)")
    parser.add_argument("--snapshot", required=True, help="path to a combined_data snapshot JSON")
    parser.add_argument("--cache-dir", default="data/holy_grail_history")
    parser.add_argument("--offline", action="store_true", help="serve everything from cache")
    parser.add_argument("--output", help="sidecar JSON path under data/ (never inside DIVERSIFICATION_DATA)")
    parser.add_argument("--no-listed", action="store_true", help="skip the listed high-bound driver block")
    args = parser.parse_args(argv)
    report = run(args.snapshot, args.cache_dir, include_listed=not args.no_listed,
                 allow_network=not args.offline, output_path=args.output)
    print(print_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())