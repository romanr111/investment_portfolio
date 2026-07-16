"""Load Section 3 metrics (YTD TWR, dividends, freedom progress) from
``combined_data_*.json`` snapshots.
"""

import json
import logging
from datetime import date as dt_date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import COMBINED_DATA_FILENAME_PREFIX

logger = logging.getLogger(__name__)


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
    files.sort(key=lambda p: _parse_combined_filename_date(p.name) or dt_date.min)
    return files


def match_combined_snapshot(
    directory: Path, boundary_date: dt_date
) -> Optional[Path]:
    """Newest combined_data snapshot with embedded date <= ``boundary_date``."""
    candidates = list_combined_snapshots(directory)
    best: Optional[Path] = None
    best_date: Optional[dt_date] = None
    for path in candidates:
        d = _parse_combined_filename_date(path.name)
        if d is None:
            continue
        if d <= boundary_date:
            if best_date is None or d > best_date:
                best = path
                best_date = d
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
    return {
        "as_of_date": data.get("as_of_date"),
        "twr": perf.get("rate_of_return_pct"),
        "dividends_yearly": fixed_income.get("total_yearly"),
        "freedom_progress": inner.get("FIN_FREEDOM_GOAL_PROGRESS"),
        "total_assets": inner.get("TOTAL_ASSETS"),
    }