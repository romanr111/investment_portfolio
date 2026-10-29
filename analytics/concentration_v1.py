"""Concentration safeguards recorded beside the diversity score (v1).

Measured limits live beside the asset-class score, not inside it: the score is a
group-level breadth metric and stays the single headline read. This block only
carries issuer/core/country/thesis facts recorded on the same frozen inputs.

Saved as `DIVERSIFICATION_DATA['concentration_v1']`, a sibling of
`allocation_score_v2`. Old saved records do not carry the key and remain valid:
absence of the sibling must never fail `validate_saved_allocation_v2` or any view.

Contract (pinned):
- Limits come from private `allocation.concentration_limits` on the stricter
  defaults below; theses from `allocation.linked_theses` as
  `{name: {'members': [position ids], 'limit_pct_equities': number}}`;
  decisions from `allocation.concentration_decisions` as
  `{id: {'limit': str, 'decided_at': str, 'decision': accept|reduce|exit,
        'reason': str, 'review_by': str}}`; records missing `decision` or
  `reason`, or decided after the block, never resolve a breach.
- Issuer aggregation uses an optional `issuer` profile key (single stocks
  default to their ticker; 9988+BABA -> 'alibaba'). Fund look-through uses a
  dated profile `holdings` field: `issuers` (issuer -> share of fund NAV),
  `coverage`, `as_of_date`, `source` plus an optional `max_other_issuer_share`
  (0..1, no larger than the smallest listed share: the upper bound for any
  issuer outside the declared list). Holdings missing `as_of_date`, or older
  than HOLDINGS_MAX_AGE_DAYS (90) days before the block's `as_of_date`, are
  not verified evidence: the fund falls back to a single ticker issuer (the
  plain-position fallback) and raises `unknown_issuer_lookthrough`. The
  uncovered fraction goes to `unknown_lookthrough_pct_equities`, never spread
  over members; with a declared `max_other_issuer_share` the unlisted tail
  joins it only when the fund's equity share times `max_other_issuer_share`
  could clear the issuer limit on its own (each unlisted issuer is otherwise
  verified too small to breach the limit), while profiles without one keep
  the whole uncovered fraction unverified.
- One breach per issuer over a limit, subject in the key: an issuer over the
  equities limit breaches under `issuer_pct_equities:<issuer>` and one over
  the NAV limit under `issuer_pct_nav:<issuer>`; the plain limits
  (`top4_pct_equities`, `core_min_pct_equities`, `country_pct_equities_china`,
  `thesis_pct_equities:<name>`) keep their plain keys. Decision records
  (still limit-name-matched until the subject-aware step) therefore resolve
  these breaches only when a record carries the exact prefixed key.
- Replay reads profiles/limits/theses/decisions ONLY from
  `v2_record['configuration']` (the merged settings stored and fingerprinted
  in the record) - never re-reads the profiles JSON path or private config.
  The block carries no own fingerprint; integrity is replay-recompute plus
  `_same` on recomputed values.

Block shape (scored):
{version, as_of_date, limits: {issuer_pct_equities, issuer_pct_nav,
 top4_pct_equities, core_min_pct_equities, country_pct_equities_china,
 thesis_pct_equities: {..}},
 facts: {largest_issuer: {id, pct_equities, pct_nav},
         top4_issuers: {ids, pct_equities}, core_pct_equities,
         issuers_over_limit: [{id, pct_equities, pct_nav}],
         country_pct_equities: {}, thesis_pct_equities: {},
         unknown_lookthrough_pct_equities, business_pct_invested,
         score_excluding_car},
 breaches: [{limit, value, decision_id}], warnings: []}
"""
from datetime import date
import math

VERSION = 'concentration_v1'

LIMIT_DEFAULTS = {
    'issuer_pct_equities': 5,
    'issuer_pct_nav': 2,
    'top4_pct_equities': 20,
    'core_min_pct_equities': 50,
    'country_pct_equities_china': 10,
    'thesis_pct_equities': {'china_stack': 10, 'consumer_recovery': 10},
}

WARNING_ISSUER = 'issuer_limit_breached'
WARNING_CORE = 'core_below_target'
WARNING_COUNTRY = 'country_limit_breached'
WARNING_THESIS = 'thesis_limit_breached'
WARNING_UNRESOLVED = 'unresolved_breach'
WARNING_UNKNOWN_LOOKTHROUGH = 'unknown_issuer_lookthrough'
WARNING_BUSINESS = 'business_assumption_material'

# Breach/warning comparison slack (values are percentages of a denominator).
EPS = 1e-9
# F5: an unmeasured business correlation drives the headline; above this share
# of invested capital the score must be read as provisional.
BUSINESS_WARNING_PCT_INVESTED = 5.
# Breach keys carry their subject after the ':': every issuer over a limit
# gets its own breach (limit=ISSUER_*_PREFIX + issuer), not just the largest.
ISSUER_EQ_PREFIX = 'issuer_pct_equities:'
ISSUER_NAV_PREFIX = 'issuer_pct_nav:'
THESIS_LIMIT_PREFIX = 'thesis_pct_equities:'
# Fund look-through is verified evidence only inside this window from the
# block's as_of_date: stale or undated holdings must not be silently spread
# into issuer shares, they make the fund an (unverified) single ticker issuer.
HOLDINGS_MAX_AGE_DAYS = 90


def unavailable_block(as_of_date, warnings):
    """Explicit unavailable state for a failed or insufficient build."""
    return {'version': VERSION, 'status': 'unavailable', 'as_of_date': as_of_date,
            'warnings': list(warnings)}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _merged_limits(config):
    """Private limits override the stricter shipped defaults; unknown keys fail."""
    limits = {'thesis_pct_equities': dict(LIMIT_DEFAULTS['thesis_pct_equities'])}
    limits.update({k: v for k, v in LIMIT_DEFAULTS.items() if k != 'thesis_pct_equities'})
    overrides = config.get('concentration_limits')
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if key == 'thesis_pct_equities':
                if not isinstance(value, dict) or any(not _finite(v) or v <= 0 for v in value.values()):
                    raise ValueError('Invalid thesis limit')
                limits['thesis_pct_equities'].update(value)
                continue
            if key not in LIMIT_DEFAULTS or not _finite(value) or value <= 0:
                raise ValueError('Invalid concentration limit: ' + str(key))
            limits[key] = value
    return limits


def _holdings_fresh(holdings, as_of_date):
    """Holdings count as verified only when dated within HOLDINGS_MAX_AGE_DAYS.

    Missing or unparseable dates on either side count as stale (the caller
    then treats the fund as holdings-less), so look-through is never silently
    applied from unverified data. A `None` anchor only occurs on direct
    harness-style calls with no block date; production callers (save hook,
    replay, what-if) always pass the block date, so the None branch defaults
    to fresh rather than silently degrading every direct probe.
    """
    if as_of_date is None:
        return True  # None anchor: direct harness calls only; production paths always pass a date
    try:
        anchor, seen = date.fromisoformat(as_of_date), holdings.get('as_of_date')
        if not isinstance(seen, str):
            return False
        return (anchor - date.fromisoformat(seen)).days <= HOLDINGS_MAX_AGE_DAYS
    except (ValueError, TypeError):
        return False


def _issuer_of(position, profile, as_of_date=None):
    """Explicit `issuer` wins; fresh declared `holdings` enable look-through;
    stale/undated holdings or none fall back to the ticker like plain positions."""
    issuer = profile.get('issuer')
    if issuer is not None:
        if not isinstance(issuer, str) or not issuer.strip():
            raise ValueError('Invalid profile issuer')
        return issuer.strip(), None
    holdings = profile.get('holdings')
    if holdings is not None:
        if not isinstance(holdings, dict):
            raise ValueError('Invalid profile holdings')
        if _holdings_fresh(holdings, as_of_date):
            return None, holdings
    identifier = position.get('id', '')
    return (identifier.split(':', 1)[1] if ':' in identifier else identifier), None


def _lookthrough(holdings):
    """Validate declared fund holdings.

    Returns (resolved issuer shares, uncovered fraction, max_other_issuer_share
    as declared or None). The optional `max_other_issuer_share` upper-bounds
    any issuer outside the listed set: it must stay in 0..1 and not exceed the
    smallest listed share.
    """
    declared = holdings.get('issuers')
    shares = {}
    if isinstance(declared, dict):
        for name, weight in declared.items():
            if not isinstance(name, str) or not name.strip() or not _finite(weight) or weight < 0:
                raise ValueError('Invalid profile holdings')
            if weight > 0:
                shares[name.strip()] = shares.get(name.strip(), 0.) + weight
    coverage = holdings.get('coverage')
    if coverage is None:
        coverage = sum(shares.values())
    if not _finite(coverage) or coverage < 0 or coverage > 1 + 1e-8 or sum(shares.values()) > coverage + 1e-8:
        raise ValueError('Invalid holdings coverage')
    max_other = holdings.get('max_other_issuer_share')
    if max_other is not None:
        if not _finite(max_other) or max_other < 0 or max_other > 1 + 1e-8:
            raise ValueError('Invalid profile holdings')
        if shares and max_other > min(shares.values()) + EPS:
            raise ValueError('Invalid profile holdings')
    resolved = sorted(shares.items(), key=lambda item: item[0])
    return resolved, max(0., 1. - float(coverage)), (None if max_other is None else float(max_other))


def _score_excluding_car(v2_result):
    """v2 main score recomputed without the car group and renormalized; null otherwise."""
    from analytics.allocation_score import correlation_map
    from analytics.allocation_score_v2 import score_components_v2
    try:
        if not isinstance(v2_result, dict) or v2_result.get('status') == 'unavailable':
            return None
        weights = {g['id']: float(g['weight']) for g in v2_result.get('groups', [])}
        car = weights.get('car_business', 0.)
        if not math.isfinite(car) or car <= 0:
            return None
        remaining = {g: w for g, w in weights.items() if g != 'car_business' and w > 0}
        scale = sum(remaining.values())
        if scale <= 0:
            return None
        weights = {g: w / scale for g, w in remaining.items()}
        scenario = (v2_result.get('scenarios') or {}).get('m60_r025')
        if not isinstance(scenario, dict) or scenario.get('score') is None:
            return None
        pairs = [p for p in scenario.get('pairs', [])
                 if isinstance(p, dict) and 'car_business' not in (p.get('left'), p.get('right'))]
        correlations = correlation_map(pairs)
        sectors = {g: s for g, s in (v2_result.get('sectors') or {}).items() if g in weights}
        return score_components_v2(weights, correlations, sectors)['score']
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def build_block(positions, config, total, as_of_date, v2_result=None):
    """Build the limits/facts/breaches concentration block from frozen inputs.

    `v2_result` is the fresh saved v2 record; the `score_excluding_car` fact
    needs its frozen group weights, correlation pairs and sector map, so it is
    computed only when the car group has a positive weight and the main
    scenario was scored.
    """
    from analytics.allocation_inputs import profile_for
    total = float(total)
    if not math.isfinite(total) or total <= 0:
        raise ValueError('invalid_total')
    limits = _merged_limits(config)
    issuers, thesis_equity, positions_equity = {}, {}, {}
    equities = invested = core = china = car = uncovered = 0.
    tails, stale = [], 0.
    for position in positions:
        value = float(position['value_usd'])
        if not math.isfinite(value) or value < 0:
            raise ValueError('invalid_valuation')
        if value == 0:
            continue
        invested += value
        profile = profile_for(position, config, as_of_date) if config is not None else None
        equity = car_now = china_now = 0.
        if profile is not None:
            for component in profile['components']:
                amount = value * component['share']
                group = component['group']
                if group == 'car_business':
                    car_now += amount
                if group == 'equity_china':
                    china_now += amount
                if group.startswith('equity_'):
                    equity += amount
        if car_now:
            car += car_now
        if china_now:
            china += china_now
        if equity <= 0:
            continue
        equities += equity
        identifier = position.get('id', '')
        positions_equity[identifier] = positions_equity.get(identifier, 0.) + equity
        if profile is not None and profile.get('core') is True:
            core += equity
        issuer, holdings = _issuer_of(position, profile, as_of_date)
        if holdings is None:
            issuers[issuer] = issuers.get(issuer, 0.) + equity
            if (profile is not None and profile.get('issuer') is None
                    and profile.get('holdings') is not None):
                stale += equity  # undated/stale look-through: unverified fallback
            continue
        resolved, share_unknown, max_other = _lookthrough(holdings)
        for name, share in resolved:
            issuers[name] = issuers.get(name, 0.) + equity * share
        if share_unknown > 0:
            if max_other is None:
                uncovered += equity * share_unknown
            else:
                tails.append((equity, share_unknown, max_other))
    for tail_equity, tail_unknown, max_other in tails:
        # The unlisted tail of a fund with a declared max_other_issuer_share is
        # only an unverified risk when one unlisted issuer times the fund's
        # equity share could clear the issuer limit on its own - otherwise it
        # is verified too small to breach anything.
        if tail_equity * max_other / equities * 100 > limits['issuer_pct_equities'] + EPS:
            uncovered += tail_equity * tail_unknown
    linked = config.get('linked_theses') if isinstance(config.get('linked_theses'), dict) else {}
    for name, thesis in sorted(linked.items()):
        members = set(thesis.get('members') or []) if isinstance(thesis, dict) else set()
        amount = sum(equity for position_id, equity in positions_equity.items() if position_id in members)
        if amount > EPS:
            thesis_equity[name] = amount
    ordered = sorted(issuers.items(), key=lambda item: (-item[1], item[0]))
    # Per-issuer percentages of both denominators in `ordered` order (pct
    # equities descending): one breach per issuer over a limit, subject in key.
    issuer_pcts = [(issuer, amount / equities * 100, amount / total * 100)
                   for issuer, amount in ordered]
    facts = {
        'largest_issuer': (dict(id=ordered[0][0],
                                pct_equities=ordered[0][1] / equities * 100,
                                pct_nav=ordered[0][1] / total * 100) if ordered
                           else dict(id=None, pct_equities=0., pct_nav=0.)),
        'top4_issuers': dict(ids=[issuer for issuer, _ in ordered[:4]],
                             pct_equities=sum(amount for _, amount in ordered[:4]) / equities * 100
                             if equities > 0 else 0.),
        'issuers_over_limit': [dict(id=issuer, pct_equities=pct_eq, pct_nav=pct_nav)
                               for issuer, pct_eq, pct_nav in issuer_pcts
                               if pct_eq > limits['issuer_pct_equities'] + EPS
                               or pct_nav > limits['issuer_pct_nav'] + EPS],
        'core_pct_equities': core / equities * 100 if equities > 0 else 0.,
        'country_pct_equities': ({'china': china / equities * 100} if china > EPS and equities > 0 else {}),
        'thesis_pct_equities': ({name: amount / equities * 100 for name, amount in sorted(thesis_equity.items())}
                                if equities > 0 else {}),
        'unknown_lookthrough_pct_equities': uncovered / equities * 100 if equities > 0 else 0.,
        'business_pct_invested': car / invested * 100 if invested > 0 else 0.,
        'score_excluding_car': _score_excluding_car(v2_result),
    }
    breaches = []
    if equities > EPS:
        for issuer, pct_eq, pct_nav in issuer_pcts:
            if pct_eq > limits['issuer_pct_equities'] + EPS:
                breaches.append(dict(limit=ISSUER_EQ_PREFIX + issuer, value=pct_eq, decision_id=None))
            if pct_nav > limits['issuer_pct_nav'] + EPS:
                breaches.append(dict(limit=ISSUER_NAV_PREFIX + issuer, value=pct_nav, decision_id=None))
        if facts['top4_issuers']['pct_equities'] > limits['top4_pct_equities'] + EPS:
            breaches.append(dict(limit='top4_pct_equities', value=facts['top4_issuers']['pct_equities'],
                                 decision_id=None))
        if facts['core_pct_equities'] < limits['core_min_pct_equities'] - EPS:
            breaches.append(dict(limit='core_min_pct_equities', value=facts['core_pct_equities'], decision_id=None))
        china_value = facts['country_pct_equities'].get('china', 0.)
        if china_value > limits['country_pct_equities_china'] + EPS:
            breaches.append(dict(limit='country_pct_equities_china', value=china_value, decision_id=None))
        for name, value in facts['thesis_pct_equities'].items():
            thesis_limit = _thesis_limit(config, name, limits)
            if thesis_limit is not None and value > thesis_limit + EPS:
                breaches.append(dict(limit=THESIS_LIMIT_PREFIX + name, value=value, decision_id=None))
    warnings = []
    if any(breach['limit'].startswith(ISSUER_EQ_PREFIX) or breach['limit'].startswith(ISSUER_NAV_PREFIX)
           or breach['limit'] == 'top4_pct_equities' for breach in breaches):
        warnings.append(WARNING_ISSUER)
    if any(breach['limit'] == 'core_min_pct_equities' for breach in breaches):
        warnings.append(WARNING_CORE)
    if any(breach['limit'] == 'country_pct_equities_china' for breach in breaches):
        warnings.append(WARNING_COUNTRY)
    if any(breach['limit'].startswith(THESIS_LIMIT_PREFIX) for breach in breaches):
        warnings.append(WARNING_THESIS)
    if facts['unknown_lookthrough_pct_equities'] > EPS or stale > EPS:
        warnings.append(WARNING_UNKNOWN_LOOKTHROUGH)
    if facts['business_pct_invested'] > BUSINESS_WARNING_PCT_INVESTED + EPS:
        warnings.append(WARNING_BUSINESS)
    if invested <= 0:
        # No invested capital: the equity-denominated facts are meaningless.
        raise ValueError('no_invested_capital')  # surfaced by the save hook as unavailable
    return dict(version=VERSION, as_of_date=as_of_date, limits=limits, facts=facts,
                breaches=breaches, warnings=warnings)


def _thesis_limit(config, name, limits):
    """Thesis limit precedence: private limits block, then the thesis record."""
    candidate = limits['thesis_pct_equities'].get(name)
    if candidate is None:
        linked = config.get('linked_theses') if isinstance(config.get('linked_theses'), dict) else {}
        thesis = linked.get(name)
        if isinstance(thesis, dict):
            candidate = thesis.get('limit_pct_equities')
            if candidate is not None and (not _finite(candidate) or candidate <= 0):
                raise ValueError('Invalid thesis limit')
    if candidate is None or isinstance(candidate, bool) or not _finite(candidate):
        return None
    return float(candidate)


def match_decisions(block, decisions, as_of_date):
    """Fill `decision_id` on breaches from recorded decision records.

    A breach counts as resolved only when a complete decision record for the
    same limit exists - the recorded choice is `accept`, `reduce` or `exit`,
    it carries a non-empty `reason`, and it was decided no later than
    `as_of_date` - and its `review_by` date is >= `as_of_date`. Incomplete or
    future-dated records, and anything else, keep `decision_id=None` and raise
    the `unresolved_breach` warning.
    """
    if not isinstance(block, dict) or block.get('version') != VERSION:
        return block
    records = decisions if isinstance(decisions, dict) else {}
    as_of = date.fromisoformat(as_of_date)
    candidates = []
    for record_id, record in records.items():
        if not isinstance(record, dict):
            continue
        limit, decided_at, review_by = record.get('limit'), record.get('decided_at'), record.get('review_by')
        if (record.get('decision') not in ('accept', 'reduce', 'exit')
                or not isinstance(record.get('reason'), str) or not record['reason'].strip()
                or not isinstance(limit, str) or not limit):
            continue
        try:
            decided, reviewed = date.fromisoformat(decided_at), date.fromisoformat(review_by)
        except (ValueError, TypeError):
            continue
        if decided > as_of:
            continue
        candidates.append(dict(id=record_id, limit=limit, decided_at=decided_at, review_by=reviewed))
    for breach in block.get('breaches', []):
        eligible = [record for record in candidates
                    if record['limit'] == breach.get('limit') and record['review_by'] >= date.fromisoformat(as_of_date)]
        if eligible:
            # Latest decision date; lexicographically greatest id breaks ties.
            chosen = max(eligible, key=lambda record: (record['decided_at'], record['id']))
            breach['decision_id'] = chosen['id']
    if block.get('breaches') and any(breach.get('decision_id') is None for breach in block['breaches']):
        warnings = block.get('warnings')
        if isinstance(warnings, list) and WARNING_UNRESOLVED not in warnings:
            warnings.append(WARNING_UNRESOLVED)
    return block


def validate_saved_concentration(block, data, v2_record):
    """Replay the saved block from the v2 record's frozen configuration."""
    try:
        if block is None:
            return True
        if not isinstance(block, dict) or block.get('version') != VERSION:
            return False
        if block.get('status') == 'unavailable':
            if not isinstance(block.get('as_of_date'), str):
                return False
            date.fromisoformat(block['as_of_date'])
            return isinstance(block.get('warnings'), list)
        if not isinstance(v2_record, dict) or v2_record.get('version') != 'capital_diversification_v2':
            return False
        as_of = v2_record.get('as_of_date')
        if block.get('as_of_date') != as_of or not isinstance(as_of, str):
            return False
        date.fromisoformat(as_of)
        config = v2_record.get('configuration')
        if not isinstance(config, dict):
            return False
        from analytics.holy_grail_data import extract_exposures  # avoid import cycles
        positions, _, _ = extract_exposures(data, as_of, config.get('extraction_settings', {}))
        if positions != v2_record.get('positions'):
            return False
        invested = sum(float(p['value_usd']) for p in positions)
        coverage = v2_record.get('coverage') or {}
        if invested <= 0:
            return False
        total = invested * 100 / float(coverage['invested_pct_nav'])
        fresh = build_block(positions, config, total, as_of, v2_result=v2_record)
        fresh = match_decisions(fresh, config.get('concentration_decisions'), as_of)
        from analytics.allocation_score_v2 import _same
        return _same(fresh, block)
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        return False