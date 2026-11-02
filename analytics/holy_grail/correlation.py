"""Monthly return windows, pairwise correlations and history (de)serialization shared by every method version."""
from itertools import combinations
import json
import math

import numpy as np
import pandas as pd

from analytics.holy_grail.fingerprint import completed_month_end


def monthly_window(frame, as_of_date):
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    if frame.index.has_duplicates or not frame.index.is_month_end.all() or frame.columns.has_duplicates:
        raise ValueError('Histories must have unique month ends and series')
    frame = frame.apply(pd.to_numeric, errors='raise')
    if np.isinf(frame.to_numpy(dtype=float)).any():
        raise ValueError('Non-finite return history')
    cutoff = completed_month_end(as_of_date)
    return frame.reindex(pd.date_range(end=cutoff, periods=60, freq=pd.offsets.MonthEnd()))


def pair_correlations(frame, groups, as_of_date, *, business=(), business_correlation=.25):
    frame = monthly_window(frame, as_of_date)
    pairs = []
    for left, right in combinations(sorted(groups), 2):
        pair = dict(left=left, right=right, correlation=None, observations=0,
                    last_month=None, months=[], kind='missing')
        if (left in business) != (right in business):
            pair.update(correlation=business_correlation, kind='modeled', observations=None)
        elif left in frame and right in frame:
            common = frame[[left, right]].dropna()
            pair.update(observations=len(common), months=[d.date().isoformat() for d in common.index],
                        last_month=common.index[-1].date().isoformat() if len(common) else None)
            if len(common) >= 36 and (common.std() > 0).all():
                rho = float(common.iloc[:, 0].corr(common.iloc[:, 1]))
                if math.isfinite(rho):
                    pair.update(correlation=min(1., max(-1., rho)), kind='measured')
        pairs.append(pair)
    return pairs


def correlation_map(pairs):
    return {(p['left'], p['right']): p['correlation'] for p in pairs if p['correlation'] is not None}


def history_payload(frame):
    return json.loads(frame.to_json(date_format='iso', double_precision=15))


def history_frame(payload):
    frame = pd.DataFrame(payload, dtype=float)
    frame.index = pd.to_datetime(frame.index)
    return frame
