from typing import Dict
import logging
import time
import traceback

from data.filters_constants import IB_BONDS_KEY
from src.brokers.ib import InteractiveBrokers
from src.brokers.ib_dividends import IBDividends
from src.cash_fixed_income.cash_summary import CashPortfolio
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio
from src.crypto.crypto_tokens import CryptoEndpoint
from src.allocation_calculator import get_sorted_sector_allocations
from src.dasha.dasha import DashaPortfolio

# Set up logging
logger = logging.getLogger(__name__)

FINANCIAL_FREEDOM_GOAL = 500000

#
# cd Documents/Development/Portfolio/clientportal.gw  && arch -x86_64 /bin/zsh bin/run.sh root/conf.yaml
#


class DataSource:
    def __init__(self):
        logger.debug("Initializing DataSource - constructor start")
        try:
            logger.debug("About to initialize data sources")
            start_time = time.time()
            self._initialize_data_sources()
            logger.debug(
                f"Data sources initialized in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("About to prepare portfolio data")
            start_time = time.time()
            self._prepare_portfolio_data()
            logger.debug(
                f"Portfolio data prepared in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("About to calculate stock dividends")
            start_time = time.time()
            self._calculate_stock_dividends()
            logger.debug(
                f"Stock dividends calculated in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("About to setup fixed income")
            start_time = time.time()
            self._setup_fixed_income()
            logger.debug(
                f"Fixed income setup completed in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("About to setup cash and dasha")
            start_time = time.time()
            self._setup_cash_and_dasha()
            logger.debug(
                f"Cash and dasha setup completed in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("About to calculate total assets")
            start_time = time.time()
            self.total_assets = self.calculate_total_assets()
            logger.debug(
                f"Total assets calculated in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("About to calculate FF goal progress")
            start_time = time.time()
            self.ff_progress = self.calculate_ff_goal_progress()
            logger.debug(
                f"FF goal progress calculated in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("DataSource initialization completed")
        except Exception as e:
            logger.error(f"Error in DataSource initialization: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def _initialize_data_sources(self) -> None:
        """Initialize primary data source connections."""
        try:
            logger.debug("Initializing Interactive Brokers connection - start")
            start_time = time.time()
            self.ib = InteractiveBrokers()
            logger.debug(
                f"InteractiveBrokers initialized in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("Initializing Crypto Endpoint - start")
            start_time = time.time()
            self.crypto = CryptoEndpoint()
            logger.debug(
                f"CryptoEndpoint initialized in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("Getting crypto savings - start")
            start_time = time.time()
            self.crypto_savings = self.crypto.all_crypto_savings
            logger.debug(
                f"Crypto savings retrieved in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("Data sources initialization completed")
        except Exception as e:
            logger.error(f"Error in _initialize_data_sources: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def _prepare_portfolio_data(self) -> None:
        """Prepare Interactive Brokers portfolio and dividend data."""
        try:
            logger.debug("Getting full portfolio data from IB - start")
            start_time = time.time()
            self.ib_data = self.ib.get_full_porfolio_data()
            logger.debug(
                f"Retrieved IB portfolio data in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("Getting IB bonds data - start")
            start_time = time.time()
            self.ib_bonds = self.ib_data.get(IB_BONDS_KEY, {})
            logger.debug(
                f"Retrieved IB bonds data in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("Initializing IB Dividends - start")
            start_time = time.time()
            self.ib_div = IBDividends(self.ib_data)
            logger.debug(
                f"IB Dividends initialized in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("Processing dividend data - start")
            start_time = time.time()
            self._process_dividend_data()
            logger.debug(
                f"Dividend data processed in {time.time() - start_time:.2f} seconds"
            )

            logger.debug("Portfolio data preparation completed")
        except Exception as e:
            logger.error(f"Error in _prepare_portfolio_data: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def _process_dividend_data(self) -> None:
        """Process dividend data from Interactive Brokers."""
        logger.debug("Getting monthly and yearly dividends")
        (
            self.monthly_dividends,
            self.yearly_dividends,
            self.stock_yearly_div,
            self.dividend_details,
        ) = self.ib_div.get_my_total_monthly_and_yearly_divs()
        logger.debug("Dividend data processing completed")

    def _calculate_stock_dividends(self) -> None:
        """Calculate stock dividend yields."""
        logger.debug("Getting total stocks value")
        self.ib_stocks_value = self.ib_data["Total Stocks Value"]
        logger.debug("Calculating yearly dividend yield")
        self.stocks_yearly_dividend_yield = round(
            (self.stock_yearly_div / self.ib_stocks_value) * 100, 2
        )
        logger.debug(f"Stock dividend yield: {self.stocks_yearly_dividend_yield}%")

    def _setup_fixed_income(self) -> None:
        """Initialize and process fixed income data."""
        logger.debug("Initializing FixedIncomePortfolio")
        self.fixed_income_endpoint = FixedIncomePortfolio(
            self.ib_bonds, self.dividend_details, self.crypto_savings
        )
        logger.debug("Getting combined fixed income data")
        self.fi_data = self.fixed_income_endpoint.get_combined_fixed_income_data()
        logger.debug("Updating fixed income with stocks")
        self._update_fixed_income_with_stocks()
        logger.debug("Fixed income setup completed")

    def _setup_cash_and_dasha(self) -> None:
        """Initialize cash and Dasha portfolio components."""
        logger.debug("Initializing CashPortfolio")
        self.cash = CashPortfolio(
            self.ib_data["Net_cash"],
            self.crypto.free_cash,
        )
        logger.debug("Initializing DashaPortfolio")
        self.dasha = DashaPortfolio(self.ib)
        logger.debug("Cash and Dasha setup completed")

    def _update_fixed_income_with_stocks(self) -> None:
        """Update fixed income data with stock-related calculations."""
        logger.debug("Adding stock principal data")
        self._add_stock_principal_data()
        logger.debug("Calculating total earnings")
        self._calculate_total_earnings()
        logger.debug("Fixed income with stocks update completed")

    def _add_stock_principal_data(self) -> None:
        """Add stock principal and interest data to fixed income."""
        logger.debug("Adding stocks principal and interest to fixed income")
        self.fi_data["stocks_principal_and_interest"] = {
            "total_principal": self.ib_stocks_value,
            "weighted_interest": self.stocks_yearly_dividend_yield,
        }
        logger.debug("Calculating stocks monthly and yearly values")
        self.fi_data["stocks_monthly"] = int(self.stock_yearly_div / 12)
        self.fi_data["stocks_yearly"] = int(self.stock_yearly_div)
        logger.debug("Stock principal data added")

    def _calculate_total_earnings(self) -> None:
        """Calculate total monthly and yearly earnings."""
        logger.debug("Calculating total monthly and yearly earnings")
        monthly = (
            self.fi_data["monthly_earnings_fixed_income"]
            + self.fi_data["stocks_monthly"]
        )
        yearly = (
            self.fi_data["yearly_earnings_fixed_income"] + self.fi_data["stocks_yearly"]
        )

        self.fi_data.update(
            {"total_monthly": int(monthly), "total_yearly": int(yearly)}
        )
        logger.debug(f"Total monthly: {int(monthly)}, Total yearly: {int(yearly)}")

    def calculate_total_assets(self) -> int:
        """Calculate total portfolio assets value."""
        logger.debug("Calculating total assets")
        asset_values = [
            self.ib_data["IB_Portfolio_Value"],
            self.crypto.get_total_crypto_value(),
            self.fi_data["group_weighted_interest"]["Crypto Landing"][0],
            self.fi_data["group_weighted_interest"]["p2p_lending"][0],
            float(self.cash.total_cash),
        ]
        total = int(sum(asset_values))
        logger.debug(f"Total assets: {total}")
        return total

    def calculate_ff_goal_progress(self):
        logger.debug("Calculating financial freedom goal progress")
        current = self.total_assets
        goal_progress = round((current / FINANCIAL_FREEDOM_GOAL) * 100, 2)
        progress = str(goal_progress) + "%"
        logger.debug(f"FF goal progress: {progress}")
        return progress

    def get_combined_data(self) -> Dict:
        """Get combined portfolio data including all assets and calculations."""
        logger.debug("Getting combined data")
        return {
            "IB_DATA": self.ib_data,
            "CRYPTO_DATA": {
                "Total_Crypto_Value": self.crypto.get_total_crypto_value(),
                "Crypto_Market_Values": self.crypto.crypto_market_values,
                "Token_Quantities": self.crypto.quantities,
            },
            "FIXED_INCOME_DATA": self.fi_data,
            "CASH_DATA": {
                "Total": self.cash.total_cash,
                "Breakdown": self.cash.as_dict(),
            },
            "TOTAL_ASSETS": self.total_assets,
            "FIN_FREEDOM_GOAL_PROGRESS": self.ff_progress,
        }

    def get_data(self) -> Dict:
        logger.debug("Starting get_data method")
        data = self.get_combined_data()
        logger.debug("Calculating allocations")
        allocations = get_sorted_sector_allocations(data)
        data["ALLOCATIONS"] = allocations
        logger.debug("Data preparation completed")
        return data


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting DataSource test run")
    data_source = DataSource()
    portfolio_data = data_source.get_data()
    print()
    print(portfolio_data)
    print()
    logger.info("DataSource test run completed")
