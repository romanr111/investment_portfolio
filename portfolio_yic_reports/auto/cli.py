"""CLI entry point: ``python -m portfolio_yic_reports.auto.cli``."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .config import ReportConfig
from .dates import last_completed_quarter
from .report_generator import generate_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Згенерувати квартальний звіт портфеля (YIC)."
    )
    parser.add_argument(
        "--year", type=int, help="Рік кварталу (за замовчуванням: останній завершений)."
    )
    parser.add_argument(
        "--quarter", type=int, choices=[1, 2, 3, 4],
        help="Номер кварталу (1-4).",
    )
    parser.add_argument(
        "--snapshot-start", default="",
        help="Шлях до XML snapshot на початок кварталу.",
    )
    parser.add_argument(
        "--snapshot-end", default="",
        help="Шлях до XML snapshot на кінець кварталу.",
    )
    parser.add_argument(
        "--skip-dalio", action="store_true",
        help="Не включати розділ Dalio.",
    )
    parser.add_argument(
        "--output-dir", default="",
        help="Директорія для збереження звіту.",
    )
    parser.add_argument(
        "--trades-xml", default="",
        help="Шлях до XML з trades за квартал (query Period=LastQuarter).",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.year and args.quarter:
        year, quarter = args.year, args.quarter
    elif args.year or args.quarter:
        parser.error("--year і --quarter треба вказувати разом.")
    else:
        year, quarter = last_completed_quarter()

    output_dir = Path(args.output_dir) if args.output_dir else None
    config = ReportConfig(
        snapshot_start=args.snapshot_start,
        snapshot_end=args.snapshot_end,
        skip_dalio=args.skip_dalio,
        trades_xml=args.trades_xml,
    )
    if output_dir is not None:
        config = ReportConfig(
            snapshots_dir=config.snapshots_dir,
            combined_data_dir=config.combined_data_dir,
            portfolio_history_csv=config.portfolio_history_csv,
            dalio_summary_json=config.dalio_summary_json,
            output_dir=output_dir,
            skip_dalio=config.skip_dalio,
            snapshot_start=config.snapshot_start,
            snapshot_end=config.snapshot_end,
            trades_xml=config.trades_xml,
        )

    try:
        generate_report(config, year, quarter)
    except ValueError as exc:
        print(f"Помилка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())