"""Quarter boundary and snapshot matching utilities."""

import calendar
import datetime as dt
from pathlib import Path
from typing import List, Optional, Tuple

from .config import SNAPSHOT_FILENAME_PREFIX


def last_completed_quarter(today: Optional[dt.date] = None) -> Tuple[int, int]:
    """Return (year, quarter) of the most recent fully completed quarter.

    A quarter is complete once its end date has passed. For example,
    Q1 2026 ends 2026-03-31 and is "completed" starting 2026-04-01.
    """
    today = today or dt.date.today()
    quarter = (today.month - 1) // 3 + 1
    first_month_of_quarter = (quarter - 1) * 3 + 1
    quarter_end_month = first_month_of_quarter + 2
    quarter_end_day = calendar.monthrange(today.year, quarter_end_month)[1]
    quarter_end = dt.date(today.year, quarter_end_month, quarter_end_day)

    if today > quarter_end:
        return today.year, quarter

    if quarter == 1:
        return today.year - 1, 4
    return today.year, quarter - 1


def quarter_end_date(year: int, quarter: int) -> dt.date:
    """Return the calendar end date of the given quarter."""
    end_month = quarter * 3
    last_day = calendar.monthrange(year, end_month)[1]
    return dt.date(year, end_month, last_day)


def quarter_start_date(year: int, quarter: int) -> dt.date:
    """Return the calendar start date of the given quarter."""
    start_month = (quarter - 1) * 3 + 1
    return dt.date(year, start_month, 1)


def previous_quarter_end_date(year: int, quarter: int) -> dt.date:
    """Return the end date of the quarter preceding the given one."""
    if quarter == 1:
        return quarter_end_date(year - 1, 4)
    return quarter_end_date(year, quarter - 1)


def format_quarter_ua(year: int, quarter: int) -> str:
    """Ukrainian display label, e.g. '1-й квартал 2026 року'."""
    suffix = "-й"
    if quarter == 3:
        suffix = "-ій"
    return f"{quarter}{suffix} квартал {year} року"


def parse_to_date(to_date_str: str) -> Optional[dt.date]:
    """Parse a YYYYMMDD string (Flex ``toDate``) into a date."""
    if not to_date_str or len(to_date_str) != 8:
        return None
    try:
        return dt.datetime.strptime(to_date_str, "%Y%m%d").date()
    except ValueError:
        return None


def parse_snapshot_filename_date(filename: str) -> Optional[dt.date]:
    """Extract the embedded ``<toDate>`` from a snapshot XML filename.

    Expected pattern: ``stocks_count_trades_YYYYMMDD_...xml``.
    """
    name = Path(filename).name
    if not name.startswith(SNAPSHOT_FILENAME_PREFIX):
        return None
    rest = name[len(SNAPSHOT_FILENAME_PREFIX):]
    date_part = rest.split("_", 1)[0]
    return parse_to_date(date_part)


def list_snapshots(snapshots_dir: Path) -> List[Path]:
    """List IB Flex portfolio snapshot XML files sorted by name ascending."""
    if not snapshots_dir.exists():
        return []
    files = sorted(
        p for p in snapshots_dir.iterdir()
        if p.is_file()
        and p.name.startswith(SNAPSHOT_FILENAME_PREFIX)
        and p.suffix == ".xml"
    )
    return files


def _snapshot_to_date(path: Path) -> Optional[dt.date]:
    """Return the effective date of a snapshot: XML ``toDate`` if parseable,
    otherwise the date embedded in the filename."""
    try:
        from .flex_xml_parser import parse_snapshot

        snap = parse_snapshot(str(path))
        to_date = parse_to_date(snap.to_date)
        if to_date is not None:
            return to_date
    except (OSError, ValueError):
        pass
    return parse_snapshot_filename_date(path.name)


def match_snapshot(
    snapshots_dir: Path, boundary_date: dt.date
) -> Optional[Path]:
    """Return the newest snapshot with ``toDate`` <= ``boundary_date``.

    Uses the XML ``toDate`` attribute when available and falls back to the
    filename-parsed date when the XML cannot be opened.
    """
    candidates = list_snapshots(snapshots_dir)
    best: Optional[Path] = None
    best_date: Optional[dt.date] = None
    for path in candidates:
        snap_date = _snapshot_to_date(path)
        if snap_date is None:
            continue
        if snap_date <= boundary_date:
            if best_date is None or snap_date > best_date:
                best = path
                best_date = snap_date
    return best
