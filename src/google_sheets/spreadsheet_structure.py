import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, Union, Tuple
import logging
from .formatting import (
    DataFormatter,
    PortfolioFormatter,
    TimelineFormatter,
    SpreadsheetFormatter,
)
from data.assets_data import OTHER_BETS


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


class PortfolioSpreadsheet:
    """Manages portfolio data in Google Sheets."""

    def __init__(self, spreadsheet: gspread.Spreadsheet):
        self.spreadsheet = spreadsheet

    def create_tab_at_left(self, sheet_title: str) -> gspread.Worksheet:
        """Create or replace a worksheet at index=1."""
        try:
            existing = self.spreadsheet.worksheet(sheet_title)
            self.spreadsheet.del_worksheet(existing)
        except gspread.exceptions.WorksheetNotFound:
            pass

        worksheet = self.spreadsheet.add_worksheet(title=sheet_title, rows=200, cols=30)
        self.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": worksheet.id, "index": 1},
                            "fields": "index",
                        }
                    }
                ]
            }
        )
        return worksheet


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


class PortfolioTableBuilder:
    """Builds complete portfolio tables."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.category_header_rows = []  # Track rows with category headers

    def build_left_columns(self) -> List[List[str]]:
        """Build columns D/E data with enhanced stock percentage display."""
        rows = []
        self.category_header_rows = []  # Reset the tracker

        ib_data = self.data.get("IB_DATA", {})
        enhanced_stocks = self.data.get("ENHANCED_STOCKS", {})

        if ib_data:
            # Calculate stock values and percentages
            china_stocks = ib_data.get("China Stocks", {})
            regular_stocks = ib_data.get("Stocks", {})
            china_stocks_value = sum(china_stocks.values()) if china_stocks else 0
            regular_stocks_value = sum(regular_stocks.values()) if regular_stocks else 0
            total_stocks_value = china_stocks_value + regular_stocks_value

            # Calculate percentages of total stocks
            if total_stocks_value > 0:
                china_pct = china_stocks_value / total_stocks_value * 100
                regular_pct = regular_stocks_value / total_stocks_value * 100

                # Format the percentage strings
                china_pct_str = DataFormatter.format_percentage(china_pct)
                regular_pct_str = DataFormatter.format_percentage(regular_pct)

                # Process categories
                for subcat, contents in ib_data.items():
                    if isinstance(contents, dict) and not contents:
                        continue

                    if isinstance(contents, dict):
                        # Special handling for China Stocks and Stocks categories
                        if subcat == "China Stocks":
                            # Track the row index for the category header
                            self.category_header_rows.append(len(rows))

                            # Add category header with percentage - removed P&L calculation
                            category_row = DataFormatter.row_left(
                                f"{subcat} / {china_pct_str}",
                                DataFormatter.format_currency(china_stocks_value),
                            )

                            # No longer adding P&L percentage to category headers
                            rows.append(category_row)

                            # Add individual positions
                            enhanced_china_stocks = (
                                enhanced_stocks.get(subcat, {})
                                if enhanced_stocks
                                else {}
                            )

                            for sym, val in contents.items():
                                position_row = DataFormatter.row_left(
                                    sym, DataFormatter.format_currency(val)
                                )

                                # Add P&L for individual position if available
                                if (
                                    sym in enhanced_china_stocks
                                    and "unrealized_pnl_percentage"
                                    in enhanced_china_stocks[sym]
                                ):
                                    pnl_percent = enhanced_china_stocks[sym][
                                        "unrealized_pnl_percentage"
                                    ]
                                    position_row.append(
                                        DataFormatter.format_pnl_percentage(pnl_percent)
                                    )

                                rows.append(position_row)

                            rows.append(DataFormatter.row_left())

                        elif subcat == "Stocks":
                            # Track the row index for the category header
                            self.category_header_rows.append(len(rows))

                            # Add category header with percentage - removed P&L calculation
                            category_row = DataFormatter.row_left(
                                f"{subcat} / {regular_pct_str}",
                                DataFormatter.format_currency(regular_stocks_value),
                            )

                            # No longer adding P&L percentage to category headers
                            rows.append(category_row)

                            # Add individual positions
                            enhanced_regular_stocks = (
                                enhanced_stocks.get(subcat, {})
                                if enhanced_stocks
                                else {}
                            )

                            for sym, val in contents.items():
                                position_row = DataFormatter.row_left(
                                    sym, DataFormatter.format_currency(val)
                                )

                                # Add P&L for individual position if available
                                if (
                                    sym in enhanced_regular_stocks
                                    and "unrealized_pnl_percentage"
                                    in enhanced_regular_stocks[sym]
                                ):
                                    pnl_percent = enhanced_regular_stocks[sym][
                                        "unrealized_pnl_percentage"
                                    ]
                                    position_row.append(
                                        DataFormatter.format_pnl_percentage(pnl_percent)
                                    )

                                rows.append(position_row)

                            rows.append(DataFormatter.row_left())

                        elif subcat == "Precious Metals":
                            # Track the row index for the category header
                            self.category_header_rows.append(len(rows))
                            rows.append(DataFormatter.row_left(subcat))

                            # Add individual positions with purchase-price delta if available
                            enhanced_precious_metals = (
                                enhanced_stocks.get(subcat, {})
                                if enhanced_stocks
                                else {}
                            )

                            for sym, val in contents.items():
                                position_row = DataFormatter.row_left(
                                    sym, DataFormatter.format_currency(val)
                                )

                                if (
                                    sym in enhanced_precious_metals
                                    and "unrealized_pnl_percentage"
                                    in enhanced_precious_metals[sym]
                                ):
                                    pnl_percent = enhanced_precious_metals[sym][
                                        "unrealized_pnl_percentage"
                                    ]
                                    position_row.append(
                                        DataFormatter.format_pnl_percentage(pnl_percent)
                                    )

                                rows.append(position_row)

                            rows.append(DataFormatter.row_left())

                        else:
                            # Track the row index for any other category header
                            self.category_header_rows.append(len(rows))
                            rows.append(DataFormatter.row_left(subcat))

                            # Add individual components
                            for sym, val in contents.items():
                                rows.append(
                                    DataFormatter.row_left(
                                        sym, DataFormatter.format_currency(val)
                                    )
                                )

                            rows.append(DataFormatter.row_left())
                    else:
                        rows.append(
                            DataFormatter.row_left(
                                subcat, DataFormatter.format_currency(contents)
                            )
                        )
                        rows.append(DataFormatter.row_left())
            else:
                # Fallback if no stock values are available
                rows.extend(self._parse_ib_data_with_tracking(ib_data))
        else:
            # Fallback if IB data is missing
            rows.extend(self._parse_ib_data_with_tracking(ib_data))

        # Handle CRYPTO_DATA and track its header
        crypto_data = self.data.get("CRYPTO_DATA", {})
        if crypto_data:
            self.category_header_rows.append(len(rows))  # Track CRYPTO_DATA header
            rows.append(DataFormatter.row_left("CRYPTO_DATA"))

            total_crypto = crypto_data.get("Total_Crypto_Value", 0)
            rows.append(
                DataFormatter.row_left(
                    "Total Crypto Value", DataFormatter.format_currency(total_crypto)
                )
            )
            rows.append(DataFormatter.row_left())

            market_vals = crypto_data.get("Crypto_Market_Values", {})
            if market_vals:
                self.category_header_rows.append(
                    len(rows)
                )  # Track Market Values header
                rows.append(DataFormatter.row_left("Market Values"))
                for sym, val in market_vals.items():
                    rows.append(
                        DataFormatter.row_left(sym, DataFormatter.format_currency(val))
                    )
                rows.append(DataFormatter.row_left())

        # Handle CASH_DATA and track its header
        cash_data = self.data.get("CASH_DATA", {})
        if cash_data:
            total_val = cash_data.get("Total", 0)
            if isinstance(total_val, Decimal):
                total_val = float(total_val)
            self.category_header_rows.append(len(rows))  # Track CASH_DATA header
            rows.append(
                DataFormatter.row_left(
                    "CASH_DATA (total)", DataFormatter.format_currency(total_val)
                )
            )
            rows.append(DataFormatter.row_left())

        other_assets = self.data.get("OTHER_ASSETS")
        if not other_assets:
            try:
                other_assets = {"Other": float(OTHER_BETS)}
            except Exception:
                other_assets = {}

        for label, raw_val in other_assets.items():
            try:
                other_val = float(raw_val)
            except (TypeError, ValueError):
                continue

            if other_val:
                self.category_header_rows.append(len(rows))
                rows.append(
                    DataFormatter.row_left(
                        label, DataFormatter.format_currency(other_val)
                    )
                )
                rows.append(DataFormatter.row_left())

        return rows

    def _parse_ib_data_with_tracking(self, ib_data: Dict) -> List[List[str]]:
        """Parse IB data and track category header rows."""
        rows = []
        for subcat, contents in ib_data.items():
            if isinstance(contents, dict) and not contents:
                continue

            if isinstance(contents, dict):
                # Track the row index for the category header
                self.category_header_rows.append(len(rows))
                rows.append(DataFormatter.row_left(subcat))
                for sym, val in contents.items():
                    rows.append(
                        DataFormatter.row_left(sym, DataFormatter.format_currency(val))
                    )
                rows.append(DataFormatter.row_left())
            else:
                rows.append(
                    DataFormatter.row_left(
                        subcat, DataFormatter.format_currency(contents)
                    )
                )
                rows.append(DataFormatter.row_left())
        return rows

    def _set_cell(self, final_table: List[List[str]], r: int, c: int, val: str) -> None:
        """Ensure cell exists and set its value."""
        while len(final_table) <= r:
            final_table.append([])
        while len(final_table[r]) <= c:
            final_table[r].append("")
        final_table[r][c] = val

    def build_central_columns(self, left_table: List[List[str]]) -> List[List[str]]:
        """Build complete table including right columns."""
        final_table = left_table[:]

        # Financial Freedom (G/H/I)
        freedom = self.data.get("FIN_FREEDOM_GOAL_PROGRESS", "")
        self._set_cell(final_table, 0, 6, "FIRE Goal")
        self._set_cell(final_table, 0, 7, freedom)

        # Net worth (TOTAL_ASSETS already includes OTHER_BETS)
        total_assets = self.data.get("TOTAL_ASSETS", 0)
        self._set_cell(final_table, 2, 6, "Net worth")
        self._set_cell(
            final_table,
            2,
            7,
            DataFormatter.format_currency(total_assets),
        )
        self._set_cell(final_table, 2, 8, "%")

        # Allocations
        alloc_data = self.data.get("ALLOCATIONS", {}).get("allocation_breakdown", {})

        # Get the actual asset values
        ib_data = self.data.get("IB_DATA", {})

        # For bonds
        bonds = ib_data.get("Bonds", {})
        actual_bonds_value = sum(bonds.values()) if bonds else 0

        # For stocks (combining China Stocks and Stocks)
        china_stocks = ib_data.get("China Stocks", {})
        regular_stocks = ib_data.get("Stocks", {})
        actual_china_stocks_value = sum(china_stocks.values()) if china_stocks else 0
        actual_regular_stocks_value = (
            sum(regular_stocks.values()) if regular_stocks else 0
        )

        # Calculate total stocks value directly from the stock values
        actual_stocks_value = actual_china_stocks_value + actual_regular_stocks_value

        # Optional logging for transparency
        logger = logging.getLogger(__name__)
        logger.debug(f"China Stocks sum: {actual_china_stocks_value}")
        logger.debug(f"Regular Stocks sum: {actual_regular_stocks_value}")
        logger.debug(f"Total Stocks calculated: {actual_stocks_value}")

        other_assets = self.data.get("OTHER_ASSETS")
        if other_assets:
            try:
                other_val = sum(float(v) for v in other_assets.values())
            except (TypeError, ValueError):
                other_val = 0.0
        else:
            try:
                from data.assets_data import OTHER_BETS

                other_val = float(OTHER_BETS)
            except Exception:
                other_val = 0.0

        # Start writing allocation rows from row index 3, skipping small categories
        current_row_idx = 3
        for cat, pct in alloc_data.items():
            # Use actual values for Bonds and Stocks, calculate others from percentage
            if cat == "Bonds" and actual_bonds_value > 0:
                val = actual_bonds_value
            elif cat == "Stocks" and actual_stocks_value > 0:
                val = actual_stocks_value
            elif cat.lower() == "other bets" and other_val:
                val = other_val
            else:
                val = round(total_assets * (pct / 100))

            # Skip categories with negligible size (< 1 unit or < 1%)
            if val < 1:
                continue

            self._set_cell(final_table, current_row_idx, 6, cat)
            self._set_cell(
                final_table, current_row_idx, 7, DataFormatter.format_currency(val)
            )
            self._set_cell(
                final_table, current_row_idx, 8, DataFormatter.format_percentage(pct)
            )
            current_row_idx += 1

        # Fixed Income Data (K/L)
        self._build_fixed_income_section(final_table)

        return final_table

    def _build_fixed_income_section(self, final_table: List[List[str]]) -> None:
        """Build fixed income section in columns K/L."""
        fid = self.data.get("FIXED_INCOME_DATA", {})
        gwi = fid.get("group_weighted_interest", {})
        fipi = fid.get("fixed_inc_principal_and_interest", {})

        self._set_cell(final_table, 2, 10, "FIXED_INCOME_DATA")
        row_gwi = 3

        if fipi:
            principal = fipi.get("principal", 0)
            interest_raw = fipi.get("interest", 0)
            combined_val = DataFormatter.format_fixed_income(principal, interest_raw)
            self._set_cell(final_table, row_gwi, 10, "Total")
            self._set_cell(final_table, row_gwi, 11, combined_val)
            row_gwi += 1

        if gwi:
            for label, (principal, rate) in gwi.items():
                text_val = DataFormatter.format_fixed_income(principal, rate)
                self._set_cell(final_table, row_gwi, 10, label)
                self._set_cell(final_table, row_gwi, 11, text_val)
                row_gwi += 1

                if label == "p2p_lending":
                    row_gwi += 1
                    monthly_div = fid.get("total_monthly", 0)
                    yearly_div = fid.get("total_yearly", 0)

                    self._set_cell(final_table, row_gwi, 10, "Monthly Dividend")
                    self._set_cell(
                        final_table,
                        row_gwi,
                        11,
                        DataFormatter.format_currency(monthly_div),
                    )
                    row_gwi += 1

                    self._set_cell(final_table, row_gwi, 10, "Yearly Dividend")
                    self._set_cell(
                        final_table,
                        row_gwi,
                        11,
                        DataFormatter.format_currency(yearly_div),
                    )


class PortfolioUpdater:
    """Main class for updating portfolio spreadsheet."""

    def __init__(self, credentials_path: str, spreadsheet_name: str):
        self.sheets_client = GoogleSheetsClient(credentials_path)
        self.spreadsheet = self.sheets_client.open_spreadsheet(spreadsheet_name)
        self.portfolio_sheet = PortfolioSpreadsheet(self.spreadsheet)

    def update_portfolio(self, data: Dict[str, Any]) -> None:
        """Update portfolio with new data."""
        date_title = datetime.now().strftime("%d %b %Y")
        worksheet = self.portfolio_sheet.create_tab_at_left(date_title)

        # Enrich data with enhanced stock positions if available
        self._enrich_with_enhanced_stock_data(data)

        table_builder = PortfolioTableBuilder(data)
        left_table = table_builder.build_left_columns()
        final_table = table_builder.build_central_columns(left_table)

        # Use the new PortfolioFormatter for formatting
        portfolio_formatter = PortfolioFormatter(worksheet)
        portfolio_formatter.format_portfolio_table(
            final_table, table_builder.category_header_rows
        )
        # Expand columns D and K for better fit
        portfolio_formatter.expand_columns_for_portfolio(
            col_d_width=200, col_k_width=180
        )
        # Apply bold+large font to Net Worth cells G3:I3 (row 2, cols 6-9)
        portfolio_formatter.apply_bold_and_large_font_to_range(2, 3, 6, 9, font_size=14)
        # Apply bold to FIXED_INCOME_DATA cell K3 (row 2, col 10)
        portfolio_formatter.apply_bold_to_cell(2, 10)
        # Calculate and display percent of fixed income of total assets
        self._write_fixed_income_percentage(worksheet)

        # Update timeline
        self.update_net_worth_timeline(data.get("TOTAL_ASSETS", 0))

    def _enrich_with_enhanced_stock_data(self, data: Dict[str, Any]) -> None:
        """
        Enrich the data dictionary with enhanced stock data if available.

        This method checks if there's an InteractiveBrokers instance available in the data
        and extracts enhanced stock positions data to include in the spreadsheet.
        """
        # If enhanced stock data is already provided, no need to extract it
        if "ENHANCED_STOCKS" in data:
            return

        # Try to import the InteractiveBrokers class
        try:
            from src.brokers.ib import InteractiveBrokers

            # Check if IB_CLIENT is provided in the data
            ib_client = data.get("IB_CLIENT")
            if ib_client and isinstance(ib_client, InteractiveBrokers):
                # Get enhanced stock positions
                enhanced_stocks = ib_client.get_stock_positions_analytics()
                if enhanced_stocks:
                    data["ENHANCED_STOCKS"] = enhanced_stocks

                    # Log success
                    logging.getLogger(__name__).info(
                        "Successfully enriched data with enhanced stock positions"
                    )
        except (ImportError, AttributeError) as e:
            # Log the error but continue without enhanced data
            logging.getLogger(__name__).warning(
                f"Could not enrich data with enhanced stock positions: {str(e)}"
            )

    def _write_fixed_income_percentage(self, worksheet: gspread.Worksheet) -> None:
        """Compute % of fixed income principal relative to total assets and write next to header.

        Cells (1-based indices):
        - Net worth value at H3
        - FIXED_INCOME_DATA header at K3; percentage should go to L3
        - Fixed income total value string at L4 (formatted like '88345 @ 7.6%')
        """
        # 1-based indices for clarity
        NET_WORTH_ROW, NET_WORTH_COL = 3, 8  # H3
        FI_HEADER_ROW, FI_PCT_COL = 3, 12  # L3
        FI_TOTAL_ROW, FI_TOTAL_VALUE_COL = 4, 12  # L4

        try:
            # Read total assets (H3), stripping thousands separators
            raw_total_assets = worksheet.cell(NET_WORTH_ROW, NET_WORTH_COL).value or "0"
            total_assets = float(str(raw_total_assets).replace(",", ""))

            # Read fixed income combined value (L4) like '88345 @ 7.6%'
            fixed_income_value = worksheet.cell(FI_TOTAL_ROW, FI_TOTAL_VALUE_COL).value
            import re

            match = re.match(r"(\d+)", str(fixed_income_value))
            fixed_income_principal = float(match.group(1)) if match else 0.0

            pct_str = SpreadsheetFormatter.calc_fixed_income_pct_of_total(
                fixed_income_principal, total_assets
            )
            # Write percentage to L3
            worksheet.update_cell(FI_HEADER_ROW, FI_PCT_COL, pct_str)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Could not calculate/write fixed income percent: {e}"
            )

    def update_net_worth_timeline(self, total_assets: Union[int, float]) -> None:
        """Update net worth timeline worksheet."""
        try:
            worksheet = self.spreadsheet.worksheet("net_worth_timeline")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title="net_worth_timeline", rows=200, cols=2
            )

        # Get current date
        date_str = datetime.now().strftime("%d %b %Y")

        # Use the new TimelineFormatter for formatting
        timeline_formatter = TimelineFormatter(worksheet)
        timeline_formatter.format_timeline_entry(total_assets, date_str)


def update_portfolio_spreadsheet(
    data: Dict[str, Any], credentials_path: str, spreadsheet_name: str, ib_client=None
) -> None:
    """
    Convenience function for updating portfolio.

    Args:
        data: Dictionary containing portfolio data
        credentials_path: Path to the Google API credentials file
        spreadsheet_name: Name of the Google Sheet to update
        ib_client: Optional InteractiveBrokers client instance to extract enhanced stock data
    """
    # If IB client is provided, add it to the data for enhanced stock positions
    if ib_client:
        data["IB_CLIENT"] = ib_client

    updater = PortfolioUpdater(credentials_path, spreadsheet_name)
    updater.update_portfolio(data)


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
