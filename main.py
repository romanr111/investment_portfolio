import time

from src.brokers.ib import InteractiveBrokers
from src.crypto.crypto import CryptoEndpoint
from src.cash_fixed_income.cash_summary import Cash
from src.dasha.dasha import DashaPortfolio
from src.brokers.ib import InteractiveBrokers
from src.brokers.ib_dividends import PublicDividends
from src.crypto.crypto import CryptoEndpoint
from src.cash_fixed_income.cash_summary import Cash
from src.google_sheets.allocation import PortfolioAllocations
from src.google_sheets.formatting import SpreadsheetFormatter
from src.google_sheets.structure import DataSource, PortfolioManager
from src.fire import FinancialFreedom

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


def main():
    worksheet_name = "Test 2023"
    ib = InteractiveBrokers()
    crypto = CryptoEndpoint()
    portfolio_manager = PortfolioManager(worksheet_name, ib, crypto)
    portfolio_manager.update_data()
    portfolio_manager.format_spreadsheet()


if __name__ == "__main__":
    start_time = time.time()
    main()
    print("--- TOTAL: %s seconds ---" % (time.time() - start_time))
