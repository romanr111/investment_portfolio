import argparse
import time
import logging
import sys
import traceback
from pathlib import Path
from typing import Optional

import pandas as pd

from analytics.dalio_holy_grail import DalioHolyGrailAnalyzer
from src.google_sheets.spreadsheet_structure import update_portfolio_spreadsheet
from src.logging.portfolio_logger import (
    log_portfolio_data,
    log_portfolio_metadata,
)
from src.data_source import DataSource
from src.allocation_calculator import AllocationCalculator
from src.portfolio_history.unified_history import (
    save_combined_data_snapshot_json,
    sync_unified_history_from_google_sheets,
)

#
# cd Documents/Development/investment_portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#

CREDENTIALS_PATH = "data/credentials.json"
SPREADSHEET_NAME = "portfolio_automated"
SNAPSHOT_DIR = "data/snapshots"
UNIFIED_HISTORY_CSV_PATH = "data/portfolio_history.csv"
UNIFIED_HISTORY_JSONL_PATH = "data/portfolio_history.jsonl"
DALIO_OUTPUT_DIR = "analytics/output"

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_factor_returns(path: Optional[str]) -> Optional[pd.DataFrame]:
    if not path:
        return None
    factor_path = Path(path)
    if not factor_path.exists():
        raise FileNotFoundError(f"Layer B factor CSV not found: {factor_path}")
    return pd.read_csv(factor_path)
def _parse_layer_a_windows(raw_windows: str) -> tuple[int, ...]:
    windows = []
    for token in raw_windows.split(","):
        token = token.strip()
        if not token:
            continue
        windows.append(int(token))
    if not windows:
        raise ValueError("Layer A windows must contain at least one integer.")
    positive_unique = sorted({window for window in windows if window > 0})
    if not positive_unique:
        raise ValueError("Layer A windows must be positive integers.")
    return tuple(positive_unique)


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch live portfolio data, update Google Sheets, and export unified history."
    )
    parser.add_argument(
        "--credentials-path",
        default=CREDENTIALS_PATH,
        help="Path to Google service account credentials JSON.",
    )
    parser.add_argument(
        "--spreadsheet-name",
        default=SPREADSHEET_NAME,
        help="Google Sheets document name.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=SNAPSHOT_DIR,
        help="Directory for dated combined_data JSON snapshots.",
    )
    parser.add_argument(
        "--history-csv-path",
        default=UNIFIED_HISTORY_CSV_PATH,
        help="Output CSV path for unified historical portfolio data.",
    )
    parser.add_argument(
        "--history-jsonl-path",
        default=UNIFIED_HISTORY_JSONL_PATH,
        help="Output JSONL path for unified historical portfolio data.",
    )
    parser.add_argument(
        "--history-currency",
        default="USD",
        help="Currency code written to unified history files.",
    )
    parser.add_argument(
        "--history-return-source",
        choices=["blank", "pct-change"],
        default="blank",
        help=(
            "How return_pct is populated in unified history. "
            "'blank' keeps return_pct empty; 'pct-change' computes from market_value."
        ),
    )
    parser.add_argument(
        "--history-frequency",
        choices=["monthly", "raw"],
        default="monthly",
        help=(
            "History date normalization mode. "
            "'monthly' keeps only latest tab per month and stamps month-end date; "
            "'raw' preserves original tab dates."
        ),
    )
    parser.add_argument(
        "--history-start-date",
        default=None,
        help="Optional lower bound for history sync (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--history-end-date",
        default=None,
        help="Optional upper bound for history sync (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--history-strict-required-buckets",
        action="store_true",
        help="Require all core Dalio buckets for every synced date.",
    )
    parser.add_argument(
        "--history-include-zero-positions",
        action="store_true",
        help="Include rows with market_value == 0 while syncing history.",
    )
    parser.add_argument(
        "--skip-history-sync",
        action="store_true",
        help="Skip downloading retrospective unified history from Google Sheets.",
    )
    parser.add_argument(
        "--skip-sheet-update",
        action="store_true",
        help="Skip writing the latest snapshot tab to Google Sheets.",
    )
    parser.add_argument(
        "--skip-dalio-analysis",
        action="store_true",
        help="Skip Dalio Holy Grail analysis at the end of the run.",
    )
    parser.add_argument(
        "--dalio-input-csv",
        default=None,
        help=(
            "Optional input CSV for Dalio analyzer. "
            "Defaults to --history-csv-path."
        ),
    )
    parser.add_argument(
        "--dalio-output-dir",
        default=DALIO_OUTPUT_DIR,
        help="Output directory for Dalio analyzer result tables.",
    )
    parser.add_argument(
        "--dalio-base-currency",
        default="USD",
        help="Base currency used by Dalio analyzer.",
    )
    parser.add_argument(
        "--dalio-corr-threshold",
        type=float,
        default=0.6,
        help="Correlation threshold for Dalio management rules.",
    )
    parser.add_argument(
        "--dalio-max-risk-contribution",
        type=float,
        default=0.25,
        help="Max risk contribution per bucket for Dalio management rules.",
    )
    parser.add_argument(
        "--dalio-drift-threshold",
        type=float,
        default=0.20,
        help="Weight drift threshold for Dalio management rules.",
    )
    parser.add_argument(
        "--dalio-return-unit",
        choices=["decimal", "percent"],
        default="decimal",
        help="Input unit for return_pct in Dalio analyzer input CSV.",
    )
    parser.add_argument(
        "--dalio-covariance-method",
        choices=["sample", "ewma"],
        default="sample",
        help="Covariance method used in Dalio analyzer.",
    )
    parser.add_argument(
        "--dalio-ewma-alpha",
        type=float,
        default=0.06,
        help="EWMA alpha for Dalio analyzer (used with ewma covariance).",
    )
    parser.add_argument(
        "--dalio-min-pair-overlap",
        type=int,
        default=24,
        help="Minimum overlap observations for Dalio pair confidence.",
    )
    parser.add_argument(
        "--dalio-min-covariance-observations",
        type=int,
        default=12,
        help="Minimum observations required for covariance estimation.",
    )
    parser.add_argument(
        "--dalio-factor-input-csv",
        default=None,
        help=(
            "Optional wide CSV with Layer B factor returns. "
            "Required columns: date,growth,inflation,real_rates,credit_liquidity."
        ),
    )
    parser.add_argument(
        "--dalio-layer-b-window-months",
        type=int,
        default=36,
        help="Rolling window size (months) for Layer B factor modeling.",
    )
    parser.add_argument(
        "--dalio-layer-b-min-observations",
        type=int,
        default=24,
        help="Minimum aligned observations needed for Layer B OLS.",
    )
    parser.add_argument(
        "--dalio-layer-b-require-data",
        action="store_true",
        help="Require factor input CSV and fail if Layer B cannot run.",
    )
    parser.add_argument(
        "--dalio-layer-b-collinearity-cond-threshold",
        type=float,
        default=30.0,
        help="Condition number threshold for Layer B collinearity flag.",
    )
    parser.add_argument(
        "--dalio-layer-b-vif-threshold",
        type=float,
        default=10.0,
        help="VIF threshold for Layer B collinearity flag.",
    )
    parser.add_argument(
        "--dalio-layer-b-max-factor-trc-share",
        type=float,
        default=0.35,
        help="Alert threshold for max factor TRC share (fraction).",
    )
    parser.add_argument(
        "--dalio-layer-b-factor-hhi-threshold",
        type=float,
        default=0.35,
        help="Alert threshold for factor HHI concentration.",
    )
    parser.add_argument(
        "--dalio-layer-b-residual-share-threshold",
        type=float,
        default=0.40,
        help="Alert threshold for residual risk share (fraction).",
    )
    parser.add_argument(
        "--dalio-layer-b-min-coverage-pct",
        type=float,
        default=80.0,
        help="Alert threshold for minimum factor coverage percentage.",
    )
    parser.add_argument(
        "--dalio-layer-a-windows",
        default="12,24,36",
        help="Comma-separated rolling windows (months) for Layer A metrics.",
    )
    parser.add_argument(
        "--dalio-layer-a-high-corr-threshold",
        type=float,
        default=0.70,
        help="Pair-level absolute correlation threshold used in Layer A metrics.",
    )
    parser.add_argument(
        "--dalio-layer-a-cluster-corr-cutoff",
        type=float,
        default=0.70,
        help="Correlation cutoff for NumPy HAC clustering in Layer A.",
    )
    parser.add_argument(
        "--dalio-layer-a-trc-max-share",
        type=float,
        default=0.35,
        help="Maximum allowed absolute TRC share (fraction) before Layer A alert.",
    )
    parser.add_argument(
        "--dalio-layer-a-min-n-rc",
        type=float,
        default=4.0,
        help="Minimum effective number of risk contributors before Layer A alert.",
    )
    parser.add_argument(
        "--dalio-layer-a-primary-window",
        type=int,
        default=36,
        help="Primary Layer A rolling window used for summary alerts.",
    )
    return parser


def _run_dalio_analysis(args: argparse.Namespace) -> None:
    input_csv = args.dalio_input_csv or args.history_csv_path
    input_path = Path(input_csv)
    if not input_path.exists():
        raise FileNotFoundError(
            "Dalio analyzer input CSV not found: {}. "
            "Run history sync or provide --dalio-input-csv.".format(input_path)
        )

    dataset = pd.read_csv(input_path)
    analyzer = DalioHolyGrailAnalyzer(
        dataset,
        base_currency=args.dalio_base_currency,
        factor_returns=_load_factor_returns(args.dalio_factor_input_csv),
        return_unit=args.dalio_return_unit,
        covariance_method=args.dalio_covariance_method,
        ewma_alpha=args.dalio_ewma_alpha,
        min_pair_overlap=args.dalio_min_pair_overlap,
        min_covariance_observations=args.dalio_min_covariance_observations,
        layer_b_window_months=args.dalio_layer_b_window_months,
        layer_b_min_observations=args.dalio_layer_b_min_observations,
        layer_b_require_data=args.dalio_layer_b_require_data,
        layer_b_collinearity_cond_threshold=args.dalio_layer_b_collinearity_cond_threshold,
        layer_b_vif_threshold=args.dalio_layer_b_vif_threshold,
        layer_b_max_factor_trc_share=args.dalio_layer_b_max_factor_trc_share,
        layer_b_factor_hhi_threshold=args.dalio_layer_b_factor_hhi_threshold,
        layer_b_residual_share_threshold=args.dalio_layer_b_residual_share_threshold,
        layer_b_min_coverage_pct=args.dalio_layer_b_min_coverage_pct,
        layer_a_windows=_parse_layer_a_windows(args.dalio_layer_a_windows),
        layer_a_high_corr_threshold=args.dalio_layer_a_high_corr_threshold,
        layer_a_cluster_corr_cutoff=args.dalio_layer_a_cluster_corr_cutoff,
        layer_a_trc_max_share_threshold=args.dalio_layer_a_trc_max_share,
        layer_a_min_n_rc=args.dalio_layer_a_min_n_rc,
        layer_a_primary_window=args.dalio_layer_a_primary_window,
    )
    result = analyzer.run_analysis(
        corr_threshold=args.dalio_corr_threshold,
        max_risk_contribution=args.dalio_max_risk_contribution,
        drift_threshold=args.dalio_drift_threshold,
    )
    analyzer.save_result_tables(result, args.dalio_output_dir)

    print("Dalio analysis complete.")
    print("Diversification metrics:", result.diversification_metrics)
    print("Management rules:", result.management_rules)
    logger.info(
        "Dalio analysis complete. input=%s output_dir=%s",
        input_path,
        args.dalio_output_dir,
    )


def main() -> int:
    args = _build_cli().parse_args()
    logger.debug("Starting main function")
    try:
        logger.debug("Initializing DataSource")
        data_source = DataSource()
        logger.debug("DataSource initialization completed")

        logger.debug("Collecting combined data snapshot")
        combined_data = data_source.get_combined_data()
        snapshot_file = save_combined_data_snapshot_json(
            combined_data,
            output_dir=args.snapshot_dir,
        )
        logger.info("Saved combined_data snapshot to %s", snapshot_file)

        # Preserve historical behavior: data for sheet includes allocations.
        data = dict(combined_data)
        data["ALLOCATIONS"] = AllocationCalculator(data).get_sorted_sector_allocations()
        logger.debug("Prepared sheet payload with allocations")

        # Get the IB client from the DataSource if available
        ib_client = None
        try:
            if hasattr(data_source, "ib") and data_source.ib:
                ib_client = data_source.ib
                enhanced_stocks = ib_client.get_stock_positions_analytics()
                log_portfolio_data(enhanced_stocks)
        except Exception as e:
            logger.warning(f"Could not get IB client or print enhanced data: {str(e)}")
            ib_client = None

        if not args.skip_sheet_update:
            logger.debug("Updating portfolio in Google Sheets")
            # Check if enhanced stock data already exists in the data
            if "ENHANCED_STOCKS" in data and not ib_client:
                enhanced_stocks = data["ENHANCED_STOCKS"]
                metadata = enhanced_stocks.get("metadata", {})
                if metadata:
                    log_portfolio_metadata(metadata)

            # Use the update_portfolio_spreadsheet function directly with the IB client
            update_portfolio_spreadsheet(
                data,
                args.credentials_path,
                args.spreadsheet_name,
                ib_client,
            )
            logger.debug("Portfolio sheet update completed")
        else:
            logger.info("Skipping sheet update by flag")

        if not args.skip_history_sync:
            logger.debug("Syncing retrospective unified history from Google Sheets")
            history_df = sync_unified_history_from_google_sheets(
                credentials_path=args.credentials_path,
                spreadsheet_name=args.spreadsheet_name,
                output_csv_path=args.history_csv_path,
                output_jsonl_path=args.history_jsonl_path,
                currency=args.history_currency,
                return_source=args.history_return_source,
                strict_required_buckets=args.history_strict_required_buckets,
                include_zero_positions=args.history_include_zero_positions,
                history_frequency=args.history_frequency,
                start_date=args.history_start_date,
                end_date=args.history_end_date,
            )
            logger.info(
                "Unified history saved: %s rows, %s dates -> %s",
                len(history_df),
                history_df["date"].nunique() if not history_df.empty else 0,
                args.history_csv_path,
            )
        else:
            logger.info("Skipping history sync by flag")

        if not args.skip_dalio_analysis:
            logger.debug("Running Dalio Holy Grail analysis")
            _run_dalio_analysis(args)
        else:
            logger.info("Skipping Dalio analysis by flag")
    except Exception as e:
        logger.error(f"Error in main function: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return 1
    return 0


if __name__ == "__main__":
    logger.info("Starting portfolio update process")
    logger.info("Python version: " + sys.version)

    start_time = time.time()
    try:
        exit_code = main()
        if exit_code != 0:
            raise SystemExit(exit_code)
        logger.info("Portfolio update process completed successfully")
    except Exception as e:
        logger.error(f"Top-level exception in main script: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"--- TOTAL: {elapsed_time:.2f} seconds ---")
