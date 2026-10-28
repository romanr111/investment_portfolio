"""Pure USD risk equivalence and an evidence-based ten-check policy.

The score counts policy checks; it is not a forecast or Dalio's methodology.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import math

import numpy as np
import pandas as pd

from analytics.holy_grail import completed_month_end, fingerprint
from analytics.dalio_holy_grail import portfolio_variance_contributions
from analytics.diversification_checks import value_checks, bound_check

COUNT_VERSION = "risk_equivalent_streams_v1"
POLICY_VERSION = "diversification_policy_v1"
CHECK_IDS = ("family_concentration", "issuer_concentration", "breadth", "stability",
             "recession", "inflation", "liquidity_crypto", "counterparty", "local_fx", "illiquidity")
DEFAULT_THRESHOLDS = dict(family_concentration=40., issuer_concentration=10., breadth=15.,
                          stability=.75, recession=20., inflation=20., liquidity_crypto=20.,
                          counterparty=5., local_fx=10., illiquidity=20.,
                          history_coverage=99., material=1., liquid_days=30.)
SCENARIO_NAMES = ("recession", "inflation", "market_liquidity", "crypto_crash")
DEFAULT_SHOCKS = {
    "equity": (-.30, -.20, -.45, -.10), "gold": (.05, .10, -.10, 0.),
    "silver": (-.20, .10, -.30, 0.), "commodities": (-.25, .20, -.35, 0.),
    "crypto": (-.50, -.30, -.70, -.70), "stablecoin_lending": (-.20, -.10, -.35, -.20),
    "p2p": (-.20, -.10, -.35, 0.), "car_inventory": (-.25, -.15, -.35, 0.),
    "stablecoin_cash": (0., 0., -.20, -.20), "usd_cash": (0., 0., 0., 0.),
}
# Nominal yield, real yield and credit-spread changes, in decimal yield units.
DEFAULT_YIELD_SHOCKS = ((-.02, -.01, .06), (.03, .015, .02), (.01, .01, .08), (0., 0., .01))
FAMILIES = dict(equity="global_equity", gold="gold", silver="industrial_commodities",
                commodities="industrial_commodities", crypto="crypto", stablecoin_lending="credit",
                p2p="credit", car_inventory="operating_business", stablecoin_cash="credit",
                corporate_credit="credit", nominal_government="nominal_government",
                inflation_linked="inflation_linked", treasury_reserve="nominal_government")


def _finite(value):
    try:
        return float(value) if not isinstance(value, bool) and math.isfinite(float(value)) else None
    except (TypeError, ValueError, OverflowError):
        return None


def reviewed_record(exposure, as_of_date, *, review_cutoff=None):
    record = exposure.get("risk_record", {})
    try:
        valid = (isinstance(record, dict) and isinstance(record.get("source"), str) and bool(record["source"].strip())
                 and date.fromisoformat(record["effective_from"]) <= date.fromisoformat(as_of_date)
                 and (not record.get("effective_to") or date.fromisoformat(as_of_date) <= date.fromisoformat(record["effective_to"]))
                 and datetime.fromisoformat(record["reviewed_at"]).date() <= (date.fromisoformat(review_cutoff) if review_cutoff else datetime.now(timezone.utc).date()))
    except (ValueError, TypeError, KeyError):
        valid = False
    return record if valid else {}


def is_reserve(exposure, record, as_of_date):
    if record.get("stress_class") == "usd_cash":
        return (record.get("currency") == "USD" and record.get("counterparty_complete") is True
                and record.get("counterparty_groups") == {} and _finite(record.get("liquidation_days")) is not None
                and 0 <= float(record["liquidation_days"]) <= 30)
    if record.get("stress_class") == "treasury_reserve" and record.get("currency") == "USD":
        try:
            days = (date.fromisoformat(record["maturity"]) - date.fromisoformat(as_of_date)).days
            return 0 <= days <= 365
        except (ValueError, KeyError, TypeError):
            pass
    return False


def _sample_risk(frame, values):
    covariance = frame.cov().to_numpy(dtype=float)
    volatility = np.sqrt(np.diag(covariance))
    if not np.isfinite(covariance).all() or (volatility <= 0).any():
        return None
    weights = np.asarray(values, dtype=float)
    variance, contributions = portfolio_variance_contributions(weights, covariance)
    standalone = float(weights @ volatility)
    if not math.isfinite(variance) or variance <= standalone ** 2 * 1e-12:
        return None
    dr = standalone / math.sqrt(variance)
    effective = float(dr ** 2)
    if abs(effective - round(effective)) <= 1e-10:
        effective = float(round(effective))
    return {"effective_streams": effective, "diversification_ratio": dr,
            "volatility_reduction_pct": 100 * (1 - 1 / dr),
            "risk_shares": dict(zip(frame.columns, (np.abs(contributions) / np.abs(contributions).sum()).tolist()))}


def _unknown(identifier, threshold, reason="insufficient_evidence"):
    return dict(id=identifier, state="unknown", value=None, upper_bound=None,
                threshold=threshold, reasons=[reason])


def summarize_checks(checks):
    if len(checks) != 10 or {c["id"] for c in checks} != set(CHECK_IDS):
        raise ValueError("Exactly the ten versioned checks are required")
    counts = {state: sum(c["state"] == state for c in checks) for state in ("pass", "fail", "unknown")}
    if sum(counts.values()) != 10:
        raise ValueError("Invalid check state")
    return dict(score_min=10 * counts["pass"], score_max=10 * (counts["pass"] + counts["unknown"]),
                score=10 * counts["pass"] if not counts["unknown"] else None, check_counts=counts)


def calculate_quality(exposures, monthly_returns, *, as_of_date, total_assets,
                      policy=None, input_flags=(), generated_at=None):
    """Calculate once from reconciled holdings, reviewed facts and monthly returns."""
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update((policy or {}).get("thresholds", {}))
    checks = [_unknown(identifier, DEFAULT_THRESHOLDS[identifier]) for identifier in CHECK_IDS]
    result = dict(count_version=COUNT_VERSION, policy_version=POLICY_VERSION, as_of_date=as_of_date,
                  calculated_at=generated_at or datetime.now(timezone.utc).isoformat(), status="unavailable",
                  effective_streams=None, modeled_exposure_count=0, target_range=[15,20],
                  volatility_reduction_pct=None, return_window_start=None, return_window_end=None,
                  observation_count=0, scope="covered_subset", reserve_share_pct=0.,
                  coverage=dict(direct_pct=0., proxy_pct=0., uncovered_pct=0., reserve_pct=0.),
                  checks=checks, scenarios={}, stability={}, concentration={}, confidence="low",
                  constraints=sorted(set(input_flags)), policy_fingerprint=None,
                  score_min=None, score_max=None, score=None)
    try:
        if set(thresholds) != set(DEFAULT_THRESHOLDS) or any(_finite(v) is None or float(v)<=0 for v in thresholds.values()):
            raise ValueError('Invalid thresholds')
        thresholds={key:float(value) for key,value in thresholds.items()}
        if any(thresholds[key]>100 for key in thresholds if key not in {'breadth','liquid_days'}) or thresholds['material']>100:
            raise ValueError('Invalid thresholds')
        shocks=deepcopy(DEFAULT_SHOCKS);shocks.update((policy or {}).get('shocks',{}))
        yields=(policy or {}).get('yield_shocks',DEFAULT_YIELD_SHOCKS)
        if set(shocks)!=set(DEFAULT_SHOCKS) or any(len(v)!=4 or any(_finite(x) is None or not -1<=float(x)<=1 for x in v) for v in shocks.values()):
            raise ValueError('Invalid shocks')
        if len(yields)!=4 or any(len(v)!=3 or any(_finite(x) is None or abs(float(x))>1 for x in v) for v in yields):
            raise ValueError('Invalid yield shocks')
        shocks={k:tuple(float(x) for x in v) for k,v in shocks.items()}
        yields=tuple(tuple(float(x) for x in v) for v in yields)
    except (ValueError,TypeError,AttributeError):
        result['constraints'].append('invalid_policy')
        return result
    for check in checks: check['threshold']=thresholds[check['id']]
    total = _finite(total_assets)
    values = [_finite(e.get("value_usd")) for e in exposures]
    if total is None or total <= 0 or any(v is None or v < 0 for v in values) or sum(values) <= 0:
        result["constraints"].append("invalid_or_short_exposure")
        return result
    # DataSource truncates TOTAL_ASSETS to whole USD; components retain cents.
    if abs(sum(values) - total) > max(1.0, total * 1e-6):
        result["constraints"].append("unreconciled_valuations")
        return result
    # Normalize analytical shares to reconciled components, not the rounded display NAV.
    total = sum(values)
    if "unsupported_borrowing" in result["constraints"] or any(e.get("unsupported_risk") for e in exposures):
        result["constraints"].append("unsupported_leverage_or_nonlinear_risk")
        return result
    result["policy_fingerprint"] = fingerprint({"thresholds": thresholds, "shocks": shocks, "yield_shocks": yields, "version": POLICY_VERSION})
    rows = [deepcopy(e) for e in exposures if e["value_usd"] > 0]
    records = {e["id"]: reviewed_record(e, as_of_date) for e in rows}
    reserves = {e["id"] for e in rows if is_reserve(e, records[e["id"]], as_of_date)}
    result["reserve_share_pct"] = 100 * sum(e["value_usd"] for e in rows if e["id"] in reserves) / total
    result["coverage"]["reserve_pct"] = result["reserve_share_pct"]
    if rows and len(reserves) == len(rows) and not any(e.get("valuation_stale") for e in rows):
        result.update(status="not_applicable", effective_streams=0., scope="whole_portfolio")
        result["constraints"].append("reserves_have_no_independent_streams")
        return result
    cutoff = completed_month_end(as_of_date)
    frame = monthly_returns.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    if frame.index.has_duplicates or frame.columns.has_duplicates or not frame.index.is_month_end.all():
        frame = pd.DataFrame()
        result["constraints"].append("invalid_monthly_history")
    else:
        frame = frame.loc[(frame.index <= cutoff) & (frame.index.to_period("M") >= cutoff.to_period("M") - 59)]
        frame = frame.sort_index().apply(pd.to_numeric, errors="coerce").replace([np.inf,-np.inf],np.nan)
    grouped = {}
    aliases = {}
    representatives = []
    for column in frame.columns:
        representative = next((other for other in representatives if frame[column].equals(frame[other])), None)
        aliases[column] = representative if representative is not None else column
        if representative is None: representatives.append(column)
    for e in rows:
        if e["id"] in reserves:
            continue
        series = e.get("series")
        eligible = (not e.get("is_cash") and series in frame.columns and frame[series].notna().sum() >= 36
                    and frame[series].dropna().std() > 0)
        if eligible:
            canonical = aliases[series]
            grouped[canonical] = grouped.get(canonical, 0.) + e["value_usd"] / total
        key = ("proxy_pct" if e.get("kind") == "proxy" else "direct_pct") if eligible else "uncovered_pct"
        result["coverage"][key] += e["value_usd"] / total * 100
    aligned = frame[list(grouped)].dropna() if grouped else pd.DataFrame()
    result["modeled_exposure_count"] = len(grouped)
    result["observation_count"] = len(aligned)
    stats = _sample_risk(aligned, list(grouped.values())) if len(aligned) >= 36 else None
    if stats:
        result.update({key: stats[key] for key in ("effective_streams", "volatility_reduction_pct")})
        result.update(return_window_start=aligned.index[0].date().isoformat(), return_window_end=aligned.index[-1].date().isoformat())
        recent_frame = aligned.loc[aligned.index.to_period("M") >= cutoff.to_period("M") - 35]
        recent = _sample_risk(recent_frame, list(grouped.values())) if len(recent_frame) == 36 else None
        result["stability"] = dict(recent_effective_streams=recent["effective_streams"] if recent else None,
                                   ratio=recent["effective_streams"]/stats["effective_streams"] if recent else None)
        if stats["effective_streams"] > len(grouped) + 1e-9:
            result["constraints"].append("hedge_driven_count")
    else:
        result["constraints"].append("degenerate_covariance" if len(aligned) >= 36 else "insufficient_common_history")
    if result["coverage"]["uncovered_pct"] < 1e-8:
        result["scope"] = "whole_portfolio"
    reliable = (stats is not None and len(aligned) == 60 and aligned.index[-1] == cutoff
                and result["coverage"]["uncovered_pct"] <= (100-result["reserve_share_pct"])*(1-thresholds['history_coverage']/100) + 1e-9
                and sum(e['value_usd'] for e in rows if e.get('weak_proxy') or e.get('valuation_stale'))/total*100 < thresholds['material'])
    if reliable:
        families={};unmapped_risk=0.
        for e in rows:
            if e['id'] in reserves or aliases.get(e.get('series')) not in grouped: continue
            series=aliases[e['series']]
            risk=stats['risk_shares'][series]*(e['value_usd']/total)/grouped[series]*100
            family=FAMILIES.get(records[e['id']].get('stress_class'))
            if family: families[family]=families.get(family,0.)+risk
            else: unmapped_risk+=risk
        largest=max(families.values(),default=0.)
        checks[0]=bound_check('family_concentration',largest,min(100.,largest+unmapped_risk),thresholds['family_concentration'])
        result['concentration']=dict(family_risk_shares_pct=families,max_family_risk_pct=largest,unmapped_risk_pct=unmapped_risk)
        count = stats["effective_streams"]
        checks[2] = dict(id="breadth", state="pass" if count >= thresholds["breadth"] - 1e-10 and len(grouped) >= thresholds["breadth"] else "fail",
                         value=count, upper_bound=count, threshold=thresholds["breadth"], reasons=[])
        ratio = result["stability"]["ratio"]
        if ratio is not None:
            checks[3] = dict(id="stability", state="pass" if ratio >= thresholds["stability"] - 1e-10 else "fail",
                             value=ratio, upper_bound=ratio, threshold=thresholds["stability"], reasons=[])
    derived,scenarios=value_checks(rows,records,total,thresholds,shocks,yields,SCENARIO_NAMES)
    result['scenarios']=scenarios
    checks[:]=[derived.get(c['id'],c) for c in checks]
    result.update(summarize_checks(checks), status="provisional")
    result['critical_failures']=[c['id'] for c in checks if c['state']=='fail' and c['id'] in {'family_concentration','issuer_concentration','breadth','counterparty'}]
    material_weak=sum(e['value_usd'] for e in rows if e.get('weak_proxy') or e.get('valuation_stale'))/total*100>=thresholds['material']
    resolved=10-result['check_counts']['unknown']
    result['confidence']='low' if material_weak else 'high' if resolved==10 else 'medium' if resolved>=8 else 'low'
    if result['check_counts']['unknown']==0 and not material_weak: result['status']='assessed'
    if material_weak: result['constraints'].append('material_proxy_or_valuation_limit')
    if result['coverage']['uncovered_pct']>1e-8: result['constraints'].append('uncovered_exposures')
    if len(aligned)<60: result['constraints'].append('short_history')
    result['constraints']=sorted(set(result['constraints']))
    return result
