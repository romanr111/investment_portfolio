import gspread

from google.oauth2.service_account import Credentials

from data_source import DataSource
from data.endpoints import SCOPE

from src.brokers.ib_dividends import PublicDividends
from src.google_sheets.formatting import SpreadsheetFormatter
from src.fire import FinancialFreedom


CREDENTIALS_PATH = "data/credentials.json"
SPREADSHEET_NAME = "portfolio_automated"

CATEGORIES = [
    "Banks",
    "China",
    "USA_Stocks",
    "Short",
    "REIT",
    "Bonds",
    "P2P",
    "Gold",
    "Commodities",
    "Crypto",
]


class GoogleSheet:
    def __init__(self, credentials_path, spreadsheet_name, worksheet_name):
        self._credentials_path = credentials_path
        self._spreadsheet_name = spreadsheet_name
        self._worksheet_name = worksheet_name
        self.client = self._authorize_google_client()
        self.spreadsheet = self.client.open(self._spreadsheet_name)

        # Check if worksheet exists and create a new one if needed
        try:
            self.sheet = self.spreadsheet.worksheet(self._worksheet_name)
        except gspread.WorksheetNotFound:
            self.sheet = self.spreadsheet.add_worksheet(
                title=self._worksheet_name, rows="70", cols="20"
            )

    def _authorize_google_client(self):
        creds = Credentials.from_service_account_file(
            self._credentials_path, scopes=SCOPE
        )
        return gspread.authorize(creds)


class SpreadsheetConstructor:
    def __init__(self, sheet, data_sources):
        self.sheet = sheet
        self.data_sources = data_sources

    def _add_data_range(self, start, finish, keys, values_dict, data_ranges):
        """Helper function to append data ranges."""
        values = [values_dict[key] for key in keys]
        data_ranges.extend(
            [
                {
                    "range": f"D{start}:D{finish}",
                    "values": [keys],
                    "major_dimension": "COLUMNS",
                },
                {
                    "range": f"E{start}:E{finish}",
                    "values": [values],
                    "major_dimension": "COLUMNS",
                },
            ]
        )
        return data_ranges

    def prepare_data_for_update(self):
        data_ranges = []

        # Loop over categories and construct keys and values
        start_pos = 2
        for category in CATEGORIES:
            asset_keys = list(self.data_sources[category].keys())
            finish_pos = start_pos + len(asset_keys)

            print(f"{category}:", asset_keys)
            data_ranges = self._add_data_range(
                start_pos,
                finish_pos,
                asset_keys,
                self.data_sources[category],
                data_ranges,
            )

            start_pos = finish_pos + 1

        # Summary table data
        p_alloc = self.data_sources["portfolio_allocations"]
        asset_types = [
            "Net worth",
            "Stocks",
            "REIT",
            "Bonds",
            "Crypto",
            "Gold",
            "Commodities",
            "P2P",
            "Cash & Equivalents",
        ]
        total_values = [
            p_alloc.net_worth,
            p_alloc.total_stocks_mkt_val,
            p_alloc.total_reits_mkt_val,
            p_alloc.bonds_mkt_value,
            p_alloc.crypto_mkt_value,
            p_alloc.ib_gold_mkt_value,
            p_alloc.comm_mkt_value,
            p_alloc.cash_balance,
        ]
        allocations = [
            "%",
            p_alloc.stocks_allocation,
            p_alloc.reit_allocation,
            p_alloc.bonds_allocation,
            p_alloc.crypto_allocation,
            p_alloc.gold_allocation,
            p_alloc.commodities_allocation,
            p_alloc.cash_allocation,
        ]
        expected_allocations = [
            "Exp %",
            p_alloc.expected_allocations["Stocks"],
            p_alloc.expected_allocations["REIT"],
            p_alloc.expected_allocations["Bonds"],
            p_alloc.expected_allocations["Crypto"],
            p_alloc.expected_allocations["Gold"],
            p_alloc.expected_allocations["Commodities"],
            p_alloc.expected_allocations["Cash & Equivalents"],
        ]

        data_ranges.extend(
            [
                {
                    "range": f"H3:H11",
                    "values": [asset_types],
                    "major_dimension": "COLUMNS",
                },
                {
                    "range": f"I3:I11",
                    "values": [total_values],
                    "major_dimension": "COLUMNS",
                },
                {
                    "range": f"J3:J11",
                    "values": [allocations],
                    "major_dimension": "COLUMNS",
                },
                {
                    "range": f"K3:K11",
                    "values": [expected_allocations],
                    "major_dimension": "COLUMNS",
                },
            ]
        )

        return data_ranges

    def update_spreadsheet(self):
        prepared_data = self.prepare_data_for_update()
        print(f"prepared_data --- {prepared_data}")
        self.sheet.batch_update(prepared_data)

    def update_individual_cells(self, allocation, broker):
        p_alloc = self.data_sources["portfolio_allocations"]
        ff = FinancialFreedom(allocation)
        d = PublicDividends(broker)

        self.sheet.update("H1", "Financial Freedom")
        self.sheet.update("I1", f"{ff.calculate_financial_freedom_goal_progress()}")

        self.sheet.update("H12", "Monthly Dividend")
        self.sheet.update("I12", f"{d.get_my_total_monthly_and_yearly_divs()[0]}")

        self.sheet.update("M1", "Dasha")
        self.sheet.update("N1", f"{p_alloc.dasha_net_worth}")


class SpreadsheetManager:
    def __init__(self, worksheet_name: str, ib_endpoint, crypto_endpoint):
        self.google_sheet = GoogleSheet(
            CREDENTIALS_PATH,
            SPREADSHEET_NAME,
            worksheet_name,
        )
        self.data_source_obj = DataSource(ib_endpoint, crypto_endpoint)
        self.data_source = self.data_source_obj.fetch_data()

    def update_data(self):
        """Updates the spreadsheet with data from various sources."""
        manager = SpreadsheetConstructor(self.google_sheet.sheet, self.data_source)
        manager.update_spreadsheet()
        manager.update_individual_cells(
            self.data_source_obj.p_alloc, self.data_source_obj.ib
        )

    def format_spreadsheet(self):
        """Applies formatting to the spreadsheet."""
        frm = SpreadsheetFormatter(self.data_source_obj.p_alloc)
        frm.format_spreadsheet(self.google_sheet.sheet)


if __name__ == "__main__":
    worksheet_name = "Test 2023"
    portfolio_manager = SpreadsheetManager(worksheet_name)
    portfolio_manager.update_data()
    portfolio_manager.format_spreadsheet()
