import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, Union, Tuple


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


class DataFormatter:
    """Handles data formatting for spreadsheet cells."""

    @staticmethod
    def row_left(d_val: str = "", e_val: str = "") -> List[str]:
        """Create a row reaching columns D & E."""
        return ["", "", "", d_val, e_val]

    @staticmethod
    def format_fixed_income(principal: Union[int, float], interest: float) -> str:
        """Format fixed income data."""
        interest_str = f"{interest * 100:.1f}%"
        return f"{principal} @ {interest_str}"


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

    def build_left_columns(self) -> List[List[str]]:
        """Build columns D/E data."""
        rows = []

        ib_data = self.data.get("IB_DATA", {})
        if ib_data:
            rows.extend(PortfolioDataParser.parse_ib_data(ib_data))

        crypto_data = self.data.get("CRYPTO_DATA", {})
        if crypto_data:
            rows.extend(PortfolioDataParser.parse_crypto_data(crypto_data))

        cash_data = self.data.get("CASH_DATA", {})
        if cash_data:
            rows.extend(PortfolioDataParser.parse_cash_data(cash_data))

        return rows

    def _set_cell(self, final_table: List[List[str]], r: int, c: int, val: str) -> None:
        """Ensure cell exists and set its value."""
        while len(final_table) <= r:
            final_table.append([])
        while len(final_table[r]) <= c:
            final_table[r].append("")
        final_table[r][c] = val

    def build_right_columns(self, left_table: List[List[str]]) -> List[List[str]]:
        """Build complete table including right columns."""
        final_table = left_table[:]

        # Financial Freedom (G/H/I)
        freedom = self.data.get("FIN_FREEDOM_GOAL_PROGRESS", "")
        self._set_cell(final_table, 0, 6, "Financial Freedom")
        self._set_cell(final_table, 0, 7, freedom)

        # Net worth
        total_assets = self.data.get("TOTAL_ASSETS", 0)
        self._set_cell(final_table, 2, 6, "Net worth")
        self._set_cell(final_table, 2, 7, str(total_assets))
        self._set_cell(final_table, 2, 8, "%")

        # Allocations
        alloc_data = self.data.get("ALLOCATIONS", {}).get("allocation_breakdown", {})
        for row_idx, (cat, pct) in enumerate(alloc_data.items(), start=3):
            val = round(total_assets * (pct / 100))
            self._set_cell(final_table, row_idx, 6, cat)
            self._set_cell(final_table, row_idx, 7, str(val))
            self._set_cell(final_table, row_idx, 8, f"{pct}")

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
                    self._set_cell(final_table, row_gwi, 11, str(monthly_div))
                    row_gwi += 1

                    self._set_cell(final_table, row_gwi, 10, "Yearly Dividend")
                    self._set_cell(final_table, row_gwi, 11, str(yearly_div))


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

        table_builder = PortfolioTableBuilder(data)
        left_table = table_builder.build_left_columns()
        final_table = table_builder.build_right_columns(left_table)

        worksheet.clear()
        worksheet.update("A1", final_table)

        # Update timeline
        self.update_net_worth_timeline(data.get("TOTAL_ASSETS", 0))

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

        # Get all existing values
        existing_values = worksheet.get_all_values()

        # Find and delete row with the same date if it exists
        for idx, row in enumerate(existing_values, start=1):
            if len(row) >= 2 and row[1] == date_str:
                # Delete the row with matching date
                worksheet.delete_rows(idx)
                existing_values = (
                    worksheet.get_all_values()
                )  # Refresh values after deletion
                break

        # Add new row at the bottom
        next_row = len(existing_values) + 1
        worksheet.update_cell(next_row, 1, str(total_assets))
        worksheet.update_cell(next_row, 2, date_str)


def update_portfolio(
    data: Dict[str, Any], credentials_path: str, spreadsheet_name: str
) -> None:
    """Convenience function for updating portfolio."""
    updater = PortfolioUpdater(credentials_path, spreadsheet_name)
    updater.update_portfolio(data)


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
