"""Configuration constants for the auto report generator."""

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS_DIR = REPO_ROOT / "data" / "ib_flex_snapshots"
COMBINED_DATA_DIR = REPO_ROOT / "data" / "snapshots"
PORTFOLIO_HISTORY_CSV = REPO_ROOT / "data" / "portfolio_history.csv"
DALIO_SUMMARY_JSON = REPO_ROOT / "analytics" / "output" / "summary.json"
REPORTS_OUTPUT_DIR = REPO_ROOT / "portfolio_yic_reports"

SNAPSHOT_FILENAME_PREFIX = "stocks_count_trades_"
COMBINED_DATA_FILENAME_PREFIX = "combined_data_"

HKD_TO_USD_RATE = 0.128

CORE_SYMBOLS = {"VOO", "QQQ", "BRK B", "BN"}
CHINA_EQUITY_SYMBOLS = {"9988", "700", "KWEB", "PDD"}
CHINESE_STOCKS = {"9988", "700"}

BOND_TICKERS = {
    "SGOV", "TLT", "IEF", "SHY", "LQD", "VCIT", "VCSH", "IGLB",
    "HYG", "JNK", "USHY", "SHYG", "ANGL", "FALN", "SJNK", "HYLS",
    "HYGV", "HYDB", "GHYG", "SPHY", "IHYG", "EMB", "EMLC", "PCY",
    "AGG", "BND", "MUB", "VTIP",
}

PRECIOUS_METALS_TICKERS = {
    "GLD", "IAU", "SGOL", "PHYS", "BAR", "GLDM",
    "GDX", "GDXJ", "RING", "SLV", "PSLV",
}

SPECIAL_ASSET_TICKERS = sorted(
    BOND_TICKERS | PRECIOUS_METALS_TICKERS | {"COMB", "SGOV", "SLV"}
)

EXCLUDED_FROM_EQUITY = sorted(
    BOND_TICKERS | PRECIOUS_METALS_TICKERS | {"SGOV", "COMB", "SLV", "BILLS"}
)


@dataclass(frozen=True)
class ReportConfig:
    snapshots_dir: Path = SNAPSHOTS_DIR
    combined_data_dir: Path = COMBINED_DATA_DIR
    portfolio_history_csv: Path = PORTFOLIO_HISTORY_CSV
    dalio_summary_json: Path = DALIO_SUMMARY_JSON
    output_dir: Path = REPORTS_OUTPUT_DIR
    skip_dalio: bool = False
    snapshot_start: str = ""
    snapshot_end: str = ""