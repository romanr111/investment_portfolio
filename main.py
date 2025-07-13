import time
import logging
import sys
import traceback
from src.google_sheets.spreadsheet_structure import update_portfolio
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


def log_portfolio_data(enhanced_stocks):
    """Log portfolio data in a structured format"""
    metadata = enhanced_stocks["metadata"]
    logger.info("=== Enhanced Stock Positions ===")
    logger.info(f"Total Portfolio Value: ${metadata['total_portfolio_value']}")
    logger.info(f"Total Stocks Value: ${metadata['total_stocks_value']}")
    logger.info(f"Total Unrealized P&L: {metadata['total_unrealized_pnl_percentage']}%")
    logger.info(f"China Stocks Value: ${metadata['china_stocks_value']} ({metadata['china_stocks_value']/metadata['total_stocks_value']*100:.2f}%)")
    logger.info(f"Regular Stocks Value: ${metadata['regular_stocks_value']} ({metadata['regular_stocks_value']/metadata['total_stocks_value']*100:.2f}%)")

    # Log China Stocks details
    logger.info("\nChina Stocks:")
    for symbol, details in enhanced_stocks["China Stocks"].items():
        logger.info(f"  {symbol}:")
        logger.info(f"    Market Value: ${details['market_value']}")
        logger.info(f"    Quantity: {details['quantity']} shares")
        logger.info(f"    Avg Price: ${details['avg_price']:.2f}")
        logger.info(f"    Current Price: ${details['current_price']:.2f}")
        logger.info(f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%")
        logger.info(f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%")
        logger.info(f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%")

    # Log Regular Stocks details
    logger.info("\nRegular Stocks:")
    for symbol, details in enhanced_stocks["Stocks"].items():
        logger.info(f"  {symbol}:")
        logger.info(f"    Market Value: ${details['market_value']}")
        logger.info(f"    Quantity: {details['quantity']} shares")
        logger.info(f"    Avg Price: ${details['avg_price']:.2f}")
        logger.info(f"    Current Price: ${details['current_price']:.2f}")
        logger.info(f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%")
        logger.info(f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%")
        logger.info(f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%")


def log_portfolio_metadata(metadata):
    """Log portfolio metadata in a structured format"""
    logger.info("=== Enhanced Stock Positions (Pre-Existing) ===")
    logger.info(f"Total Portfolio Value: ${metadata.get('total_portfolio_value', 'N/A')}")
    logger.info(f"Total Stocks Value: ${metadata.get('total_stocks_value', 'N/A')}")
    logger.info(f"Total Unrealized P&L: {metadata.get('total_unrealized_pnl_percentage', 'N/A')}%")

    total_stocks_value = metadata.get("total_stocks_value", 0)
    china_stocks_value = metadata.get("china_stocks_value", 0)
    regular_stocks_value = metadata.get("regular_stocks_value", 0)

    if total_stocks_value > 0:
        logger.info(f"China Stocks Value: ${china_stocks_value} ({china_stocks_value/total_stocks_value*100:.2f}%)")
        logger.info(f"Regular Stocks Value: ${regular_stocks_value} ({regular_stocks_value/total_stocks_value*100:.2f}%)")


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
                logger.debug("Getting IB client for enhanced stock data")
                ib_client = data_source.ib
                logger.info("Successfully obtained IB client for enhanced stock data")

                enhanced_stocks = ib_client.get_enhanced_stock_positions()
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

        # Use the update_portfolio function directly with the IB client
        update_portfolio(data, CREDENTIALS_PATH, SPREADSHEET_NAME, ib_client)
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
