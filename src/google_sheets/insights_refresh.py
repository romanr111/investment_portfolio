"""Local configuration and JSON snapshot replay for portfolio insights."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Optional


_CONFIG_KEYS = {
    "allocation_targets_pct",
    "fire_target_usd",
    "fire_eligible_categories",
    "essential_monthly_spending_usd",
    "liabilities_usd",
    "cash_available_now_usd",
    "assets_for_sale_usd",
    "restricted_assets_usd",
}
_SNAPSHOT_NAME = re.compile(r"combined_data_(\d{4}-\d{2}-\d{2})_(.+)\.json$")


@dataclass(frozen=True)
class SnapshotRecord:
    path: Path
    as_of_date: Optional[str]
    saved_at_utc: Optional[str]
    data: dict[str, Any]


def _parse_date(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _snapshot_date(payload: dict, path: Path, data: dict) -> Optional[str]:
    value = payload.get("as_of_date") or data.get("as_of_date")
    if value is None:
        metadata = data.get("DATA_METADATA")
        if isinstance(metadata, dict):
            value = metadata.get("last_updated")
    parsed = _parse_date(value)
    if parsed is not None:
        return parsed
    match = _SNAPSHOT_NAME.match(path.name)
    return match.group(1) if match else None


def load_snapshot(path: str | Path) -> SnapshotRecord:
    """Load either the saved snapshot envelope or a plain combined_data object."""
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Snapshot must contain a JSON object: {source_path}")
    raw_data = payload.get("data", payload)
    if not isinstance(raw_data, dict):
        raise ValueError(f"Snapshot data must contain a JSON object: {source_path}")
    return SnapshotRecord(
        path=source_path,
        as_of_date=_snapshot_date(payload, source_path, raw_data),
        saved_at_utc=payload.get("saved_at_utc"),
        data=raw_data,
    )


def _saved_sort_key(record: SnapshotRecord) -> tuple[str, str]:
    saved_at = record.saved_at_utc or ""
    return saved_at, record.path.name


def _read_snapshots(directory: Path) -> list[SnapshotRecord]:
    records = []
    for path in directory.glob("combined_data_*.json"):
        if path.name == "combined_data_latest.json":
            continue
        try:
            record = load_snapshot(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if record.as_of_date is not None:
            records.append(record)
    return records


def select_previous_snapshot(
    snapshot_dir: str | Path, current_date: Optional[str]
) -> Optional[SnapshotRecord]:
    """Choose the latest valid snapshot before the selected valuation date."""
    cutoff = _parse_date(current_date)
    if cutoff is None:
        return None
    directory = Path(snapshot_dir)
    candidates = [
        record
        for record in _read_snapshots(directory)
        if record.as_of_date is not None and record.as_of_date < cutoff
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda record: (record.as_of_date or "", *_saved_sort_key(record)))
    return candidates[-1]


def _latest_per_date(records: list[SnapshotRecord]) -> list[SnapshotRecord]:
    latest: dict[str, SnapshotRecord] = {}
    for record in records:
        if record.as_of_date is None:
            continue
        existing = latest.get(record.as_of_date)
        if existing is None or _saved_sort_key(record) > _saved_sort_key(existing):
            latest[record.as_of_date] = record
    return [latest[key] for key in sorted(latest)]


def load_insights_config(path: Optional[str | Path] = None) -> dict[str, Any]:
    """Read supported settings from an ignored local-only JSON file."""
    if path is not None:
        config_path = Path(path)
    elif os.environ.get("PORTFOLIO_INSIGHTS_CONFIG"):
        config_path = Path(os.environ["PORTFOLIO_INSIGHTS_CONFIG"])
    else:
        config_path = Path("data/insights_config.json")
    if not config_path.exists():
        return {}
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Insights config must be a JSON object")
    return {key: value for key, value in payload.items() if key in _CONFIG_KEYS}


def refresh_insights(
    spreadsheet: Any,
    combined_data: dict,
    config: Optional[dict[str, Any]] = None,
    snapshot_dir: str | Path = "data/snapshots",
) -> dict[str, Any]:
    """Build and write the eight generated insight tabs from saved pipeline data."""
    from src.google_sheets.insights_tables import build_insight_tabs
    from src.google_sheets.insights_writer import write_insight_tabs

    settings = config if config is not None else load_insights_config()
    current_date = (
        _parse_date(combined_data.get("as_of_date"))
        or _parse_date(
            combined_data.get("DATA_METADATA", {}).get("last_updated")
            if isinstance(combined_data.get("DATA_METADATA"), dict)
            else None
        )
    )
    records = _read_snapshots(Path(snapshot_dir))
    previous = select_previous_snapshot(snapshot_dir, current_date)
    history = [
        {"as_of_date": record.as_of_date, "data": record.data}
        for record in _latest_per_date(records)
        if current_date is None or (record.as_of_date or "") <= current_date
    ]
    if current_date is not None:
        history = [record for record in history if record["as_of_date"] != current_date]
    history.append({"as_of_date": current_date, "data": combined_data})
    tabs = build_insight_tabs(
        combined_data,
        config=settings,
        previous_snapshot=previous.data if previous else None,
        previous_date=previous.as_of_date if previous else None,
        current_date=current_date,
        history_snapshots=history,
    )
    return write_insight_tabs(spreadsheet, tabs)


def refresh_from_snapshot(
    spreadsheet: Any,
    snapshot_path: str | Path,
    config_path: Optional[str | Path] = None,
    snapshot_dir: str | Path = "data/snapshots",
) -> dict[str, Any]:
    """Replay saved data without calling any broker or other data source."""
    snapshot = load_snapshot(snapshot_path)
    combined_data = deepcopy(snapshot.data)
    metadata = combined_data.get("DATA_METADATA")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata["source"] = "cached_snapshot"
    if snapshot.saved_at_utc:
        try:
            saved_at = datetime.fromisoformat(snapshot.saved_at_utc.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - saved_at.astimezone(timezone.utc)).total_seconds()
            metadata["age_seconds"] = max(age, 0.0)
        except ValueError:
            metadata.pop("age_seconds", None)
    combined_data["DATA_METADATA"] = metadata
    return refresh_insights(
        spreadsheet,
        combined_data,
        config=load_insights_config(config_path),
        snapshot_dir=snapshot_dir,
    )
