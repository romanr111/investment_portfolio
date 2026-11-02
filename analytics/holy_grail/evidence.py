"""Fingerprint of the saved inputs a diversification record was built from, and dated risk-evidence validation."""
from datetime import date, datetime, timezone

from analytics.holy_grail.fingerprint import fingerprint, holdings_fingerprint


def quality_inputs_fingerprint(data):
    def normalize(value):
        if isinstance(value,dict): return {k:normalize(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)): return [normalize(v) for v in value]
        if isinstance(value,(int,float)) and not isinstance(value,bool): return float(value)
        # Enhanced broker fields may use Decimal in the existing serializer.
        from decimal import Decimal
        if isinstance(value,Decimal): return float(value)
        return value
    return fingerprint(dict(holdings=holdings_fingerprint(data),
                            metadata=normalize(data.get('DATA_METADATA')),
                            enhanced=normalize(data.get('ENHANCED_STOCKS'))))


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
