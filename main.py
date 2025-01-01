import time
from src.google_sheets.spreadsheet_structure import PortfolioUpdater
from data_source import DataSource

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#

CREDENTIALS_PATH = "data/credentials.json"
SPREADSHEET_NAME = "portfolio_automated"


def main():

    data_source = DataSource()
    data = data_source.get_data()
    updater = PortfolioUpdater(CREDENTIALS_PATH, SPREADSHEET_NAME)
    updater.update_portfolio(data)


if __name__ == "__main__":
    start_time = time.time()
    main()
    print("--- TOTAL: %s seconds ---" % (time.time() - start_time))
