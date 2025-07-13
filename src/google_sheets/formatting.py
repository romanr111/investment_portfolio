from typing import List, Union
import logging
from decimal import Decimal
import gspread


class SpreadsheetFormatter:
    """Base class for spreadsheet formatting operations."""

    def __init__(self, worksheet: gspread.Worksheet):
        self.worksheet = worksheet
        self.logger = logging.getLogger(__name__)

    def apply_bold_formatting(
        self, header_rows: List[int], column_index: int = 3
    ) -> None:
        """Apply bold formatting to specified rows in a column."""
        if not header_rows:
            return

        format_requests = []
        bold_format = {"textFormat": {"bold": True}}

        for row_idx in header_rows:
            format_requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": self.worksheet.id,
                            "startRowIndex": row_idx,
                            "endRowIndex": row_idx + 1,
                            "startColumnIndex": column_index,
                            "endColumnIndex": column_index + 1,
                        },
                        "cell": {"userEnteredFormat": bold_format},
                        "fields": "userEnteredFormat.textFormat.bold",
                    }
                }
            )

        if format_requests:
            self.worksheet.spreadsheet.batch_update({"requests": format_requests})
            self.logger.info(
                f"Applied bold formatting to {len(header_rows)} category headers"
            )

    def apply_bold_and_large_font_to_range(
        self,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
        font_size: int = 14,
    ) -> None:
        """Apply bold and larger font formatting to a specific cell range (zero-based, end exclusive)."""
        format_request = {
            "repeatCell": {
                "range": {
                    "sheetId": self.worksheet.id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": font_size}
                    }
                },
                "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.textFormat.fontSize",
            }
        }
        self.worksheet.spreadsheet.batch_update({"requests": [format_request]})
        self.logger.info(
            f"Applied bold and font size {font_size} formatting to range R{start_row+1}:C{start_col+1} to R{end_row}:C{end_col}"
        )

    def set_column_width(self, column_index: int, width: int) -> None:
        """Set the width of a column (0-based index) to the specified pixel size."""
        format_request = {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": self.worksheet.id,
                    "dimension": "COLUMNS",
                    "startIndex": column_index,
                    "endIndex": column_index + 1,
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        }
        self.worksheet.spreadsheet.batch_update({"requests": [format_request]})
        self.logger.info(f"Set column {column_index+1} width to {width} pixels")

    def expand_columns_for_portfolio(
        self, col_d_width: int = 200, col_k_width: int = 180
    ) -> None:
        """Expand both column D and column K for better fit (default widths: D=200, K=180)."""
        self.set_column_width(3, col_d_width)  # Column D
        self.set_column_width(10, col_k_width)  # Column K
        self.logger.info(
            f"Expanded columns D and K to {col_d_width} and {col_k_width} pixels respectively."
        )

    def apply_bold_to_cell(self, row: int, col: int) -> None:
        """Apply bold formatting to a single cell (zero-based)."""
        format_request = {
            "repeatCell": {
                "range": {
                    "sheetId": self.worksheet.id,
                    "startRowIndex": row,
                    "endRowIndex": row + 1,
                    "startColumnIndex": col,
                    "endColumnIndex": col + 1,
                },
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        }
        self.worksheet.spreadsheet.batch_update({"requests": [format_request]})
        self.logger.info(f"Applied bold formatting to cell R{row+1}C{col+1}")

    @staticmethod
    def calc_fixed_income_pct_of_total(
        fixed_income_principal: float, total_assets: float
    ) -> str:
        """Calculate percent of fixed income principal of total assets, formatted as a percent string."""
        if total_assets == 0:
            return "0.0%"
        pct = (fixed_income_principal / total_assets) * 100
        return f"{pct:.1f}%"


class PortfolioFormatter(SpreadsheetFormatter):
    """Handles portfolio-specific formatting operations."""

    def format_portfolio_table(
        self, table_data: List[List[str]], header_rows: List[int]
    ) -> None:
        """Format the portfolio table with appropriate styling."""
        # Clear existing content
        self.worksheet.clear()

        # Update table data
        self.worksheet.update("A1", table_data)

        # Apply bold formatting to category headers
        self.apply_bold_formatting(header_rows)


class TimelineFormatter(SpreadsheetFormatter):
    """Handles timeline-specific formatting operations."""

    def format_timeline_entry(
        self, total_assets: Union[int, float], date_str: str
    ) -> None:
        """Format a new timeline entry."""
        # Get all existing values
        existing_values = self.worksheet.get_all_values()

        # Find and delete row with the same date if it exists
        for idx, row in enumerate(existing_values, start=1):
            if len(row) >= 2 and row[1] == date_str:
                self.worksheet.delete_rows(idx)
                existing_values = self.worksheet.get_all_values()
                break

        # Add new row at the bottom
        next_row = len(existing_values) + 1
        self.worksheet.update_cell(next_row, 1, str(total_assets))
        self.worksheet.update_cell(next_row, 2, date_str)


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

    @staticmethod
    def format_percentage(value: float) -> str:
        """Format a percentage value."""
        return f"{value:.1f}%"

    @staticmethod
    def format_currency(value: Union[int, float, Decimal]) -> str:
        """Format a currency value."""
        if isinstance(value, Decimal):
            value = float(value)
        return str(value)

    @staticmethod
    def format_pnl_percentage(value: float) -> str:
        """Format a P&L percentage value with a sign prefix.

        Args:
            value: P&L percentage value

        Returns:
            Formatted string with '+' or '-' prefix and % suffix
        """
        if value > 0:
            return f"+{value:.1f}%"
        elif value < 0:
            return f"{value:.1f}%"  # Negative sign is already included
        else:
            return "0.0%"
