# TODO:
"""
import gspread_formatting as gsf
from src.google_sheets.allocation import PortfolioAllocations


class AllocationRatioCalculator:
    @staticmethod
    def calculate_allocation_ratio(real, exp):
        return int((real / exp) * 100)


class SpreadsheetFormatter:
    def __init__(self, alloc: PortfolioAllocations):
        self.alloc = alloc
        self.calculator = AllocationRatioCalculator()

    def format_spreadsheet(self, sheet):
        # Setting column widths
        gsf.set_column_widths(
            sheet,
            [
                ("A", 100),
                ("B:", 40),
                ("C", 45),
                ("D", 50),
                ("E", 60),
                ("F", 60),
                ("G", 60),
                ("H", 140),
                ("I", 100),
                ("J", 30),
                ("K", 60),
            ],
        )

        # Formatting cells
        self._set_static_cell_formats(sheet)
        self._color_allocation_cells_based_on_ratio(sheet)

    def _set_static_cell_formats(self, sheet):
        net_worth = gsf.cellFormat(
            textFormat=gsf.textFormat(bold=True, fontSize=12),
            horizontalAlignment="CENTER",
        )

        summary_asset_types = gsf.cellFormat(
            textFormat=gsf.textFormat(bold=True, fontSize=10),
            horizontalAlignment="CENTER",
        )

        asset_types_amounts = gsf.cellFormat(
            textFormat=gsf.textFormat(bold=False, fontSize=10),
        )

        current_allocation = gsf.cellFormat(
            textFormat=gsf.textFormat(bold=True, fontSize=9),
            horizontalAlignment="CENTER",
        )

        expected_allocation = gsf.cellFormat(
            textFormat=gsf.textFormat(bold=False, fontSize=9),
            horizontalAlignment="CENTER",
        )

        dividends = gsf.cellFormat(
            textFormat=gsf.textFormat(bold=True, fontSize=10),
            horizontalAlignment="CENTER",
        )

        gsf.format_cell_ranges(
            sheet,
            [
                ("H3:I3", net_worth),
                ("H4:H10", summary_asset_types),
                ("I4:I10", asset_types_amounts),
                ("J3:J10", current_allocation),
                ("K3:K10", expected_allocation),
                ("H12:I12", dividends),
            ],
        )

    def _color_allocation_cells_based_on_ratio(self, sheet):
        for cell, actual, expected in zip(
            list(self.alloc.actual_allocations.keys()),
            list(self.alloc.actual_allocations.values()),
            list(self.alloc.expected_allocations.values()),
        ):
            ratio = self.calculator.calculate_allocation_ratio(actual, expected)
            self._color_cell_based_on_ratio(sheet, cell, ratio)

    def _color_cell_based_on_ratio(self, sheet, cell, ratio):
        if ratio < 50 or ratio > 200:
            # Red
            color = {"red": 0.76, "green": 0.13, "blue": 0.13}
        elif 80 <= ratio <= 120:
            # Green
            color = {"red": 0.72, "green": 0.84, "blue": 0.66}
        else:
            # Yellow
            color = {"red": 0.973, "green": 0.793, "blue": 0.115}

        sheet.format(cell, {"backgroundColor": color})


if __name__ == "__main__":
    alloc = PortfolioAllocations()
    formatter = SpreadsheetFormatter(alloc)
    sheet = ...  # Get your Google Sheet instance here
    formatter.format_spreadsheet(sheet)
"""
