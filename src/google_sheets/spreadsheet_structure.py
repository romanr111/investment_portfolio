import gspread
from google.oauth2.service_account import Credentials
from decimal import Decimal
from typing import List, Dict, Any
from .formatting import DataFormatter


class GoogleSheetsClient:
    """Handles Google Sheets authentication and worksheet operations."""

    def __init__(self, credentials_path: str):
        self.credentials_path = credentials_path
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        self.client = self._initialize_client()

    def _initialize_client(self) -> gspread.Client:
        """Initialize and return an authorized gspread client."""
        credentials = Credentials.from_service_account_file(
            self.credentials_path, scopes=self.scopes
        )
        return gspread.authorize(credentials)

    def open_spreadsheet(self, spreadsheet_name: str) -> gspread.Spreadsheet:
        """Open and return a spreadsheet by name."""
        return self.client.open(spreadsheet_name)


class PortfolioDataParser:
    """Parses different types of portfolio data."""

    @staticmethod
    def parse_ib_data(ib_data: Dict) -> List[List[str]]:
        """Parse IB data into rows."""
        rows = []
        for subcat, contents in ib_data.items():
            if isinstance(contents, dict) and not contents:
                continue

            if isinstance(contents, dict):
                rows.append(DataFormatter.row_left(subcat))
                for sym, val in contents.items():
                    rows.append(DataFormatter.row_left(sym, str(val)))
                rows.append(DataFormatter.row_left())
            else:
                rows.append(DataFormatter.row_left(subcat, str(contents)))
                rows.append(DataFormatter.row_left())
        return rows

    @staticmethod
    def parse_crypto_data(crypto_data: Dict) -> List[List[str]]:
        """Parse crypto data into rows."""
        rows = []
        rows.append(DataFormatter.row_left("CRYPTO_DATA"))

        total_crypto = crypto_data.get("Total_Crypto_Value", 0)
        rows.append(DataFormatter.row_left("Total Crypto Value", str(total_crypto)))
        rows.append(DataFormatter.row_left())

        market_vals = crypto_data.get("Crypto_Market_Values", {})
        if market_vals:
            rows.append(DataFormatter.row_left("Market Values"))
            for sym, val in market_vals.items():
                rows.append(DataFormatter.row_left(sym, str(val)))
            rows.append(DataFormatter.row_left())

        return rows

    @staticmethod
    def parse_cash_data(cash_data: Dict) -> List[List[str]]:
        """Parse cash data into rows."""
        rows = []
        total_val = cash_data.get("Total", 0)
        if isinstance(total_val, Decimal):
            total_val = float(total_val)
        rows.append(DataFormatter.row_left("CASH_DATA (total)", str(total_val)))
        rows.append(DataFormatter.row_left())
        return rows


class PortfolioUpdater:
    """Main class for updating portfolio spreadsheet."""

    def __init__(self, credentials_path: str, spreadsheet_name: str):
        self.sheets_client = GoogleSheetsClient(credentials_path)
        self.spreadsheet = self.sheets_client.open_spreadsheet(spreadsheet_name)

    def update_portfolio(
        self,
        data: Dict[str, Any],
        *,
        valuation_date=None,
        config=None,
        adoptions=None,
        dry_run=False,
    ) -> dict:
        """Render saved data into one dated tab and the shared timeline."""
        from .insights_refresh import refresh_insights

        return refresh_insights(
            self.spreadsheet,
            data,
            config=config,
            valuation_date=valuation_date,
            adoptions=adoptions,
            dry_run=dry_run,
        )


def update_portfolio_spreadsheet(
    data: Dict[str, Any],
    credentials_path: str,
    spreadsheet_name: str,
    ib_client=None,
    *,
    valuation_date=None,
    config=None,
    adoptions=None,
    dry_run=False,
) -> dict:
    """
    Convenience function for updating portfolio.

    Args:
        data: Dictionary containing portfolio data
        credentials_path: Path to the Google API credentials file
        spreadsheet_name: Name of the Google Sheet to update
        ib_client: Accepted for compatibility; saved analytics are used instead
    """
    # ib_client remains accepted for caller compatibility; rendering never uses it.
    updater = PortfolioUpdater(credentials_path, spreadsheet_name)
    return updater.update_portfolio(
        data,
        valuation_date=valuation_date,
        config=config,
        adoptions=adoptions,
        dry_run=dry_run,
    )


def create_enhanced_stocks_data(
    china_stocks: Dict[str, Dict[str, Any]] = None,
    regular_stocks: Dict[str, Dict[str, Any]] = None,
    precious_metals: Dict[str, Dict[str, Any]] = None,
    metadata: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Create enhanced stocks data structure from raw data.

    This function allows creating the enhanced stocks data structure without requiring
    the InteractiveBrokers client, useful for testing or when constructing data manually.

    Args:
        china_stocks: Dictionary mapping stock symbols to position details for China stocks
        regular_stocks: Dictionary mapping stock symbols to position details for regular stocks
        precious_metals: Dictionary mapping metal symbols to position details
        metadata: Dictionary containing metadata about the stock positions

    Returns:
        Enhanced stocks data structure compatible with the spreadsheet builder
    """
    # Initialize with empty dictionaries if not provided
    china_stocks = china_stocks or {}
    regular_stocks = regular_stocks or {}
    precious_metals = precious_metals or {}
    metadata = metadata or {}

    # Create the structure
    enhanced_data = {
        "China Stocks": china_stocks,
        "Stocks": regular_stocks,
        "Precious Metals": precious_metals,
        "metadata": metadata,
    }

    # Ensure required metadata fields exist
    if "total_stocks_value" not in metadata:
        metadata["total_stocks_value"] = 0
    if "china_stocks_value" not in metadata:
        metadata["china_stocks_value"] = 0
    if "regular_stocks_value" not in metadata:
        metadata["regular_stocks_value"] = 0
    if "total_portfolio_value" not in metadata:
        metadata["total_portfolio_value"] = 0
    if "total_cost_basis" not in metadata:
        metadata["total_cost_basis"] = 0
    if "total_unrealized_pnl" not in metadata:
        metadata["total_unrealized_pnl"] = 0
    if "total_unrealized_pnl_percentage" not in metadata:
        metadata["total_unrealized_pnl_percentage"] = 0

    return enhanced_data


if __name__ == "__main__":
    CREDENTIALS_PATH = "data/credentials.json"
    SPREADSHEET_NAME = "portfolio_automated"

    portfolio_data = {
        "IB_DATA": {
            "Bonds": {
                "IBCID746579811": 29667,
                "IBCID722427489": 22887,
                "TLT": 3503,
                "SGOV": 1706,
            },
            "China Stocks": {"700": 5376, "9988": 5309, "KWEB": 3880, "PDD": 971},
            "Stocks": {
                "C": 3793,
                "GOOG": 3626,
                "NKE": 3476,
                "BN": 2236,
                "CVS": 1997,
                "COP": 1880,
                "COF": 1781,
                "HUM": 1762,
                "CVX": 1739,
                "INTC": 1435,
                "IBKR": 1096,
                "ADBE": 887,
                "CP": 798,
                "UPS": 755,
            },
            "Short Selling": {},
            "REIT": {},
            "Gold": {"IAU": 545},
            "Commodities": {"COMB": 2591},
            "Total Stocks Value": 42797,
            "Net_cash": 194,
            "IB_Portfolio_Value": 103890,
        },
        "CRYPTO_DATA": {
            "Total_Crypto_Value": 6232,
            "Crypto_Market_Values": {
                "BTC": 3750,
                "ETH": 2051,
                "TON": 99,
                "ADA": 88,
                "BNB": 83,
                "EOS": 70,
                "NEO": 68,
                "SC": 23,
            },
            "Token_Quantities": {
                "BTC": 0.04,
                "ETH": 0.6129,
                "BNB": 0.1183,
                "ADA": 103.5339,
                "LUNA": 0.2025,
                "TON": 17.9409,
                "BANANA": 0.0062,
                "DOGS": 101.87,
                "HMSTR": 15.96,
                "CATI": 0.4943,
                "SCR": 0.2952,
                "USUAL": 1.622,
                "THE": 0.1729,
                "MOVE": 1.6477,
                "VANA": 0.0271,
                "PENGU": 20.4154,
                "1000CAT": 8.7506,
                "AVAX": 0.0096,
                "COMP": 0.0443,
                "UAH": 0.2925,
                "EOS": 90,
                "NEO": 5,
                "SC": 4343,
            },
        },
        "FIXED_INCOME_DATA": {
            "group_weighted_interest": {
                "Bonds": (57763, 0.041),
                "Crypto Landing": (24364, 0.114),
                "p2p_lending": (3508, 0.079),
            },
            "calculated_income": {
                "Bonds": 2368,
                "Crypto Landing": 2777,
                "p2p_lending": 277,
            },
            "fixed_inc_principal_and_interest": {"principal": 85635, "interest": 0.063},
            "monthly_earnings_fixed_income": 451,
            "yearly_earnings_fixed_income": 5422,
            "fixed_income_full_data": {
                "Bonds": {
                    "IBCID746579811": (29667, 0.044),
                    "IBCID722427489": (22887, 0.044),
                    "TLT": (3503, 0.0),
                    "SGOV": (1706, 0.045),
                },
                "Crypto Landing": {
                    "binance": {
                        "EURI": (503, 0.085),
                        "USDC": (1004, 0.077),
                        "USDT": (3923, 0.057),
                    },
                    "okx": {"USDT": (3051, 0.058), "USDC": (3569, 0.105)},
                    "bybit": {"USDC": (503, 0.138), "USDT": (543, 0.107)},
                    "whitebit": {"USDT": (3864, 0.156), "USDC": (7404, 0.156)},
                },
                "p2p_lending": {"EstateGuru": (3224, 0.08), "PeerBerry": (284, 0.068)},
            },
            "stocks_principal_and_interest": {
                "total_principal": 42797,
                "weighted_interest": 1.84,
            },
            "stocks_monthly": 65,
            "stocks_yearly": 788,
            "total_monthly": 516,
            "total_yearly": 6210,
        },
        "CASH_DATA": {
            "Total": Decimal("2579"),
            "Breakdown": {
                "cash": Decimal("910"),
                "lended": Decimal("1674"),
                "debt": Decimal("0"),
                "private": Decimal("-738"),
                "ib_cash": Decimal("194"),
                "crypto_cash": Decimal("1"),
                "mono": Decimal("538"),
                "wise": Decimal("0"),
            },
        },
        "TOTAL_ASSETS": 140573,
        "FIN_FREEDOM_GOAL_PROGRESS": "28.11%",
        "ALLOCATIONS": {
            "allocation_breakdown": {
                "Bonds": 41.24,
                "Stocks": 30.44,
                "Crypto Lending": 17.33,
                "Crypto Coins": 4.43,
                "P2P Lending": 2.5,
                "Commodities": 1.84,
                "Cash": 1.83,
                "Gold": 0.39,
                "REIT": 0.0,
            },
            "total_fixed_income_pct": 60.92,
        },
    }

    update_portfolio(portfolio_data, CREDENTIALS_PATH, SPREADSHEET_NAME)
