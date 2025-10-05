import time
import logging
import sys
import traceback
from src.google_sheets.spreadsheet_structure import update_portfolio_spreadsheet
from src.logging.portfolio_logger import (
    log_portfolio_data,
    log_portfolio_metadata,
)
from src.data_source import DataSource

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
    logger.debug("Starting main function")
    try:
        logger.debug("Initializing DataSource")
        data_source = DataSource()
        logger.debug("DataSource initialization completed")

        logger.debug("Getting data from DataSource")
        data = data_source.get_data()
        logger.debug("Data retrieved from DataSource")

        # Get the IB client from the DataSource if available
        ib_client = None
        try:
            if hasattr(data_source, "ib") and data_source.ib:
                ib_client = data_source.ib
                enhanced_stocks = ib_client.get_stock_positions_analytics()
                log_portfolio_data(enhanced_stocks)
        except Exception as e:
            logger.warning(f"Could not get IB client or print enhanced data: {str(e)}")
            ib_client = None

        logger.debug("Updating portfolio")
        # Check if enhanced stock data already exists in the data
        if "ENHANCED_STOCKS" in data and not ib_client:
            enhanced_stocks = data["ENHANCED_STOCKS"]
            metadata = enhanced_stocks.get("metadata", {})
            if metadata:
                log_portfolio_metadata(metadata)

        # Use the update_portfolio_spreadsheet function directly with the IB client
        update_portfolio_spreadsheet(
            data, CREDENTIALS_PATH, SPREADSHEET_NAME, ib_client
        )
        logger.debug("Portfolio update completed")
    except Exception as e:
        logger.error(f"Error in main function: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")


if __name__ == "__main__":
    logger.info("Starting portfolio update process")
    logger.info("Python version: " + sys.version)

    start_time = time.time()
    try:
        main()
        logger.info("Portfolio update process completed successfully")
    except Exception as e:
        logger.error(f"Top-level exception in main script: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"--- TOTAL: {elapsed_time:.2f} seconds ---")
