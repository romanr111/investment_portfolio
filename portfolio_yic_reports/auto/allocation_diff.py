"""Bucket allocation diff from ``portfolio_history.csv``."""

from dataclasses import dataclass
from datetime import date as dt_date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .dates import quarter_end_date, previous_quarter_end_date


@dataclass
class BucketChange:
    bucket: str
    was_pct: float
    now_pct: float
    change_pct: float
    value_change: float


@dataclass
class AllocationDiff:
    rows: List[BucketChange]
    start_date: dt_date
    end_date: dt_date
    start_total: float
    end_total: float


def _nearest_month_end(
    df: pd.DataFrame, target: dt_date
) -> Optional[dt_date]:
    """Return the latest month-end date in ``df`` that is <= ``target``."""
    available = sorted(df["date"].unique())
    best: Optional[dt_date] = None
    for d in available:
        if d <= target:
            best = d
        else:
            break
    return best


def load_portfolio_history(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def compute_allocation_diff(
    csv_path: Path, year: int, quarter: int
) -> AllocationDiff:
    """Compute bucket-level allocation changes for a quarter.

    Uses ``portfolio_history.csv`` month-end rows. ``start_date`` is the
    nearest month-end <= previous quarter end, ``end_date`` is the nearest
    month-end <= current quarter end.
    """
    df = load_portfolio_history(csv_path)
    end_boundary = quarter_end_date(year, quarter)
    start_boundary = previous_quarter_end_date(year, quarter)

    end_date = _nearest_month_end(df, end_boundary)
    start_date = _nearest_month_end(df, start_boundary)

    if end_date is None:
        raise ValueError(
            f"No portfolio_history.csv rows on or before quarter end "
            f"{end_boundary}"
        )
    if start_date is None:
        raise ValueError(
            f"No portfolio_history.csv rows on or before previous quarter "
            f"end {start_boundary}"
        )

    start_rows = df[df["date"] == start_date].set_index("asset_bucket")
    end_rows = df[df["date"] == end_date].set_index("asset_bucket")

    start_total = float(start_rows["market_value"].sum())
    end_total = float(end_rows["market_value"].sum())

    buckets = sorted(set(start_rows.index) | set(end_rows.index))
    rows: List[BucketChange] = []
    for bucket in buckets:
        was_val = float(start_rows.loc[bucket, "market_value"]) if bucket in start_rows.index else 0.0
        now_val = float(end_rows.loc[bucket, "market_value"]) if bucket in end_rows.index else 0.0
        was_pct = (was_val / start_total * 100) if start_total > 0 else 0.0
        now_pct = (now_val / end_total * 100) if end_total > 0 else 0.0
        rows.append(
            BucketChange(
                bucket=bucket,
                was_pct=was_pct,
                now_pct=now_pct,
                change_pct=now_pct - was_pct,
                value_change=now_val - was_val,
            )
        )

    return AllocationDiff(
        rows=rows,
        start_date=start_date,
        end_date=end_date,
        start_total=start_total,
        end_total=end_total,
    )