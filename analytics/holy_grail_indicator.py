"""Saved, risk-equivalent indicator independent of the legacy policy score."""
from analytics.holy_grail import fingerprint
from analytics.diversification_quality import COUNT_VERSION
from analytics.diversification_inputs import quality_inputs_fingerprint

VERSION = 'holy_grail_indicator_v1'


def validate_saved_indicator(indicator, data, expected_date=None):
    """Historical config is frozen; validation never reads today's private config."""
    if not isinstance(indicator,dict) or indicator.get('version') != VERSION: return False
    if indicator.get('count_version') != COUNT_VERSION: return False
    if indicator.get('result_fingerprint') != fingerprint({k:v for k,v in indicator.items() if k != 'result_fingerprint'}): return False
    if indicator.get('holdings_fingerprint') != quality_inputs_fingerprint(data): return False
    if expected_date and indicator.get('as_of_date') != expected_date: return False
    if indicator.get('configuration_fingerprint') != fingerprint(indicator.get('configuration')): return False
    return indicator.get('status') in {'modeled','provisional','not_applicable','unavailable'}
