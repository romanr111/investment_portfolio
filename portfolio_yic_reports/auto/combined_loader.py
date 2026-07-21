"""Load Section 3 metrics (YTD TWR, dividends, freedom progress) from
``combined_data_*.json`` snapshots.
"""

import json
import logging
import re
from datetime import date as dt_date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import COMBINED_DATA_FILENAME_PREFIX

logger = logging.getLogger(__name__)

_TIMESTAMP_RE = re.compile(r"_(\d{8})T(\d{6})Z$")


def _parse_combined_filename_date(name: str) -> Optional[dt_date]:
    """Extract the embedded date from a ``combined_data_YYYY-MM-DD_...json``."""
    stem = Path(name).stem
    if not stem.startswith(COMBINED_DATA_FILENAME_PREFIX):
        return None
    rest = stem[len(COMBINED_DATA_FILENAME_PREFIX):]
    date_part = rest.split("_", 1)[0]
    try:
        return datetime.strptime(date_part, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_combined_filename_timestamp(name: str) -> Optional[datetime]:
    """Extract the embedded ``YYYYMMDDTHHMMSSZ`` timestamp from a
    ``combined_data_YYYY-MM-DD_YYYYMMDDTHHMMSSZ.json`` filename.

    Returns None for files without a timestamp suffix (e.g. the
    canonical ``combined_data_YYYY-MM-DD.json``). Such files are
    treated as *earlier* than any timestamped sibling of the same date.
    """
    stem = Path(name).stem
    m = _TIMESTAMP_RE.search(stem)
    if m is None:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _sort_key(path: Path) -> Tuple[dt_date, datetime]:
    """Sort key: (embedded date, embedded timestamp or datetime.min).

    Files without a timestamp suffix sort before timestamped siblings
    of the same date, so the latest timestamped snapshot wins on ties.
    """
    d = _parse_combined_filename_date(path.name) or dt_date.min
    ts = _parse_combined_filename_timestamp(path.name)
    return (d, ts or datetime.min)


def list_combined_snapshots(directory: Path) -> List[Path]:
    if not directory.exists():
        return []
    files = [
        p
        for p in directory.iterdir()
        if p.is_file()
        and p.name.startswith(COMBINED_DATA_FILENAME_PREFIX)
        and p.suffix == ".json"
        and p.name != "combined_data_latest.json"
    ]
    files.sort(key=_sort_key)
    return files


def match_combined_snapshot(
    directory: Path, boundary_date: dt_date
) -> Optional[Path]:
    """Latest combined_data snapshot with embedded date <= ``boundary_date``.

    When multiple snapshots share the same embedded date, the one with
    the latest filename-embedded timestamp wins. This prefers the most
    recent (and typically most complete) re-run for that date.
    """
    candidates = list_combined_snapshots(directory)
    best: Optional[Path] = None
    best_key: Optional[Tuple[dt_date, datetime]] = None
    for path in candidates:
        d = _parse_combined_filename_date(path.name)
        if d is None or d > boundary_date:
            continue
        key = _sort_key(path)
        if best_key is None or key > best_key:
            best = path
            best_key = key
    return best


def load_combined_snapshot(path: Optional[Path]) -> Dict:
    if path is None or not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load combined_data snapshot %s: %s", path, exc)
        return {}


def extract_metrics(data: Dict) -> Dict:
    """Extract Section 3 metrics from a combined_data payload."""
    inner = data.get("data", {}) if isinstance(data, dict) else {}
    perf = inner.get("IB_PERFORMANCE", {}) if isinstance(inner, dict) else {}
    fixed_income = (
        inner.get("FIXED_INCOME_DATA", {}) if isinstance(inner, dict) else {}
    )
    index_perf = (
        inner.get("INDEX_PERFORMANCE", {}) if isinstance(inner, dict) else {}
    )
    sp500 = index_perf.get("SP500") if isinstance(index_perf, dict) else None
    nasdaq = index_perf.get("NASDAQ") if isinstance(index_perf, dict) else None
    benchmark_ytd_pct = None
    if isinstance(sp500, dict):
        rate = sp500.get("rate_of_return_pct")
        if rate is not None:
            benchmark_ytd_pct = rate
    benchmark_nasdaq_ytd_pct = None
    if isinstance(nasdaq, dict):
        rate = nasdaq.get("rate_of_return_pct")
        if rate is not None:
            benchmark_nasdaq_ytd_pct = rate
    return {
        "as_of_date": data.get("as_of_date"),
        "twr": perf.get("rate_of_return_pct"),
        "dividends_yearly": fixed_income.get("total_yearly"),
        "income_total_yearly": fixed_income.get("total_yearly"),
        "income_stocks_yearly": fixed_income.get("stocks_yearly"),
        "income_fixed_yearly": fixed_income.get("yearly_earnings_fixed_income"),
        "benchmark_ytd_pct": benchmark_ytd_pct,
        "benchmark_nasdaq_ytd_pct": benchmark_nasdaq_ytd_pct,
        "freedom_progress": inner.get("FIN_FREEDOM_GOAL_PROGRESS"),
        "total_assets": inner.get("TOTAL_ASSETS"),
    }