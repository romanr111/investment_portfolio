import gspread
from endpoints import SCOPE
from google.oauth2.service_account import Credentials
from ib import InteractiveBrokers
from crypto_data import CryptoData
from cash_balance import CashBalance
from dividends import Dividends
from portfolio_allocation import Portfolio_Allocations
from spreadsheet_formatting import SpreadsheetFromatting
from financial_freedom import FinancialFreedom

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#

summary_info = {}
positions_info = {}

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
client = gspread.authorize(creds)
s = client.open("portfolio_automated")
# sheet = s.add_worksheet(title="31 May 2023", rows="70", cols="20")
sheet = s.worksheet("31 May 2023")

ib = InteractiveBrokers()
crypto = CryptoData()
cash = CashBalance()
d = Dividends()
p_alloc = Portfolio_Allocations()
frm = SpreadsheetFromatting()
ff = FinancialFreedom()

if __name__ == "__main__":
    ### ### ### ### ### ### ### ### ### ### ### ### ### ###
    # Data fetching
    ### ### ### ### ### ### ### ### ### ### ### ### ### ###

    banks = ib.get_banks_positions()
    other_stocks = ib.get_stocks_without_banks_reits_gld_cmd()
    reits = ib.get_reits_positions()
    bonds = ib.get_bonds_positions()
    ib_gold = ib.get_gold_positions()
    ib_comm = ib.get_commodities_positions()
    crypto_data = crypto.getCryptoPositions()

    bank_keys = [str(eachvalue) for eachvalue in banks.keys()]
    bank_values = [eachvalue for eachvalue in banks.values()]

    other_stocks_keys = [str(eachvalue) for eachvalue in other_stocks.keys()]
    other_stocks_values = [eachvalue for eachvalue in other_stocks.values()]

    reit_keys = [str(eachvalue) for eachvalue in reits.keys()]
    reit_values = [eachvalue for eachvalue in reits.values()]

    bonds_keys = [str(eachvalue) for eachvalue in bonds.keys()]
    bonds_values = [eachvalue for eachvalue in bonds.values()]

    gold_keys = [eachvalue for eachvalue in ib_gold.keys()]
    gold_values = [eachvalue for eachvalue in ib_gold.values()]

    comm_keys = [eachvalue for eachvalue in ib_comm.keys()]
    comm_values = [eachvalue for eachvalue in ib_comm.values()]
    total_gold = p_alloc.ib_gold_mkt_value

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
        total_gold,
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

    ### ### ### ### ### ### ### ### ### ### ### ### ### ###
    # Data Positions for individual assets in spreadsheet
    ### ### ### ### ### ### ### ### ### ### ### ### ### ###

    banks_start = 2
    banks_finish = banks_start + len(bank_keys)
    other_stocks_start = banks_finish + 1
    other_stocks_finish = other_stocks_start + len(other_stocks_keys)
    reits_start = other_stocks_finish + 1
    reits_finish = reits_start + len(reit_keys)
    bonds_start = reits_finish + 1
    bonds_finish = bonds_start + len(bonds_keys)
    gold_position_start = bonds_finish + 1
    gold_position_finish = gold_position_start + len(gold_keys)
    comm_position_start = gold_position_finish + 2
    comm_position_finish = comm_position_start + len(comm_keys)
    crypto_position_start = comm_position_finish + 1
    crypto_position_finish = crypto_position_start + len(crypto_data.keys())

    ### ### ### ### ### ### ### ### ### ### ### ### ### ###
    # Data preparation for batch update
    ### ### ### ### ### ### ### ### ### ### ### ### ### ###

    prepared_data = [
        {
            "range": f"D{banks_start}:D{banks_finish}",
            "values": [bank_keys],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"E{banks_start}:E{banks_finish}",
            "values": [bank_values],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"D{other_stocks_start}:D{other_stocks_finish}",
            "values": [other_stocks_keys],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"E{other_stocks_start}:E{other_stocks_finish}",
            "values": [other_stocks_values],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"D{reits_start}:D{reits_finish}",
            "values": [reit_keys],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"E{reits_start}:E{reits_finish}",
            "values": [reit_values],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"D{bonds_start}:D{bonds_finish}",
            "values": [bonds_keys],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"E{bonds_start}:E{bonds_finish}",
            "values": [bonds_values],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"D{gold_position_start}:D{gold_position_finish}",
            "values": [gold_keys],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"E{gold_position_start}:E{gold_position_finish}",
            "values": [gold_values],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"D{comm_position_start}:D{comm_position_finish}",
            "values": [comm_keys],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"E{comm_position_start}:E{comm_position_finish}",
            "values": [comm_values],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"D{crypto_position_start}:D{crypto_position_finish}",
            "values": [list(crypto_data.keys())],
            "major_dimension": "COLUMNS",
        },
        {
            "range": f"E{crypto_position_start}:E{crypto_position_finish}",
            "values": [list(crypto_data.values())],
            "major_dimension": "COLUMNS",
        },
        # Summary table
        {"range": f"H3:H11", "values": [asset_types], "major_dimension": "COLUMNS"},
        {"range": f"I3:I11", "values": [total_values], "major_dimension": "COLUMNS"},
        {"range": f"J3:J11", "values": [allocations], "major_dimension": "COLUMNS"},
        {
            "range": f"K3:K11",
            "values": [expected_allocations],
            "major_dimension": "COLUMNS",
        },
    ]

    ### ### ### ### ### ### ### ### ### ### ### ### ### ###
    # Filling data into the spreadsheet:
    ### ### ### ### ### ### ### ### ### ### ### ### ### ###

    sheet.batch_update(prepared_data)

    ### ### ### ### ### ### ### ### ### ### ### ### ### ###
    # Individual cells update
    ### ### ### ### ### ### ### ### ### ### ### ### ### ###

    sheet.update(f"D{crypto_position_finish + 1}", "Mining")
    sheet.update(f"E{crypto_position_finish + 1}", f"{p_alloc.mining_mkt_value}")

    sheet.update("H1", "Financial Freedom")
    sheet.update("I1", f"{ff.calculate_financial_freedom_goal_progress()}")

    sheet.update("H12", "Monthly Dividend")
    sheet.update("I12", f"{d.get_my_monthly_and_yearly_dividends()[0]}")

    sheet.update("M1", "Dasha")
    sheet.update("N1", f"{p_alloc.dasha_net_worth}")

    ### ### ### ### ### ### ### ### ### ### ### ### ### ###
    # Cells formating
    ### ### ### ### ### ### ### ### ### ### ### ### ### ###

    frm.formatSpreadheet(sheet)

### ### ### ### ### ### ### ###
