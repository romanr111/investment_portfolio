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

        # Get the IB client from the DataSource if available
        ib_client = None
        try:
            if hasattr(data_source, "ib") and data_source.ib:
                logger.debug("Getting IB client for enhanced stock data")
                ib_client = data_source.ib
                logger.info("Successfully obtained IB client for enhanced stock data")

                # Print enhanced stock data to terminal logs
                print("\n=== Enhanced Stock Positions ===")
                enhanced_stocks = ib_client.get_enhanced_stock_positions()

                # Print metadata
                metadata = enhanced_stocks["metadata"]
                print(f"Total Portfolio Value: ${metadata['total_portfolio_value']}")
                print(f"Total Stocks Value: ${metadata['total_stocks_value']}")
                print(
                    f"Total Unrealized P&L: {metadata['total_unrealized_pnl_percentage']}%"
                )
                print(
                    f"China Stocks Value: ${metadata['china_stocks_value']} ({metadata['china_stocks_value']/metadata['total_stocks_value']*100:.2f}%)"
                )
                print(
                    f"Regular Stocks Value: ${metadata['regular_stocks_value']} ({metadata['regular_stocks_value']/metadata['total_stocks_value']*100:.2f}%)"
                )

                # Print China Stocks details
                print("\nChina Stocks:")
                for symbol, details in enhanced_stocks["China Stocks"].items():
                    print(f"  {symbol}:")
                    print(f"    Market Value: ${details['market_value']}")
                    print(f"    Quantity: {details['quantity']} shares")
                    print(f"    Avg Price: ${details['avg_price']:.2f}")
                    print(f"    Current Price: ${details['current_price']:.2f}")
                    print(
                        f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%"
                    )
                    print(
                        f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%"
                    )
                    print(
                        f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%"
                    )

                # Print Regular Stocks details
                print("\nRegular Stocks:")
                for symbol, details in enhanced_stocks["Stocks"].items():
                    print(f"  {symbol}:")
                    print(f"    Market Value: ${details['market_value']}")
                    print(f"    Quantity: {details['quantity']} shares")
                    print(f"    Avg Price: ${details['avg_price']:.2f}")
                    print(f"    Current Price: ${details['current_price']:.2f}")
                    print(
                        f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%"
                    )
                    print(
                        f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%"
                    )
                    print(
                        f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%"
                    )

                print("========================\n")
        except Exception as e:
            logger.warning(f"Could not get IB client or print enhanced data: {str(e)}")
            ib_client = None

        print("Updating portfolio")
        logger.debug("Updating portfolio")

        # Check if enhanced stock data already exists in the data
        if "ENHANCED_STOCKS" in data and not ib_client:
            print("\n=== Enhanced Stock Positions (Pre-Existing) ===")
            enhanced_stocks = data["ENHANCED_STOCKS"]

            # Print metadata
            metadata = enhanced_stocks.get("metadata", {})
            if metadata:
                print(
                    f"Total Portfolio Value: ${metadata.get('total_portfolio_value', 'N/A')}"
                )
                print(
                    f"Total Stocks Value: ${metadata.get('total_stocks_value', 'N/A')}"
                )
                print(
                    f"Total Unrealized P&L: {metadata.get('total_unrealized_pnl_percentage', 'N/A')}%"
                )

                total_stocks_value = metadata.get("total_stocks_value", 0)
                china_stocks_value = metadata.get("china_stocks_value", 0)
                regular_stocks_value = metadata.get("regular_stocks_value", 0)

                if total_stocks_value > 0:
                    print(
                        f"China Stocks Value: ${china_stocks_value} ({china_stocks_value/total_stocks_value*100:.2f}%)"
                    )
                    print(
                        f"Regular Stocks Value: ${regular_stocks_value} ({regular_stocks_value/total_stocks_value*100:.2f}%)"
                    )

            print("========================\n")

        # Use the update_portfolio function directly with the IB client
        update_portfolio(data, CREDENTIALS_PATH, SPREADSHEET_NAME, ib_client)
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
