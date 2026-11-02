"""Content fingerprints and the completed-month rule shared by every saved Holy Grail record."""
from decimal import Decimal
import hashlib
import json

import pandas as pd


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


def holdings_fingerprint(data):
    """Identify saved financial inputs without including the derived metric."""
    keys = ("IB_DATA", "CRYPTO_DATA", "POSITION_DATA", "CASH_DATA", "TOTAL_ASSETS",
            "FIXED_INCOME_DATA", "OTHER_ASSETS", "DATA_QUALITY")
    def normalize(value, numeric_strings=False):
        # final_data serializes Decimal as text; dated snapshots use floats.
        # Instrument identifiers remain strings even when they look numeric.
        if isinstance(value, dict):
            return {key: normalize(item, numeric_strings) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item, numeric_strings) for item in value]
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return float(value)
        if numeric_strings and isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
        return value
    return fingerprint({key: normalize(data.get(key), key == "CASH_DATA") for key in keys})


def completed_month_end(as_of_date):
    stamp = pd.Timestamp(as_of_date).normalize()
    month = stamp.to_period("M")
    if stamp != month.end_time.normalize():
        month -= 1
    return month.end_time.normalize()
