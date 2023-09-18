import gspread_formatting as gsf
from gspread_formatting import batch_updater
from portfolio_allocation import Portfolio_Allocations

alloc = Portfolio_Allocations()


class SpreadsheetFromatting:
    def calculate_allocation_ratio(self, real, exp):
        ratio = int((real / exp) * 100)
        return ratio

    def formatSpreadheet(self, sheet):
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

        for cell, actual, expected in zip(
            list(alloc.actual_allocations.keys()),
            list(alloc.actual_allocations.values()),
            list(alloc.expected_allocations.values()),
        ):
            if (self.calculate_allocation_ratio(actual, expected) < 50) or (
                self.calculate_allocation_ratio(actual, expected) > 200
            ):
                # Red
                sheet.format(
                    cell,
                    {"backgroundColor": {"red": 0.76, "green": 0.13, "blue": 0.13}},
                )
            elif self.calculate_allocation_ratio(actual, expected) in range(80, 120):
                # Green
                sheet.format(
                    cell,
                    {"backgroundColor": {"red": 0.72, "green": 0.84, "blue": 0.66}},
                )
            else:
                # Yellow
                sheet.format(
                    cell,
                    {"backgroundColor": {"red": 0.973, "green": 0.793, "blue": 0.115}},
                )
