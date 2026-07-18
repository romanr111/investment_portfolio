"""Orchestrator: ties snapshots, allocation diff, metrics, Dalio, rendering."""

import logging
from dataclasses import dataclass
from pathlib import Path

from .allocation_diff import compute_allocation_diff
from .combined_loader import (
    extract_metrics,
    load_combined_snapshot,
    match_combined_snapshot,
)
from .config import ReportConfig
from .dalio_loader import extract_dalio_metrics, load_dalio_summary
from .dates import (
    match_snapshot,
    quarter_end_date,
    quarter_start_date,
)
from .flex_xml_parser import parse_snapshot
from .markdown_renderer import render_report

logger = logging.getLogger(__name__)


@dataclass
class ReportInputs:
    start_snap_path: Path
    end_snap_path: Path
    end_snapshot_date: str
    start_snapshot_date: str


def resolve_snapshots(
    config: ReportConfig, year: int, quarter: int
) -> ReportInputs:
    """Locate start/end snapshot XML files for a quarter."""
    if config.snapshot_start and config.snapshot_end:
        return ReportInputs(
            start_snap_path=Path(config.snapshot_start),
            end_snap_path=Path(config.snapshot_end),
            end_snapshot_date="",
            start_snapshot_date="",
        )

    end_boundary = quarter_end_date(year, quarter)
    start_boundary = quarter_start_date(year, quarter)

    end_path = match_snapshot(config.snapshots_dir, end_boundary)
    start_path = match_snapshot(config.snapshots_dir, start_boundary)

    if end_path is None:
        raise ValueError(
            f"No IB Flex snapshot XML found with toDate <= quarter end "
            f"{end_boundary} in {config.snapshots_dir}. Run the fetcher or "
            f"pass --snapshot-end."
        )
    if start_path is None:
        raise ValueError(
            f"No IB Flex snapshot XML found with toDate <= quarter start "
            f"{start_boundary} in {config.snapshots_dir}. Run the fetcher "
            f"or pass --snapshot-start."
        )

    return ReportInputs(
        start_snap_path=start_path,
        end_snap_path=end_path,
        end_snapshot_date="",
        start_snapshot_date="",
    )


def generate_report(
    config: ReportConfig, year: int, quarter: int
) -> Path:
    """Generate and save a quarterly report. Returns the output path."""
    inputs = resolve_snapshots(config, year, quarter)

    start_snap = parse_snapshot(str(inputs.start_snap_path))
    end_snap = parse_snapshot(str(inputs.end_snap_path))

    trades_snap = None
    if config.trades_xml:
        trades_snap = parse_snapshot(config.trades_xml)

    # Section 1: allocation diff from portfolio_history.csv
    allocation_diff = compute_allocation_diff(
        config.portfolio_history_csv, year, quarter
    )

    # Section 3: metrics from combined_data snapshots
    end_boundary = quarter_end_date(year, quarter)
    start_boundary = quarter_start_date(year, quarter)
    end_combined = match_combined_snapshot(config.combined_data_dir, end_boundary)
    start_combined = match_combined_snapshot(
        config.combined_data_dir, start_boundary
    )
    end_metrics = extract_metrics(load_combined_snapshot(end_combined))
    start_metrics = extract_metrics(load_combined_snapshot(start_combined))

    # Section 4: Dalio
    dalio_raw = {} if config.skip_dalio else load_dalio_summary(
        config.dalio_summary_json
    )
    dalio = extract_dalio_metrics(dalio_raw)

    markdown = render_report(
        year=year,
        quarter=quarter,
        start_snap=start_snap,
        end_snap=end_snap,
        allocation_diff=allocation_diff,
        start_metrics=start_metrics,
        end_metrics=end_metrics,
        dalio=dalio,
        skip_dalio=config.skip_dalio,
        trades_snap=trades_snap,
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.output_dir / f"REPORT_{year}_q{quarter}.md"
    out_path.write_text(markdown, encoding="utf-8")
    logger.info("Quarterly report written to %s", out_path)
    print(f"Звіт згенеровано: {out_path}")
    if end_combined is not None:
        print(
            f"  Метрики (Section 3) взято з combined_data: "
            f"{end_combined.name}"
        )
    else:
        print("  Попередження: combined_data snapshot для кінця кварталу не знайдено; "
              "Section 3 може бути неповною.")
    return out_path