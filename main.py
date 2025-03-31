import time
import logging
import sys
import traceback
from src.google_sheets.spreadsheet_structure import PortfolioUpdater
from data_source import DataSource

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#

CREDENTIALS_PATH = "data/credentials.json"
SPREADSHEET_NAME = "portfolio_automated"

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    print("STARTING MAIN FUNCTION - BEFORE LOGGING")
    logger.debug("Starting main function")
    try:
        print("Before initializing DataSource")
        logger.debug("Before initializing DataSource")
        data_source = DataSource()
        print("DataSource initialized")
        logger.debug("After DataSource initialization")

        print("Getting data from DataSource")
        logger.debug("Getting data from DataSource")
        data = data_source.get_data()
        print("Data retrieved")
        logger.debug("Data retrieved from DataSource")

        print("Initializing PortfolioUpdater")
        logger.debug("Initializing PortfolioUpdater")
        updater = PortfolioUpdater(CREDENTIALS_PATH, SPREADSHEET_NAME)

        print("Updating portfolio")
        logger.debug("Updating portfolio")
        updater.update_portfolio(data)
        print("Portfolio updated")
        logger.debug("Portfolio update completed")
    except Exception as e:
        print(f"ERROR in main function: {str(e)}")
        logger.error(f"Error in main function: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")


if __name__ == "__main__":
    print("STARTING SCRIPT - BEFORE LOGGING")
    logger.info("Starting portfolio update process")
    print("LOGGING INITIALIZED")
    logger.info("Python version: " + sys.version)
    print("PYTHON VERSION LOGGED")

    start_time = time.time()
    try:
        print("ABOUT TO CALL MAIN")
        main()
        print("MAIN COMPLETED")
        logger.info("Portfolio update process completed successfully")
    except Exception as e:
        print(f"TOP LEVEL EXCEPTION: {str(e)}")
        logger.error(f"Top-level exception in main script: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
    finally:
        elapsed_time = time.time() - start_time
        print(f"--- TOTAL: {elapsed_time:.2f} seconds ---")
        logger.info(f"--- TOTAL: {elapsed_time:.2f} seconds ---")
