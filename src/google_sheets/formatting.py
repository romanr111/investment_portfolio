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
            f"Applied bold and font size {font_size} formatting to range R{start_row+1}C{start_col+1}:R{end_row}C{end_col}"
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
        """Expand columns A, B, D, and K for better fit (default widths: A=150, B=150, D=200, K=180)."""
        self.set_column_width(0, 150)  # Column A
        self.set_column_width(1, 150)  # Column B
        self.set_column_width(3, col_d_width)  # Column D
        self.set_column_width(10, col_k_width)  # Column K
        self.logger.info(
            f"Expanded columns A, B, D, and K to 150, 150, {col_d_width}, and {col_k_width} pixels respectively."
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

    def apply_percentage_gradient_to_column(
        self,
        start_row: int,
        end_row: int,
        column_index: int = 5,
        min_value: float = -0.30,
        mid_value: float = 0.0,
        max_value: float = 0.50,
    ) -> None:
        """Apply percentage display and red-white-green gradient to a column range."""
        if end_row <= start_row:
            return

        target_range = {
            "sheetId": self.worksheet.id,
            "startRowIndex": start_row,
            "endRowIndex": end_row,
            "startColumnIndex": column_index,
            "endColumnIndex": column_index + 1,
        }

        number_format_request = {
            "repeatCell": {
                "range": target_range,
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "PERCENT",
                            "pattern": "+0.0%;-0.0%;0.0%",
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        }

        gradient_request = {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [target_range],
                    "gradientRule": {
                        "minpoint": {
                            "type": "NUMBER",
                            "value": str(min_value),
                            "color": {
                                "red": 245 / 255,
                                "green": 69 / 255,
                                "blue": 69 / 255,
                            },
                        },
                        "midpoint": {
                            "type": "NUMBER",
                            "value": str(mid_value),
                            "color": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        },
                        "maxpoint": {
                            "type": "NUMBER",
                            "value": str(max_value),
                            "color": {
                                "red": 46 / 255,
                                "green": 204 / 255,
                                "blue": 113 / 255,
                            },
                        },
                    },
                },
                "index": 0,
            }
        }

        self.worksheet.spreadsheet.batch_update(
            {"requests": [number_format_request, gradient_request]}
        )
        self.logger.info(
            "Applied percentage gradient formatting to column %s for rows %s-%s",
            column_index + 1,
            start_row + 1,
            end_row,
        )

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

    def format_holy_grail(self, details_range) -> None:
        requests = [{"repeatCell": {
            "range": {"sheetId": self.worksheet.id, "startRowIndex": 9,
                      "endRowIndex": 10, "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
            "fields": "userEnteredFormat.numberFormat",
        }}, {"repeatCell": {
            "range": {"sheetId": self.worksheet.id, "startRowIndex": 9,
                      "endRowIndex": 14, "startColumnIndex": 0, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment",
        }}]
        if details_range and details_range[1] > details_range[0]:
            bounds = {"sheetId": self.worksheet.id, "dimension": "ROWS",
                      "startIndex": details_range[0], "endIndex": details_range[1]}
            requests.extend([
                {"repeatCell": {
                    "range": {"sheetId": self.worksheet.id, "startRowIndex": details_range[0],
                              "endRowIndex": details_range[1], "startColumnIndex": 0, "endColumnIndex": 2},
                    "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                    "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment",
                }},
                {"addDimensionGroup": {"range": bounds}},
                {"updateDimensionGroup": {"dimensionGroup": {"range": bounds, "depth": 1, "collapsed": True}, "fields": "collapsed"}},
                {"updateDimensionProperties": {"range": bounds, "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
            ])
        self.worksheet.spreadsheet.batch_update({"requests": requests})

    def format_portfolio_table(
        self, table_data: List[List[Union[str, float]]], header_rows: List[int]
    ) -> None:
        """Format the portfolio table with appropriate styling."""
        # Clear existing content
        self.worksheet.clear()

        # Update table data
        self.worksheet.update("A1", table_data)

        # Apply bold formatting to category headers
        self.apply_bold_formatting(header_rows)
        # Column F stores unrealized P&L deltas.
        self.apply_percentage_gradient_to_column(
            start_row=0,
            end_row=len(table_data),
            column_index=5,
        )


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
        # Ensure principal is displayed as an integer (no decimals)
        try:
            principal_int = int(round(float(principal)))
        except Exception:
            principal_int = int(principal) if isinstance(principal, int) else 0
        interest_str = f"{interest * 100:.1f}%"
        return f"{principal_int} @ {interest_str}"

    @staticmethod
    def format_percentage(value: float) -> str:
        """Format a percentage value."""
        return f"{value:.1f}%"

    @staticmethod
    def format_currency(value: Union[int, float, Decimal]) -> str:
        """Format a currency value."""
        if isinstance(value, Decimal):
            value = float(value)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)

    @staticmethod
    def format_pnl_percentage(value: float) -> float:
        """Convert a P&L percentage to decimal form for Sheets percent formatting.

        Args:
            value: P&L percentage value (for example, -14.2 means -14.2%)

        Returns:
            Decimal percentage value (for example, -0.142)
        """
        return round(value / 100, 6)
