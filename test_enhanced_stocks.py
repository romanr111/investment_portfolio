import os
import logging
from src.brokers.ib import InteractiveBrokers
from src.google_sheets.spreadsheet_structure import (
    update_portfolio,
    create_enhanced_stocks_data,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_with_ib_client():
    """Test using the IB client to automatically extract enhanced stock data."""
    try:
        # Initialize IB client
        ib_client = InteractiveBrokers()

        # Get regular portfolio data
        portfolio_data = {
            "IB_DATA": ib_client.get_portfolio_positions(),
            # Add other data as needed
            "TOTAL_ASSETS": 150000,  # Example value
        }

        # Update portfolio with enhanced stock data automatically extracted
        update_portfolio(
            data=portfolio_data,
            credentials_path="data/credentials.json",
            spreadsheet_name="portfolio_automated",
            ib_client=ib_client,  # Pass the IB client to automatically extract enhanced data
        )

        logger.info(
            "Successfully updated portfolio with enhanced stock data from IB client"
        )

    except Exception as e:
        logger.error(f"Error testing with IB client: {str(e)}")


def test_with_manual_data():
    """Test using manually constructed enhanced stock data."""
    try:
        # Create portfolio data
        portfolio_data = {
            "IB_DATA": {
                "Bonds": {"TLT": 5916, "SGOV": 1510},
                "China Stocks": {"9988": 8226, "KWEB": 4618, "PDD": 2128},
                "Stocks": {"GOOG": 2941, "AAPL": 3500},
                "Total Stocks Value": 21413,
                "IB_Portfolio_Value": 28839,
            },
            "TOTAL_ASSETS": 30000,  # Example value
        }

        # Create enhanced stock data manually
        enhanced_stocks = create_enhanced_stocks_data(
            china_stocks={
                "9988": {
                    "market_value": 8226,
                    "quantity": 500,
                    "avg_price": 96.49,
                    "current_price": 128.00,
                    "unrealized_pnl": 15753.74,
                    "unrealized_pnl_percentage": 32.65,
                    "percentage_of_stocks": 38.42,
                    "percentage_of_portfolio": 28.52,
                },
                "KWEB": {
                    "market_value": 4618,
                    "quantity": 133,
                    "avg_price": 32.10,
                    "current_price": 34.72,
                    "unrealized_pnl": 348.64,
                    "unrealized_pnl_percentage": 8.17,
                    "percentage_of_stocks": 21.57,
                    "percentage_of_portfolio": 16.01,
                },
                "PDD": {
                    "market_value": 2128,
                    "quantity": 18,
                    "avg_price": 115.84,
                    "current_price": 118.20,
                    "unrealized_pnl": 42.51,
                    "unrealized_pnl_percentage": 2.04,
                    "percentage_of_stocks": 9.94,
                    "percentage_of_portfolio": 7.38,
                },
            },
            regular_stocks={
                "GOOG": {
                    "market_value": 2941,
                    "quantity": 19,
                    "avg_price": 136.79,
                    "current_price": 154.78,
                    "unrealized_pnl": 334.54,
                    "unrealized_pnl_percentage": 13.15,
                    "percentage_of_stocks": 13.73,
                    "percentage_of_portfolio": 10.20,
                },
                "AAPL": {
                    "market_value": 3500,
                    "quantity": 20,
                    "avg_price": 150.00,
                    "current_price": 175.00,
                    "unrealized_pnl": 500.00,
                    "unrealized_pnl_percentage": 16.67,
                    "percentage_of_stocks": 16.34,
                    "percentage_of_portfolio": 12.14,
                },
            },
            metadata={
                "total_stocks_value": 21413,
                "china_stocks_value": 14972,
                "regular_stocks_value": 6441,
                "total_portfolio_value": 28839,
                "total_unrealized_pnl": 16979.43,
                "total_unrealized_pnl_percentage": 19.30,
            },
        )

        # Add the enhanced stock data to the portfolio data
        portfolio_data["ENHANCED_STOCKS"] = enhanced_stocks

        # Update portfolio with manually created enhanced stock data
        update_portfolio(
            data=portfolio_data,
            credentials_path="data/credentials.json",
            spreadsheet_name="portfolio_automated",
        )

        logger.info(
            "Successfully updated portfolio with manually created enhanced stock data"
        )

    except Exception as e:
        logger.error(f"Error testing with manual data: {str(e)}")


if __name__ == "__main__":
    # Uncomment the test you want to run
    # test_with_ib_client()
    test_with_manual_data()
