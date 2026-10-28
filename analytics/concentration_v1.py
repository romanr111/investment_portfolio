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
        'reason': str, 'review_by': str}}`.
- Issuer aggregation uses an optional `issuer` profile key (single stocks
  default to their ticker; 9988+BABA -> 'alibaba'). Fund look-through uses a
  dated profile `holdings` field (issuer -> share, plus `source`,
  `as_of_date`, `coverage`); the uncovered fraction goes to
  `unknown_lookthrough_pct_equities`, never spread over members.
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
         country_pct_equities: {}, thesis_pct_equities: {},
         unknown_lookthrough_pct_equities, business_pct_invested,
         score_excluding_car},
 breaches: [{limit, value, decision_id}], warnings: []}
"""
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


def unavailable_block(as_of_date, warnings):
    """Explicit unavailable state for a failed or insufficient build."""
    return {'version': VERSION, 'status': 'unavailable', 'as_of_date': as_of_date,
            'warnings': list(warnings)}


def build_block(positions, config, total, as_of_date, v2_result=None):
    """Build the limits/facts/breaches concentration block from frozen inputs.

    `v2_result` is the fresh saved v2 record; the `score_excluding_car` fact
    needs its frozen group weights, correlation pairs and sector map, so it is
    computed only when the car group has a positive weight and the main
    scenario was scored.
    """
    raise NotImplementedError('Implemented by the concentration-facts change')


def match_decisions(block, decisions, as_of_date):
    """Fill `decision_id` on breaches from recorded decision records.

    A breach counts as resolved only when a decision record for the same
    limit exists and its `review_by` date is >= `as_of_date`; anything else
    keeps `decision_id=None` and raises the `unresolved_breach` warning.
    """
    raise NotImplementedError('Implemented by the concentration-facts change')


def validate_saved_concentration(block, data, v2_record):
    """Replay the saved block from the v2 record's frozen configuration."""
    raise NotImplementedError('Implemented by the concentration-facts change')