from typing import List, Dict, Any, Union
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
