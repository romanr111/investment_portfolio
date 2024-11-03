import time

from src.brokers.ib import InteractiveBrokers
from src.crypto.crypto_tokens import CryptoEndpoint
from src.google_sheets.structure import SpreadsheetManager

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


def main():
    worksheet_name = "Test 2024"
    ib = InteractiveBrokers()
    crypto = CryptoEndpoint()
    portfolio_manager = SpreadsheetManager(worksheet_name, ib, crypto)
    portfolio_manager.update_data()
    portfolio_manager.format_spreadsheet()


if __name__ == "__main__":
    start_time = time.time()
    main()
    print("--- TOTAL: %s seconds ---" % (time.time() - start_time))
