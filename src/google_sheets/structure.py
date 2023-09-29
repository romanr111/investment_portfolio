import gspread
from data.endpoints import SCOPE
from google.oauth2.service_account import Credentials
from src.brokers.ib import InteractiveBrokers
from src.brokers.ib_dividends import PublicDividends
from src.crypto.crypto import CryptoValue
from src.cash_fixed_income.cash_summary import Cash
from allocation import Portfolio_Allocations
from formatting import SpreadsheetFromatting
from src.fire import FinancialFreedom

CREDENTIALS_PATH = "credentials.json"
SPREADSHEET_NAME = "portfolio_automated"
WORKSHEET_NAME = "Test 2023"


def authorize_google_client():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPE)
    return gspread.authorize(creds)


def fetch_data_sources():
    ib = InteractiveBrokers()
    crypto = CryptoValue()
    cash = Cash()
    p_alloc = Portfolio_Allocations()
    return {
        "banks": ib.get_banks_positions(),
        "other_stocks": ib.get_stocks_without_banks_reits_gld_cmd(),
        "reits": ib.get_reits_positions(),
        "bonds": ib.get_bonds_positions(),
        "ib_gold": ib.get_gold_positions(),
        "ib_comm": ib.get_commodities_positions(),
        "crypto": crypto.getCryptoPositions(),
        "cash": cash.getCashPositions(),
        "portfolio_allocations": p_alloc,
    }


def prepare_data_for_update(data_sources):
    data_ranges = []

    def add_data_range(start, finish, keys, values):
        data_ranges.append(
            {
                "range": f"D{start}:D{finish}",
                "values": [keys],
                "major_dimension": "COLUMNS",
            }
        )
        data_ranges.append(
            {
                "range": f"E{start}:E{finish}",
                "values": [values],
                "major_dimension": "COLUMNS",
            }
        )

    # Data fetching
    banks_keys = list(map(str, data_sources["banks"].keys()))
    other_stocks_keys = list(map(str, data_sources["other_stocks"].keys()))
    reits_keys = list(map(str, data_sources["reits"].keys()))
    bonds_keys = list(map(str, data_sources["bonds"].keys()))
    gold_keys = list(data_sources["ib_gold"].keys())
    comm_keys = list(data_sources["ib_comm"].keys())
    crypto_keys = list(data_sources["crypto"].keys())

    start_pos = 2
    for asset in [
        banks_keys,
        other_stocks_keys,
        reits_keys,
        bonds_keys,
        gold_keys,
        comm_keys,
        crypto_keys,
    ]:
        finish_pos = start_pos + len(asset)
        add_data_range(start_pos, finish_pos, asset, data_sources[asset])
        start_pos = finish_pos + 1

    # Summary table
    p_alloc = data_sources["portfolio_allocations"]
    asset_types = [
        "Net worth",
        "Stocks",
        "REIT",
        "Bonds",
        "Crypto",
        "Gold",
        "Commodities",
        "Mining",
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
        p_alloc.mining_mkt_value,
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
        p_alloc.mining_allocation,
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
        p_alloc.expected_allocations["Mining"],
        p_alloc.expected_allocations["Cash & Equivalents"],
    ]

    data_ranges.extend(
        [
            {"range": f"H3:H11", "values": [asset_types], "major_dimension": "COLUMNS"},
            {
                "range": f"I3:I11",
                "values": [total_values],
                "major_dimension": "COLUMNS",
            },
            {"range": f"J3:J11", "values": [allocations], "major_dimension": "COLUMNS"},
            {
                "range": f"K3:K11",
                "values": [expected_allocations],
                "major_dimension": "COLUMNS",
            },
        ]
    )

    return data_ranges


def main():
    client = authorize_google_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

    data_sources = fetch_data_sources()

    # Filling data into the spreadsheet:
    prepared_data = prepare_data_for_update(data_sources)
    sheet.batch_update(prepared_data)

    # Individual cells update
    p_alloc = data_sources["portfolio_allocations"]
    ff = FinancialFreedom()
    d = PublicDividends()

    crypto_position_finish = len(data_sources["crypto"].keys()) + 2
    sheet.update(f"D{crypto_position_finish + 1}", "Mining")
    sheet.update(f"E{crypto_position_finish + 1}", f"{p_alloc.mining_mkt_value}")

    sheet.update("H1", "Financial Freedom")
    sheet.update("I1", f"{ff.calculate_financial_freedom_goal_progress()}")

    sheet.update("H12", "Monthly Dividend")
    sheet.update("I12", f"{d.get_my_monthly_and_yearly_dividends()[0]}")

    sheet.update("M1", "Dasha")
    sheet.update("N1", f"{p_alloc.dasha_net_worth}")

    # Cells formatting
    frm = SpreadsheetFromatting()
    frm.formatSpreadheet(sheet)


if __name__ == "__main__":
    main()
